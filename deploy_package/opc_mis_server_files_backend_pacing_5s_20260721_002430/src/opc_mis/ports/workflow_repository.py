"""Workflow state persistence port."""

from typing import Protocol

from opc_mis.domain.workflow import WorkflowRunState


class WorkflowStateRepository(Protocol):
    """Persist the latest state after every workflow node attempt."""

    async def save(self, state: WorkflowRunState) -> None:
        """Persist or replace the current workflow run state."""
        ...

    async def get(self, workflow_run_id: str) -> WorkflowRunState | None:
        """Return a workflow run state when present."""
        ...
