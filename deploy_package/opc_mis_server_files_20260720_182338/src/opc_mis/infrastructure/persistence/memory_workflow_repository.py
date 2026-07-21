"""Process-local workflow state adapter for CLI and tests."""

from opc_mis.domain.workflow import WorkflowRunState


class InMemoryWorkflowStateRepository:
    """Store the latest state for each workflow run ID."""

    def __init__(self) -> None:
        self._states: dict[str, WorkflowRunState] = {}

    async def save(self, state: WorkflowRunState) -> None:
        """Persist or replace one state snapshot."""
        self._states[state.workflow_run_id] = state

    async def get(self, workflow_run_id: str) -> WorkflowRunState | None:
        """Return the current state for a workflow run."""
        return self._states.get(workflow_run_id)
