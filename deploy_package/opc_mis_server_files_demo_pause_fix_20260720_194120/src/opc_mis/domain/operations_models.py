"""Domain contracts for deterministic Operations assessment artifacts."""

from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictFloat, StrictInt, StrictStr

from opc_mis.domain.artifacts import ArtifactEnvelope
from opc_mis.domain.components import ComponentResult
from opc_mis.domain.enums import (
    ComponentStatus,
    OperationsAssessmentStatus,
    OperationsCalculation,
    OperationsDataScope,
    OperationsFactQuality,
    OperationsMetric,
    OperationsObservationCode,
    OperationsSourceStatusCategory,
    OperationsUnit,
    WorkflowStatus,
)
from opc_mis.domain.missing_data import MissingDataRequest
from opc_mis.domain.validation_reports import ValidationReport

OperationsValue = StrictBool | StrictInt | StrictFloat | StrictStr | None


class OperationsRequest(BaseModel):
    """Typed Operations input parsed from workflow-owned component input."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    dataset_id: str
    evaluation_case_id: str
    as_of_date: date | None = None


class OperationsFact(BaseModel):
    """One verified operational value with complete evidence lineage."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    fact_id: str
    metric: OperationsMetric
    value: OperationsValue
    unit: OperationsUnit
    scope: OperationsDataScope
    quality: OperationsFactQuality
    calculation: OperationsCalculation
    evidence_id: str
    source_evidence_ids: tuple[str, ...]
    note: str | None = None


class OrderScheduleFact(BaseModel):
    """Per-order planned schedule derived only from exact source fields."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    order_id: str
    order_date: date
    due_date: date
    planned_duration_days: int = Field(ge=1)
    source_status: str
    status_category: OperationsSourceStatusCategory
    outside_contract_window: bool
    past_due_days: int | None = Field(default=None, ge=0)
    evidence_ids: tuple[str, ...]


class SourceOrderNote(BaseModel):
    """Uninterpreted delivery note retained as source evidence."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    order_id: str
    text: str
    evidence_id: str


class OperationsObservation(BaseModel):
    """A traceable condition; not a risk finding or recommendation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    observation_id: str
    code: OperationsObservationCode
    title: str
    detail: str
    fact_ids: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()


class OperationsEvidenceLimitation(BaseModel):
    """Non-blocking limitation in available operational evidence."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    limitation_id: str
    code: str
    detail: str
    scope: OperationsDataScope
    evidence_ids: tuple[str, ...] = ()


class OperationsSummaryStatement(BaseModel):
    """Deterministic summary sentence tied to verified facts."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    statement_id: str
    text: str
    fact_ids: tuple[str, ...] = Field(min_length=1)


class OperationsFacts(BaseModel):
    """Authoritative deterministic Operations output."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    evaluation_case_id: str
    dataset_id: str
    contract_id: str
    as_of_date: date | None
    facts: tuple[OperationsFact, ...]
    order_schedules: tuple[OrderScheduleFact, ...]
    source_notes: tuple[SourceOrderNote, ...]
    observations: tuple[OperationsObservation, ...]
    limitations: tuple[OperationsEvidenceLimitation, ...]


class OperationsAssessment(BaseModel):
    """Operations assessment without risk classification or approval logic."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    evaluation_case_id: str
    dataset_id: str
    contract_id: str
    assessment_status: OperationsAssessmentStatus
    facts_input_hash: str
    fact_ids: tuple[str, ...]
    observations: tuple[OperationsObservation, ...]
    limitations: tuple[OperationsEvidenceLimitation, ...]
    summary: tuple[OperationsSummaryStatement, ...]


class OperationsComponentResult(ComponentResult):
    """Typed result of the side-effect-free Operations business component."""

    operations_facts: OperationsFacts | None = None
    operations_assessment: OperationsAssessment | None = None


class OperationsExecutionResult(BaseModel):
    """Validated Operations workflow response returned by API and CLI."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: WorkflowStatus
    component_status: ComponentStatus
    current_node: str
    operations_facts: OperationsFacts | None = None
    operations_assessment: OperationsAssessment | None = None
    generated_artifacts: tuple[ArtifactEnvelope, ...] = ()
    validation_reports: tuple[ValidationReport, ...] = ()
    validation_errors: tuple[str, ...] = ()
    missing_data_requests: tuple[MissingDataRequest, ...] = ()
    warnings: tuple[str, ...] = ()
    runtime_events: tuple[dict[str, Any], ...] = ()
