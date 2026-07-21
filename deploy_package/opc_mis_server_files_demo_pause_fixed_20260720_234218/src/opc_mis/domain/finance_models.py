"""Domain contracts for deterministic Finance assessment artifacts."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictFloat, StrictInt, StrictStr

from opc_mis.domain.artifacts import ArtifactEnvelope
from opc_mis.domain.components import ComponentResult
from opc_mis.domain.enums import (
    ComponentStatus,
    FinanceAssessmentStatus,
    FinanceCalculation,
    FinanceDataScope,
    FinanceFactQuality,
    FinanceMetric,
    FinanceNarrativeSource,
    FinanceObservationCode,
    FinanceUnit,
    WorkflowStatus,
)
from opc_mis.domain.missing_data import MissingDataRequest
from opc_mis.domain.validation_reports import ValidationReport

FinanceValue = StrictBool | StrictInt | StrictFloat | StrictStr | None


class FinanceFact(BaseModel):
    """One typed value with explicit scope, quality, and evidence lineage."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    fact_id: str
    metric: FinanceMetric
    value: FinanceValue
    unit: FinanceUnit
    scope: FinanceDataScope
    quality: FinanceFactQuality
    calculation: FinanceCalculation
    evidence_id: str
    source_evidence_ids: tuple[str, ...]
    note: str | None = None


class FinanceObservation(BaseModel):
    """A traceable condition; deliberately not a risk finding or severity."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    observation_id: str
    code: FinanceObservationCode
    title: str
    detail: str
    fact_ids: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()


class FinanceEvidenceLimitation(BaseModel):
    """A non-blocking limitation caused by unavailable explicit relationships."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    limitation_id: str
    code: str
    detail: str
    scope: FinanceDataScope
    evidence_ids: tuple[str, ...] = ()


class FinanceNarrativeStatement(BaseModel):
    """Composer text that must cite already verified Finance facts."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    statement_id: str
    text: str
    fact_ids: tuple[str, ...] = Field(min_length=1)


class FinanceNarrative(BaseModel):
    """Non-authoritative narrative produced from sanitized facts only."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    headline: str
    statements: tuple[FinanceNarrativeStatement, ...]


class FinanceNarrativeComposition(BaseModel):
    """Narrative plus safe runtime metadata returned through the composer port."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    narrative: FinanceNarrative
    source: FinanceNarrativeSource
    model: str
    prompt_version: str
    fallback_reason: str | None = None


class FinanceComposerInput(BaseModel):
    """Sanitized, case-scoped payload allowed to leave through the LLM port."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    facts: tuple[FinanceFact, ...]
    observations: tuple[FinanceObservation, ...]
    limitations: tuple[FinanceEvidenceLimitation, ...]


class FinanceFacts(BaseModel):
    """Authoritative deterministic Finance output."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    evaluation_case_id: str
    dataset_id: str
    contract_id: str
    facts: tuple[FinanceFact, ...]
    observations: tuple[FinanceObservation, ...]
    limitations: tuple[FinanceEvidenceLimitation, ...]


class FinanceAssessment(BaseModel):
    """Finance assessment layered on FinanceFacts without risk decisions."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    evaluation_case_id: str
    dataset_id: str
    contract_id: str
    assessment_status: FinanceAssessmentStatus
    facts_input_hash: str
    fact_ids: tuple[str, ...]
    observations: tuple[FinanceObservation, ...]
    limitations: tuple[FinanceEvidenceLimitation, ...]
    narrative: FinanceNarrative
    narrative_source: FinanceNarrativeSource
    composer_model: str
    prompt_version: str


class FinanceComponentResult(ComponentResult):
    """Typed result of the side-effect-free Finance business component."""

    finance_facts: FinanceFacts | None = None
    finance_assessment: FinanceAssessment | None = None


class FinanceExecutionResult(BaseModel):
    """Validated Finance workflow response returned by API and CLI."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: WorkflowStatus
    component_status: ComponentStatus
    current_node: str
    finance_facts: FinanceFacts | None = None
    finance_assessment: FinanceAssessment | None = None
    generated_artifacts: tuple[ArtifactEnvelope, ...] = ()
    validation_reports: tuple[ValidationReport, ...] = ()
    validation_errors: tuple[str, ...] = ()
    missing_data_requests: tuple[MissingDataRequest, ...] = ()
    warnings: tuple[str, ...] = ()
    runtime_events: tuple[dict[str, Any], ...] = ()
