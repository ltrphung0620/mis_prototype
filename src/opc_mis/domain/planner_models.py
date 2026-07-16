"""Pydantic domain models for Planner input and business output."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from opc_mis.domain.artifacts import ArtifactEnvelope
from opc_mis.domain.components import ComponentResult
from opc_mis.domain.enums import (
    CashflowScope,
    ComponentStatus,
    EvaluationScope,
    ReadinessStatus,
    RunTaskType,
    WorkflowStatus,
)
from opc_mis.domain.evidence import EvidenceRef
from opc_mis.domain.missing_data import MissingDataRequest
from opc_mis.domain.validation_reports import ValidationReport


def _non_empty(value: str) -> str:
    normalized = " ".join(value.split())
    if not normalized:
        raise ValueError("value must not be blank")
    return normalized


class PlannerRequest(BaseModel):
    """Typed component input parsed from an ExecutionContext."""

    model_config = ConfigDict(frozen=True)

    dataset_id: str
    contract_id: str
    evaluation_scope: tuple[EvaluationScope, ...]

    @field_validator("dataset_id")
    @classmethod
    def validate_dataset_id(cls, value: str) -> str:
        return _non_empty(value)

    @field_validator("contract_id")
    @classmethod
    def normalize_contract_id(cls, value: str) -> str:
        normalized = _non_empty(value).upper()
        if any(character.isspace() for character in normalized):
            raise ValueError("contract_id must not contain whitespace")
        return normalized

    @field_validator("evaluation_scope", mode="before")
    @classmethod
    def normalize_scopes(cls, value: Any) -> tuple[Any, ...]:
        if isinstance(value, str):
            value = (value,)
        unique: list[Any] = []
        for item in value:
            normalized = item.upper() if isinstance(item, str) else item
            if normalized not in unique:
                unique.append(normalized)
        if not unique:
            raise ValueError("at least one evaluation scope is required")
        scope_order = {
            EvaluationScope.FINANCE.value: 0,
            EvaluationScope.OPERATIONS.value: 1,
            EvaluationScope.RISK.value: 2,
        }
        return tuple(sorted(unique, key=lambda item: scope_order.get(str(item), 99)))


class PlannerWarning(BaseModel):
    """Traceable non-blocking evidence gap."""

    model_config = ConfigDict(frozen=True)

    warning_code: str
    target_record: str
    field: str
    reason: str
    evidence_refs: tuple[EvidenceRef, ...]
    details: dict[str, Any] = Field(default_factory=dict)


class DataReadiness(BaseModel):
    """Planner assessment of initial-assessment input sufficiency."""

    model_config = ConfigDict(frozen=True)

    status: ReadinessStatus
    blocking_missing_fields: tuple[str, ...]
    non_blocking_warnings: tuple[PlannerWarning, ...]
    validation_notes: tuple[str, ...]


class EvaluationCase(BaseModel):
    """Standardized, traceable case without workflow-owned state."""

    model_config = ConfigDict(frozen=True)

    evaluation_case_id: str
    dataset_id: str
    contract_id: str
    customer_id: str
    related_order_ids: tuple[str, ...]
    related_invoice_ids: tuple[str, ...]
    related_service_ids: tuple[str, ...]
    related_credit_case_ids: tuple[str, ...]
    evaluation_scope: tuple[EvaluationScope, ...]
    cashflow_scope: CashflowScope
    warnings: tuple[PlannerWarning, ...]
    evidence_refs: tuple[EvidenceRef, ...]


class RunPlan(BaseModel):
    """Planner's bounded plan containing initial assessment tasks only."""

    model_config = ConfigDict(frozen=True)

    parallel_initial_tasks: tuple[RunTaskType, ...]
    plan_reason: str


class PlannerResult(BaseModel):
    """Business payload produced by Planner."""

    model_config = ConfigDict(frozen=True)

    evaluation_case: EvaluationCase | None
    data_readiness: DataReadiness
    run_plan: RunPlan
    missing_data_requests: tuple[MissingDataRequest, ...]
    warnings: tuple[PlannerWarning, ...]
    evidence_refs: tuple[EvidenceRef, ...]


class PlannerComponentResult(ComponentResult):
    """Typed specialization of the shared component result."""

    planner_result: PlannerResult | None


class PlannerExecutionResult(BaseModel):
    """Planner-intake workflow response returned by the Orchestrator and CLI."""

    model_config = ConfigDict(frozen=True)

    status: WorkflowStatus
    component_status: ComponentStatus
    current_node: str
    planner_result: PlannerResult | None
    generated_artifacts: tuple[ArtifactEnvelope, ...]
    validation_reports: tuple[ValidationReport, ...] = ()
    validation_errors: tuple[str, ...] = ()
