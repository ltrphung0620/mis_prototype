"""Persistence port for Master Workflow run and node state."""

from typing import Protocol

from opc_mis.domain.case_workflow_models import CaseWorkflowRun, WorkflowNodeState


class CaseWorkflowRepository(Protocol):
    """Persist automatic case workflows independently from interface code."""

    async def save_run(self, run: CaseWorkflowRun) -> None: ...

    async def get_run(self, workflow_run_id: str) -> CaseWorkflowRun | None: ...

    async def list_recoverable(
        self, dataset_id: str, dataset_snapshot_hash: str
    ) -> tuple[CaseWorkflowRun, ...]: ...

    async def save_node(self, node: WorkflowNodeState) -> None: ...

    async def get_node(
        self, workflow_run_id: str, node: str
    ) -> WorkflowNodeState | None: ...

    async def list_nodes(self, workflow_run_id: str) -> tuple[WorkflowNodeState, ...]: ...
