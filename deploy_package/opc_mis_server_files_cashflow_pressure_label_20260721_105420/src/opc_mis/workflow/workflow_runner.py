"""In-process durable queue runner with startup recovery for Master Workflows."""

import asyncio

from opc_mis.ports.case_workflow_repository import CaseWorkflowRepository
from opc_mis.workflow.case_workflow_orchestrator import CaseWorkflowOrchestrator


class WorkflowRunner:
    """Execute durable runs in the background; SQLite remains the source of truth."""

    def __init__(
        self,
        *,
        orchestrator: CaseWorkflowOrchestrator,
        workflows: CaseWorkflowRepository,
    ) -> None:
        self._orchestrator = orchestrator
        self._workflows = workflows
        self._queue: asyncio.Queue[str | None] = asyncio.Queue()
        self._queued: set[str] = set()
        self._active: set[str] = set()
        self._rerun_requested: set[str] = set()
        self._locks: dict[str, asyncio.Lock] = {}
        self._worker: asyncio.Task[None] | None = None
        self._stopping = False

    async def start(self, *, dataset_id: str, dataset_snapshot_hash: str) -> None:
        """Recover persisted PENDING/RUNNING work and start one local worker."""
        if self._worker is not None:
            return
        self._stopping = False
        self._worker = asyncio.create_task(self._work_loop(), name="opc-workflow-runner")
        for run in await self._workflows.list_recoverable(
            dataset_id, dataset_snapshot_hash
        ):
            await self.enqueue(run.workflow_run_id)

    async def enqueue(self, workflow_run_id: str) -> None:
        """Queue a run idempotently within this process."""
        if self._stopping:
            return
        if workflow_run_id in self._active:
            self._rerun_requested.add(workflow_run_id)
            return
        if workflow_run_id in self._queued:
            return
        self._queued.add(workflow_run_id)
        await self._queue.put(workflow_run_id)

    async def stop(self) -> None:
        """Finish the active item and stop accepting background work."""
        worker = self._worker
        if worker is None:
            return
        self._stopping = True
        await self._queue.put(None)
        await worker
        self._worker = None
        self._queued.clear()
        self._active.clear()
        self._rerun_requested.clear()

    async def _work_loop(self) -> None:
        while True:
            workflow_run_id = await self._queue.get()
            if workflow_run_id is None:
                self._queue.task_done()
                return
            lock = self._locks.setdefault(workflow_run_id, asyncio.Lock())
            self._queued.discard(workflow_run_id)
            self._active.add(workflow_run_id)
            try:
                async with lock:
                    await self._orchestrator.execute(workflow_run_id)
            finally:
                self._active.discard(workflow_run_id)
                if (
                    not self._stopping
                    and workflow_run_id in self._rerun_requested
                ):
                    self._rerun_requested.discard(workflow_run_id)
                    self._queued.add(workflow_run_id)
                    self._queue.put_nowait(workflow_run_id)
                self._queue.task_done()
