"""Shared contract for all business components."""

from __future__ import annotations

from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator

from opc_mis.domain.approvals import ApprovalSignal
from opc_mis.domain.artifacts import ArtifactDraft
from opc_mis.domain.commands import ActionCommand
from opc_mis.domain.enums import ComponentStatus, EvaluationScope
from opc_mis.domain.events import RuntimeEvent
from opc_mis.domain.missing_data import MissingDataRequest


class ExecutionContext(BaseModel):
    """Workflow-owned context passed to one business component invocation."""

    model_config = ConfigDict(frozen=True)

    evaluation_case_id: str | None = None
    dataset_id: str
    workflow_run_id: str
    input_artifact_ids: tuple[str, ...] = ()
    requested_scope: tuple[EvaluationScope, ...]
    component_input: dict[str, Any] = Field(default_factory=dict)
    current_node: str

    @field_validator("requested_scope", mode="before")
    @classmethod
    def canonicalize_scope(cls, value: Any) -> tuple[Any, ...]:
        """Deduplicate and stabilize initial scope order for idempotent execution."""
        if isinstance(value, str):
            value = (value,)
        order = {
            EvaluationScope.FINANCE.value: 0,
            EvaluationScope.OPERATIONS.value: 1,
            EvaluationScope.RISK.value: 2,
        }
        unique: list[Any] = []
        for item in value:
            normalized = item.upper() if isinstance(item, str) else item
            if normalized not in unique:
                unique.append(normalized)
        return tuple(sorted(unique, key=lambda item: order.get(str(item), 99)))


class ComponentResult(BaseModel):
    """Common, side-effect-free result returned by a business component."""

    model_config = ConfigDict(frozen=True)

    status: ComponentStatus
    artifacts: tuple[ArtifactDraft, ...] = ()
    missing_data_requests: tuple[MissingDataRequest, ...] = ()
    approval_signals: tuple[ApprovalSignal, ...] = ()
    action_commands: tuple[ActionCommand, ...] = ()
    warnings: tuple[str, ...] = ()
    runtime_events: tuple[RuntimeEvent, ...] = ()


class BusinessComponent(Protocol):
    """Uniform async interface implemented by every business component."""

    component_id: str

    async def execute(self, context: ExecutionContext) -> ComponentResult:
        """Execute one deterministic component node without persisting workflow state."""
        ...
