"""Typed, founder-facing projection contracts for one persisted workflow run."""

from enum import StrEnum
from typing import Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictFloat,
    StrictInt,
    StrictStr,
    model_validator,
)

from opc_mis.domain.decision_models import DecisionConfidence, DecisionRecommendation
from opc_mis.domain.enums import (
    ArtifactType,
    ContractRequirementType,
    CurrencyCode,
    FinanceDataScope,
    FinanceFactQuality,
    FinanceUnit,
    ProtectedAction,
    ReadinessStatus,
    RequirementCertainty,
    ValidationStatus,
    WorkflowStatus,
)


class DashboardApplicability(StrEnum):
    """Whether a canonical workflow task belongs to the currently resolved route."""

    APPLICABLE = "APPLICABLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    UNDETERMINED = "UNDETERMINED"


class DashboardTaskStatus(StrEnum):
    """Presentation-safe status for one canonical workflow task."""

    NOT_STARTED = "NOT_STARTED"
    RUNNING = "RUNNING"
    WAITING_FOR_DEPENDENCIES = "WAITING_FOR_DEPENDENCIES"
    WAITING_FOR_INPUT = "WAITING_FOR_INPUT"
    WAITING_FOR_APPROVAL = "WAITING_FOR_APPROVAL"
    COMPLETED = "COMPLETED"
    COMPLETED_WITH_WARNINGS = "COMPLETED_WITH_WARNINGS"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    BLOCKED = "BLOCKED"
    FAILED_SAFE = "FAILED_SAFE"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class DashboardBusinessStatus(StrEnum):
    """Business meaning kept separate from workflow execution status."""

    ASSESSMENT_IN_PROGRESS = "ASSESSMENT_IN_PROGRESS"
    WAITING_FOR_INPUT = "WAITING_FOR_INPUT"
    WAITING_FOR_BANKING_APPROVAL = "WAITING_FOR_BANKING_APPROVAL"
    PREPARING_DECISION = "PREPARING_DECISION"
    WAITING_FOR_FINAL_DECISION = "WAITING_FOR_FINAL_DECISION"
    WAITING_FOR_EXTERNAL_RELEASE_APPROVAL = "WAITING_FOR_EXTERNAL_RELEASE_APPROVAL"
    NOT_EVALUABLE = "NOT_EVALUABLE"
    NEGOTIATION_IN_PROGRESS = "NEGOTIATION_IN_PROGRESS"
    ACCEPTED = "ACCEPTED"
    NOT_ACCEPTED = "NOT_ACCEPTED"
    READY_FOR_EXTERNAL_SUBMISSION = "READY_FOR_EXTERNAL_SUBMISSION"
    BLOCKED = "BLOCKED"
    FAILED_SAFE = "FAILED_SAFE"


class DashboardInteractionType(StrEnum):
    """Typed interaction the dashboard may safely offer to the Founder."""

    APPROVAL = "APPROVAL"
    BANKING_AMOUNT_INPUT = "BANKING_AMOUNT_INPUT"
    BANKING_PRECHECK_EVIDENCE = "BANKING_PRECHECK_EVIDENCE"
    DOCUMENT_EVIDENCE = "DOCUMENT_EVIDENCE"
    UNSUPPORTED_INPUT = "UNSUPPORTED_INPUT"
    NOT_EVALUABLE_REVIEW = "NOT_EVALUABLE_REVIEW"


DashboardMetricValue = StrictBool | StrictInt | StrictFloat | StrictStr | None


class DashboardProgress(BaseModel):
    """Progress over a fixed canonical task set, including resolved non-applicable tasks."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    resolved_task_count: int = Field(ge=0)
    total_task_count: int = Field(gt=0)
    percent: int = Field(ge=0, le=100)
    basis: Literal["CANONICAL_WORKFLOW_TASKS"] = "CANONICAL_WORKFLOW_TASKS"


class DashboardTask(BaseModel):
    """One chronological, explicitly applicable workflow task."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    task_id: str
    owner_id: str
    title_vi: str
    applicability: DashboardApplicability
    applicability_reason_vi: str
    status: DashboardTaskStatus
    status_label_vi: str
    artifact_ids: tuple[str, ...] = ()
    approval_request_ids: tuple[str, ...] = ()
    resolution_status: str | None = None


