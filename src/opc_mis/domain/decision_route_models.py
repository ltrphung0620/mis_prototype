"""Domain contracts for deterministic Decision Initial Route Planning."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from opc_mis.domain.artifacts import ArtifactEnvelope
from opc_mis.domain.components import ComponentResult
from opc_mis.domain.enums import (
    BankingNeedType,
    ComponentStatus,
    DecisionCapability,
    DecisionRouteMode,
    DecisionRouteOutcome,
    DecisionRoutingReasonCode,
    WorkflowStatus,
)
from opc_mis.domain.missing_data import MissingDataRequest
from opc_mis.domain.validation_reports import ValidationReport


class DecisionRoutingReason(BaseModel):
    """One typed route reason tied to explicit upstream evidence."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    reason_id: str
    code: DecisionRoutingReasonCode
    banking_need_type: BankingNeedType
    source_artifact_id: str
    source_reference_ids: tuple[str, ...] = Field(min_length=1)
    evidence_ids: tuple[str, ...] = Field(min_length=1)


class DecisionRoutePlan(BaseModel):
    """Business route classification without workflow-owned next-node state."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    route_plan_id: str
    evaluation_case_id: str
    dataset_id: str
    contract_id: str
    execution_mode: DecisionRouteMode
    route_outcome: DecisionRouteOutcome
    required_capabilities: tuple[DecisionCapability, ...] = Field(min_length=1)
    banking_need_types: tuple[BankingNeedType, ...] = ()
    routing_reasons: tuple[DecisionRoutingReason, ...] = ()
    conditional_approval_checkpoint_ids: tuple[str, ...] = ()
    source_artifact_ids: tuple[str, ...] = Field(min_length=1)


class DecisionRouteComponentResult(ComponentResult):
    """Typed result returned by the side-effect-free Initial Route component."""

    route_plan: DecisionRoutePlan | None = None


class DecisionRouteExecutionResult(BaseModel):
    """Validated workflow result returned through the application boundary."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: WorkflowStatus
    component_status: ComponentStatus
    current_node: str
    route_plan: DecisionRoutePlan | None = None
    generated_artifacts: tuple[ArtifactEnvelope, ...] = ()
    validation_reports: tuple[ValidationReport, ...] = ()
    validation_errors: tuple[str, ...] = ()
    missing_data_requests: tuple[MissingDataRequest, ...] = ()
    warnings: tuple[str, ...] = ()
    runtime_events: tuple[dict[str, Any], ...] = ()
