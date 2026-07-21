"""Append-only workflow event persistence port."""

from datetime import datetime
from typing import Any, Protocol

from opc_mis.domain.case_workflow_models import WorkflowEvent
from opc_mis.domain.workflow import WorkflowNode


class RuntimeEventRepository(Protocol):
    """Append ordered workflow events and support polling by sequence."""

    async def append(
        self,
        *,
        workflow_run_id: str,
        event_type: str,
        node: WorkflowNode | None,
        metadata: dict[str, Any],
        created_at: datetime,
    ) -> WorkflowEvent: ...

    async def list_after(
        self, workflow_run_id: str, after_sequence: int
    ) -> tuple[WorkflowEvent, ...]: ...