class DashboardStage(BaseModel):
    """One canonical stage; parallel tasks share the same stage."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    stage_id: str
    sequence: int = Field(ge=1)
    title_vi: str
    parallel: bool = False
    applicability: DashboardApplicability
    status: DashboardTaskStatus
    status_label_vi: str
    tasks: tuple[DashboardTask, ...] = Field(min_length=1)


class DashboardArtifactReference(BaseModel):
    """Run-scoped artifact identity without payload or evidence details."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    artifact_id: str
    artifact_type: ArtifactType
    version: int = Field(ge=1)
    validation_status: ValidationStatus


class DashboardPendingInteraction(BaseModel):
    """A typed Founder interaction contract consumable by the dashboard."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    interaction_type: DashboardInteractionType
    title_vi: str
    instruction_vi: str
    request_ids: tuple[str, ...] = ()
    approval_request_ids: tuple[str, ...] = ()
    protected_action: ProtectedAction | None = None
    subject_artifact_id: str | None = None
    subject_artifact_version: int | None = Field(default=None, ge=1)
    endpoint: str | None = None
    required_fields: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_interaction_contract(self) -> Self:
        """Keep approval and view-only interactions bound to an exact artifact."""

        has_subject_id = self.subject_artifact_id is not None
        has_subject_version = self.subject_artifact_version is not None
        if has_subject_id is not has_subject_version:
            raise ValueError(
                "subject_artifact_id and subject_artifact_version must be supplied together"
            )
        if self.interaction_type is DashboardInteractionType.APPROVAL and not (
            has_subject_id and has_subject_version
        ):
            raise ValueError("APPROVAL interaction requires an exact subject artifact")
        if self.interaction_type is DashboardInteractionType.NOT_EVALUABLE_REVIEW:
            if not (has_subject_id and has_subject_version):
                raise ValueError(
                    "NOT_EVALUABLE_REVIEW requires an exact Decision Card artifact"
                )
            if (
                self.endpoint is not None
                or self.protected_action is not None
                or self.request_ids
                or self.approval_request_ids
                or self.required_fields
            ):
                raise ValueError(
                    "NOT_EVALUABLE_REVIEW must be view-only and cannot carry actions or requests"
                )
        return self


class DashboardMetric(BaseModel):
    """Founder-facing metric with explicit business scope and no evidence lineage."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str
    label_vi: str
    value: DashboardMetricValue
    unit: FinanceUnit
    scope: FinanceDataScope
    quality: FinanceFactQuality
    note_vi: str | None = None


class DashboardDecisionCardSummary(BaseModel):
    """Exact current-run Decision Card summary without evidence or model metadata."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    available: bool
    artifact_id: str | None = None
    decision_card_id: str | None = None
    recommendation: DecisionRecommendation | None = None
    recommendation_label_vi: str
    confidence: DecisionConfidence | None = None
    executive_summary: str | None = None


class DashboardContractRequirement(BaseModel):
    """Explicit contract requirement without evidence or source identifiers."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    requirement_type: ContractRequirementType
    certainty: RequirementCertainty
    requested_amount: StrictInt | None = None
    requested_amount_currency: CurrencyCode
    credit_case_id: str | None = None


class DashboardInputSummary(BaseModel):
    """Planner input/readiness summary safe for Founder presentation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    available: bool
    readiness_status: ReadinessStatus | None = None
    readiness_label_vi: str
    blocking_missing_count: int = Field(default=0, ge=0)
    warning_count: int = Field(default=0, ge=0)
    linked_customer_count: int = Field(default=0, ge=0)
    linked_order_count: int = Field(default=0, ge=0)
    linked_invoice_count: int = Field(default=0, ge=0)
    linked_service_count: int = Field(default=0, ge=0)
    linked_credit_profile_count: int = Field(default=0, ge=0)
    contract_requirements: tuple[DashboardContractRequirement, ...] = ()


class DashboardWorkflowProjection(BaseModel):
    """Complete read model for the Founder dashboard."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    workflow_run_id: str
    evaluation_case_id: str | None
    contract_id: str
    execution_status: WorkflowStatus
    execution_status_label_vi: str
    business_status: DashboardBusinessStatus
    business_status_label_vi: str
    current_stage: str
    current_stage_label_vi: str
    progress: DashboardProgress
    stages: tuple[DashboardStage, ...]
    run_artifacts: tuple[DashboardArtifactReference, ...] = ()
    approval_request_ids: tuple[str, ...] = ()
    pending_interactions: tuple[DashboardPendingInteraction, ...] = ()
    input: DashboardInputSummary
    metrics: tuple[DashboardMetric, ...] = ()
    decision_card: DashboardDecisionCardSummary
