"""HTTP request and discovery response schemas."""

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator

from opc_mis.domain.approvals import (
    ApprovalCheckpointSet,
    ApprovalDecision,
    ApprovalDecisionReasonCode,
)
from opc_mis.domain.banking_input_models import BankingInputExecutionResult
from opc_mis.domain.banking_models import (
    BankingDiscoveryExecutionResult,
    BankingDiscoveryHandoffExecutionResult,
    BankingDiscoveryRequest,
    BankingDiscoveryResult,
    BankingInputSupplement,
    BankingOptionAdvice,
    BankingOptionMatrix,
    BankingPrecheckReadiness,
    BankingPrecheckReadinessExecutionResult,
)
from opc_mis.domain.banking_precheck_evidence_models import (
    BankingPrecheckEvidenceExecutionResult,
    BankingPrecheckEvidenceSupplement,
)
from opc_mis.domain.case_workflow_models import WorkflowStartResult
from opc_mis.domain.decision_post_banking_models import (
    DecisionPostBankingExecutionResult,
    DecisionPostBankingReview,
)
from opc_mis.domain.decision_post_precheck_models import (
    DecisionPostPrecheckExecutionResult,
    DecisionPostPrecheckReview,
)
from opc_mis.domain.decision_route_models import (
    DecisionRouteExecutionResult,
    DecisionRoutePlan,
)
from opc_mis.domain.document_models import (
    DecisionDocumentHandoffExecutionResult,
    DocumentChecklist,
    DocumentEvidenceExecutionResult,
    DocumentEvidenceReasonCode,
    DocumentEvidenceSupplement,
    DocumentPackageDraft,
    DocumentPreparationRequest,
    DocumentReleasePackage,
    DocumentRequirementCode,
    DocumentSkillExecutionResult,
)
from opc_mis.domain.enums import (
    ArtifactType,
    BankingDiscoveryHandoffStatus,
    BankingDiscoveryStatus,
    ComponentStatus,
    CurrencyCode,
    EvaluationScope,
    FinanceAssessmentStatus,
    FinanceNarrativeSource,
    RiskDependency,
    RiskRunStatus,
    ValidationStatus,
    WorkflowStatus,
)
from opc_mis.domain.finance_models import (
    FinanceEvidenceLimitation,
    FinanceExecutionResult,
    FinanceFact,
    FinanceNarrative,
    FinanceObservation,
)
from opc_mis.domain.missing_data import MissingDataRequest
from opc_mis.domain.negotiation_models import (
    NegotiationConditionOutcomeInput,
    NegotiationOutcomeExecutionResult,
)
from opc_mis.domain.risk_models import (
    InitialRiskAssessment,
    RiskExecutionResult,
    RuleEvaluation,
)


class PlannerEvaluationRequest(BaseModel):
    """Swagger request for evaluating one contract through Planner Intake."""

    model_config = ConfigDict(
        frozen=True,
        json_schema_extra={
            "example": {
                "contract_id": "CONTRACT-ID",
                "evaluation_scope": ["FINANCE", "OPERATIONS", "RISK"],
            }
        },
    )

    contract_id: str = Field(description="Exact contract_id from 04_CONTRACTS")
    evaluation_scope: tuple[EvaluationScope, ...] = (
        EvaluationScope.FINANCE,
        EvaluationScope.OPERATIONS,
        EvaluationScope.RISK,
    )

    @field_validator("contract_id")
    @classmethod
    def normalize_contract_id(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not normalized or any(character.isspace() for character in normalized):
            raise ValueError("contract_id must be a non-empty identifier without whitespace")
        return normalized

    @field_validator("evaluation_scope", mode="before")
    @classmethod
    def require_scope(cls, value: Any) -> Any:
        if value is None or value == [] or value == ():
            raise ValueError("evaluation_scope must contain at least one scope")
        return value


class NegotiationTermsSentRequest(BaseModel):
    """Typed manual confirmation; this endpoint does not send email or CRM data."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    workflow_run_id: str = Field(min_length=1)
    decision_card_artifact_id: str = Field(min_length=1)


class NegotiationOutcomeSubmissionRequest(BaseModel):
    """Complete response set for every condition on the current Decision Card."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    workflow_run_id: str = Field(min_length=1)
    decision_card_artifact_id: str = Field(min_length=1)
    condition_outcomes: tuple[NegotiationConditionOutcomeInput, ...] = Field(
        min_length=1
    )
    founder_summary: str | None = Field(default=None, min_length=1, max_length=1000)


class NegotiationOutcomeResponse(BaseModel):
    """Persisted response artifact plus the automatically advanced workflow."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    result: NegotiationOutcomeExecutionResult
    workflow: WorkflowStartResult


class AutomaticCaseWorkflowRequest(BaseModel):
    """One-call request for the complete automatic Initial Assessment workflow."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        json_schema_extra={
            "example": {
                "contract_id": "CONTRACT-ID",
                "evaluation_scope": ["FINANCE", "OPERATIONS", "RISK"],
                "as_of_date": "2026-07-16",
                "run_request_id": "0190f15a-9b7d-7000-8000-000000000001",
            }
        },
    )

    contract_id: str = Field(description="Exact contract_id from 04_CONTRACTS")
    evaluation_scope: tuple[EvaluationScope, ...] = (
        EvaluationScope.FINANCE,
        EvaluationScope.OPERATIONS,
        EvaluationScope.RISK,
    )
    as_of_date: date | None = None
    run_request_id: str | None = Field(
        default=None,
        min_length=8,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$",
        description=(
            "Client-generated idempotency key for one intentional workflow run. "
            "Reuse the same key when retrying the same start request; use a new key "
            "only when the user explicitly starts a new evaluation run."
        ),
    )

    @field_validator("contract_id")
    @classmethod
    def normalize_contract_id(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not normalized or any(character.isspace() for character in normalized):
            raise ValueError("contract_id must be a non-empty identifier without whitespace")
        return normalized

    @field_validator("evaluation_scope", mode="after")
    @classmethod
    def require_complete_initial_scope(
        cls, value: tuple[EvaluationScope, ...]
    ) -> tuple[EvaluationScope, ...]:
        required = {
            EvaluationScope.FINANCE,
            EvaluationScope.OPERATIONS,
            EvaluationScope.RISK,
        }
        if set(value) != required or len(value) != len(required):
            raise ValueError(
                "automatic Initial Assessment requires FINANCE, OPERATIONS, and RISK"
            )
        return (
            EvaluationScope.FINANCE,
            EvaluationScope.OPERATIONS,
            EvaluationScope.RISK,
        )


class ContractCatalogResponse(BaseModel):
    """Contracts available for Swagger evaluation."""

    model_config = ConfigDict(frozen=True)

    dataset_id: str
    snapshot_hash: str
    contract_ids: tuple[str, ...]


class OperationsAssessmentRequest(BaseModel):
    """Optional point-in-time input for deterministic past-due calculations."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        json_schema_extra={"example": {"as_of_date": "2026-07-16"}},
    )

    as_of_date: date | None = Field(
        default=None,
        description=(
            "Explicit assessment date. If omitted, Operations reports past-due facts "
            "as unavailable rather than using the server clock."
        ),
    )


class ProtectedActionRequest(BaseModel):
    """A downstream component request that must pass the Governance gate."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        json_schema_extra={
            "example": {
                "workflow_run_id": "CWF-MASTER-WORKFLOW-ID",
                "payload_artifact_id": "ART-VALIDATED-CASE-ARTIFACT",
                "requested_by": "API_CLIENT",
                "payload": {"requested_amount": 300000001},
            }
        },
    )

    workflow_run_id: str | None = Field(
        default=None,
        description=(
            "Master Workflow to pause/resume. Omit only when testing Governance "
            "as a standalone component."
        ),
    )
    payload_artifact_id: str
    requested_by: str = Field(
        min_length=1,
        max_length=64,
        description=(
            "Compatibility label only. The public runtime replaces it with the "
            "server-owned PUBLIC_API_CLIENT audit actor."
        ),
    )
    payload: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Public endpoint accepts only optional requested_amount; Banking and "
            "Document protected-action payloads are workflow-generated."
        ),
    )


class ApprovalDecisionRequest(BaseModel):
    """Explicit human resolution for one pending ApprovalRequest."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        json_schema_extra={
            "example": {
                "decision": "APPROVE",
                "decided_by": "FOUNDER",
                "reason": "HUMAN_REVIEW_COMPLETED",
            }
        },
    )

    decision: ApprovalDecision
    decided_by: Literal["FOUNDER"] = Field(
        default="FOUNDER",
        description=(
            "Prototype approval principal. The server accepts Founder decisions only; "
            "a future authentication adapter must supply this identity."
        ),
    )
    reason: ApprovalDecisionReasonCode


class BankingAmountInputSubmissionRequest(BaseModel):
    """Legacy gap input; not used to override a Planner-linked contract amount."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    workflow_run_id: str = Field(min_length=1)
    missing_request_id: str = Field(min_length=1)
    requested_amount: StrictInt = Field(gt=0)
    requested_amount_currency: CurrencyCode = CurrencyCode.VND
    evidence_note: str = Field(min_length=1, max_length=500)


class BankingPrecheckEvidenceSubmissionRequest(BaseModel):
    """Staff evidence reference; identity is supplied by the server boundary."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    workflow_run_id: str = Field(min_length=1)
    missing_request_id: str = Field(min_length=1)
    evidence_reference_id: str = Field(min_length=1)
    evidence_note: str = Field(min_length=1)


class DocumentEvidenceSubmissionRequest(BaseModel):
    """Caller-declared metadata for an opaque document reference."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    workflow_run_id: str = Field(min_length=1)
    missing_request_id: str = Field(min_length=1)
    document_reference_id: str = Field(
        min_length=43,
        max_length=43,
        pattern=(
            r"^DOCREF-[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-4[0-9A-Fa-f]{3}-"
            r"[89ABab][0-9A-Fa-f]{3}-[0-9A-Fa-f]{12}$"
        ),
        description=(
            "Caller-declared DOCREF-UUIDv4 metadata; paths, URLs, arbitrary text, "
            "and raw content are rejected. "
            "This prototype does not verify it against a document repository."
        ),
    )
    content_sha256: str = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[0-9A-Fa-f]{64}$",
    )
    document_type: DocumentRequirementCode
    evidence_note: DocumentEvidenceReasonCode


class ArtifactReference(BaseModel):
    """Compact pointer to an immutable artifact available from the artifact endpoint."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    artifact_id: str
    artifact_type: ArtifactType
    version: int
    validation_status: ValidationStatus


class DecisionRouteResponse(BaseModel):
    """Compact Decision Initial Route response without repeated artifact payloads."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: WorkflowStatus
    component_status: ComponentStatus
    current_node: str
    route_plan: DecisionRoutePlan | None = None
    artifact_refs: tuple[ArtifactReference, ...] = ()
    validation_errors: tuple[str, ...] = ()
    missing_data_requests: tuple[MissingDataRequest, ...] = ()
    warnings: tuple[str, ...] = ()
    runtime_events: tuple[dict[str, Any], ...] = ()

    @classmethod
    def from_execution_result(
        cls, result: DecisionRouteExecutionResult
    ) -> "DecisionRouteResponse":
        return cls(
            status=result.status,
            component_status=result.component_status,
            current_node=result.current_node,
            route_plan=result.route_plan,
            artifact_refs=tuple(
                ArtifactReference(
                    artifact_id=item.artifact_id,
                    artifact_type=item.artifact_type,
                    version=item.version,
                    validation_status=item.validation_status,
                )
                for item in result.generated_artifacts
            ),
            validation_errors=result.validation_errors,
            missing_data_requests=result.missing_data_requests,
            warnings=result.warnings,
            runtime_events=result.runtime_events,
        )


class BankingDiscoveryHandoffResponse(BaseModel):
    """Compact Decision-to-Banking handoff response for Swagger clients."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: WorkflowStatus
    component_status: ComponentStatus
    current_node: str
    handoff_status: BankingDiscoveryHandoffStatus
    banking_discovery_request: BankingDiscoveryRequest | None = None
    artifact_refs: tuple[ArtifactReference, ...] = ()
    validation_errors: tuple[str, ...] = ()
    missing_data_requests: tuple[MissingDataRequest, ...] = ()
    warnings: tuple[str, ...] = ()
    runtime_events: tuple[dict[str, Any], ...] = ()

    @classmethod
    def from_execution_result(
        cls, result: BankingDiscoveryHandoffExecutionResult
    ) -> "BankingDiscoveryHandoffResponse":
        return cls(
            status=result.status,
            component_status=result.component_status,
            current_node=result.current_node,
            handoff_status=result.handoff_status,
            banking_discovery_request=result.banking_discovery_request,
            artifact_refs=tuple(
                ArtifactReference(
                    artifact_id=item.artifact_id,
                    artifact_type=item.artifact_type,
                    version=item.version,
                    validation_status=item.validation_status,
                )
                for item in result.generated_artifacts
            ),
            validation_errors=result.validation_errors,
            missing_data_requests=result.missing_data_requests,
            warnings=result.warnings,
            runtime_events=result.runtime_events,
        )


class BankingDiscoveryResponse(BaseModel):
    """Compact Phase A response with deterministic options and advisory prose."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: WorkflowStatus
    component_status: ComponentStatus
    current_node: str
    discovery_status: BankingDiscoveryStatus
    option_matrix: BankingOptionMatrix | None = None
    discovery_result: BankingDiscoveryResult | None = None
    option_advice: BankingOptionAdvice | None = None
    artifact_refs: tuple[ArtifactReference, ...] = ()
    validation_errors: tuple[str, ...] = ()
    missing_data_requests: tuple[MissingDataRequest, ...] = ()
    warnings: tuple[str, ...] = ()
    runtime_events: tuple[dict[str, Any], ...] = ()

    @classmethod
    def from_execution_result(
        cls, result: BankingDiscoveryExecutionResult
    ) -> "BankingDiscoveryResponse":
        return cls(
            status=result.status,
            component_status=result.component_status,
            current_node=result.current_node,
            discovery_status=result.discovery_status,
            option_matrix=result.option_matrix,
            discovery_result=result.discovery_result,
            option_advice=result.option_advice,
            artifact_refs=tuple(
                ArtifactReference(
                    artifact_id=item.artifact_id,
                    artifact_type=item.artifact_type,
                    version=item.version,
                    validation_status=item.validation_status,
                )
                for item in result.generated_artifacts
            ),
            validation_errors=result.validation_errors,
            missing_data_requests=result.missing_data_requests,
            warnings=result.warnings,
            runtime_events=result.runtime_events,
        )


class BankingPrecheckReadinessResponse(BaseModel):
    """Compact deterministic readiness response with no external API result."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: WorkflowStatus
    component_status: ComponentStatus
    current_node: str
    readiness: BankingPrecheckReadiness | None = None
    artifact_refs: tuple[ArtifactReference, ...] = ()
    validation_errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    runtime_events: tuple[dict[str, Any], ...] = ()

    @classmethod
    def from_execution_result(
        cls, result: BankingPrecheckReadinessExecutionResult
    ) -> "BankingPrecheckReadinessResponse":
        return cls(
            status=result.status,
            component_status=result.component_status,
            current_node=result.current_node,
            readiness=result.readiness,
            artifact_refs=tuple(
                ArtifactReference(
                    artifact_id=item.artifact_id,
                    artifact_type=item.artifact_type,
                    version=item.version,
                    validation_status=item.validation_status,
                )
                for item in result.generated_artifacts
            ),
            validation_errors=result.validation_errors,
            warnings=result.warnings,
            runtime_events=result.runtime_events,
        )


class DecisionPostBankingResponse(BaseModel):
    """Decision route review without selection, approval, or external execution."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: WorkflowStatus
    component_status: ComponentStatus
    current_node: str
    review: DecisionPostBankingReview | None = None
    artifact_refs: tuple[ArtifactReference, ...] = ()
    validation_errors: tuple[str, ...] = ()
    missing_data_requests: tuple[MissingDataRequest, ...] = ()
    warnings: tuple[str, ...] = ()
    runtime_events: tuple[dict[str, Any], ...] = ()

    @classmethod
    def from_execution_result(
        cls, result: DecisionPostBankingExecutionResult
    ) -> "DecisionPostBankingResponse":
        return cls(
            status=result.status,
            component_status=result.component_status,
            current_node=result.current_node,
            review=result.review,
            artifact_refs=tuple(
                ArtifactReference(
                    artifact_id=item.artifact_id,
                    artifact_type=item.artifact_type,
                    version=item.version,
                    validation_status=item.validation_status,
                )
                for item in result.generated_artifacts
            ),
            validation_errors=result.validation_errors,
            missing_data_requests=result.missing_data_requests,
            warnings=result.warnings,
            runtime_events=result.runtime_events,
        )


class DecisionPostPrecheckResponse(BaseModel):
    """Typed result classification without selection or downstream execution."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: WorkflowStatus
    component_status: ComponentStatus
    current_node: str
    review: DecisionPostPrecheckReview | None = None
    artifact_refs: tuple[ArtifactReference, ...] = ()
    validation_errors: tuple[str, ...] = ()
    missing_data_requests: tuple[MissingDataRequest, ...] = ()
    warnings: tuple[str, ...] = ()
    runtime_events: tuple[dict[str, Any], ...] = ()

    @classmethod
    def from_execution_result(
        cls, result: DecisionPostPrecheckExecutionResult
    ) -> "DecisionPostPrecheckResponse":
        return cls(
            status=result.status,
            component_status=result.component_status,
            current_node=result.current_node,
            review=result.review,
            artifact_refs=tuple(
                ArtifactReference(
                    artifact_id=item.artifact_id,
                    artifact_type=item.artifact_type,
                    version=item.version,
                    validation_status=item.validation_status,
                )
                for item in result.generated_artifacts
            ),
            validation_errors=result.validation_errors,
            missing_data_requests=result.missing_data_requests,
            warnings=result.warnings,
            runtime_events=result.runtime_events,
        )


class DecisionDocumentHandoffResponse(BaseModel):
    """Compact Decision-to-Document handoff without selecting an option."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: WorkflowStatus
    component_status: ComponentStatus
    current_node: str
    preparation_requests: tuple[DocumentPreparationRequest, ...] = ()
    artifact_refs: tuple[ArtifactReference, ...] = ()
    validation_errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    runtime_events: tuple[dict[str, Any], ...] = ()

    @classmethod
    def from_execution_result(
        cls, result: DecisionDocumentHandoffExecutionResult
    ) -> "DecisionDocumentHandoffResponse":
        return cls(
            status=result.status,
            component_status=result.component_status,
            current_node=result.current_node,
            preparation_requests=result.preparation_requests,
            artifact_refs=tuple(
                ArtifactReference(
                    artifact_id=item.artifact_id,
                    artifact_type=item.artifact_type,
                    version=item.version,
                    validation_status=item.validation_status,
                )
                for item in result.generated_artifacts
            ),
            validation_errors=result.validation_errors,
            warnings=result.warnings,
            runtime_events=result.runtime_events,
        )


class DocumentPreparationResponse(BaseModel):
    """Masked internal dossier state; it never claims an external release."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: WorkflowStatus
    component_status: ComponentStatus
    current_node: str
    checklist: DocumentChecklist | None = None
    package_draft: DocumentPackageDraft | None = None
    release_package: DocumentReleasePackage | None = None
    artifact_refs: tuple[ArtifactReference, ...] = ()
    validation_errors: tuple[str, ...] = ()
    missing_data_requests: tuple[MissingDataRequest, ...] = ()
    warnings: tuple[str, ...] = ()
    runtime_events: tuple[dict[str, Any], ...] = ()

    @classmethod
    def from_execution_result(
        cls, result: DocumentSkillExecutionResult
    ) -> "DocumentPreparationResponse":
        return cls(
            status=result.status,
            component_status=result.component_status,
            current_node=result.current_node,
            checklist=result.checklist,
            package_draft=result.package_draft,
            release_package=result.release_package,
            artifact_refs=tuple(
                ArtifactReference(
                    artifact_id=item.artifact_id,
                    artifact_type=item.artifact_type,
                    version=item.version,
                    validation_status=item.validation_status,
                )
                for item in result.generated_artifacts
            ),
            validation_errors=result.validation_errors,
            missing_data_requests=result.missing_data_requests,
            warnings=result.warnings,
            runtime_events=result.runtime_events,
        )


class DocumentEvidenceSupplementResponse(BaseModel):
    """Accepted opaque evidence reference and automatically resumed workflow."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: WorkflowStatus
    component_status: ComponentStatus
    current_node: str
    supplement: DocumentEvidenceSupplement | None = None
    artifact_refs: tuple[ArtifactReference, ...] = ()
    workflow: WorkflowStartResult
    validation_errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    runtime_events: tuple[dict[str, Any], ...] = ()

    @classmethod
    def from_results(
        cls,
        result: DocumentEvidenceExecutionResult,
        workflow: WorkflowStartResult,
    ) -> "DocumentEvidenceSupplementResponse":
        return cls(
            status=result.status,
            component_status=result.component_status,
            current_node=result.current_node,
            supplement=result.supplement,
            artifact_refs=tuple(
                ArtifactReference(
                    artifact_id=item.artifact_id,
                    artifact_type=item.artifact_type,
                    version=item.version,
                    validation_status=item.validation_status,
                )
                for item in result.generated_artifacts
            ),
            workflow=workflow,
            validation_errors=result.validation_errors,
            warnings=result.warnings,
            runtime_events=result.runtime_events,
        )


class BankingInputSupplementResponse(BaseModel):
    """Accepted immutable Banking input plus the automatically resumed workflow."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: WorkflowStatus
    component_status: ComponentStatus
    current_node: str
    supplement: BankingInputSupplement | None = None
    artifact_refs: tuple[ArtifactReference, ...] = ()
    workflow: WorkflowStartResult
    validation_errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    runtime_events: tuple[dict[str, Any], ...] = ()

    @classmethod
    def from_results(
        cls,
        result: BankingInputExecutionResult,
        workflow: WorkflowStartResult,
    ) -> "BankingInputSupplementResponse":
        return cls(
            status=result.status,
            component_status=result.component_status,
            current_node=result.current_node,
            supplement=result.supplement,
            artifact_refs=tuple(
                ArtifactReference(
                    artifact_id=item.artifact_id,
                    artifact_type=item.artifact_type,
                    version=item.version,
                    validation_status=item.validation_status,
                )
                for item in result.generated_artifacts
            ),
            workflow=workflow,
            validation_errors=result.validation_errors,
            warnings=result.warnings,
            runtime_events=result.runtime_events,
        )


class BankingPrecheckEvidenceSupplementResponse(BaseModel):
    """Accepted evidence handoff and its explicit fresh-precheck workflow state."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: WorkflowStatus
    component_status: ComponentStatus
    current_node: str
    supplement: BankingPrecheckEvidenceSupplement | None = None
    artifact_refs: tuple[ArtifactReference, ...] = ()
    workflow: WorkflowStartResult
    validation_errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    runtime_events: tuple[dict[str, Any], ...] = ()

    @classmethod
    def from_results(
        cls,
        result: BankingPrecheckEvidenceExecutionResult,
        workflow: WorkflowStartResult,
    ) -> "BankingPrecheckEvidenceSupplementResponse":
        return cls(
            status=result.status,
            component_status=result.component_status,
            current_node=result.current_node,
            supplement=result.supplement,
            artifact_refs=tuple(
                ArtifactReference(
                    artifact_id=item.artifact_id,
                    artifact_type=item.artifact_type,
                    version=item.version,
                    validation_status=item.validation_status,
                )
                for item in result.generated_artifacts
            ),
            workflow=workflow,
            validation_errors=result.validation_errors,
            warnings=result.warnings,
            runtime_events=result.runtime_events,
        )


class FinanceAssessmentResponse(BaseModel):
    """Non-duplicating Finance response optimized for Swagger and frontend clients."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: WorkflowStatus
    component_status: ComponentStatus
    current_node: str
    evaluation_case_id: str | None = None
    dataset_id: str | None = None
    contract_id: str | None = None
    assessment_status: FinanceAssessmentStatus | None = None
    facts: tuple[FinanceFact, ...] = ()
    observations: tuple[FinanceObservation, ...] = ()
    limitations: tuple[FinanceEvidenceLimitation, ...] = ()
    narrative: FinanceNarrative | None = None
    narrative_source: FinanceNarrativeSource | None = None
    composer_model: str | None = None
    prompt_version: str | None = None
    artifact_refs: tuple[ArtifactReference, ...] = ()
    validation_errors: tuple[str, ...] = ()
    missing_data_requests: tuple[MissingDataRequest, ...] = ()
    warnings: tuple[str, ...] = ()
    runtime_events: tuple[dict[str, Any], ...] = ()

    @classmethod
    def from_execution_result(
        cls,
        result: FinanceExecutionResult,
    ) -> "FinanceAssessmentResponse":
        """Flatten one execution result without copying artifact payloads or evidence."""
        facts = result.finance_facts
        assessment = result.finance_assessment
        return cls(
            status=result.status,
            component_status=result.component_status,
            current_node=result.current_node,
            evaluation_case_id=(
                facts.evaluation_case_id
                if facts is not None
                else assessment.evaluation_case_id
                if assessment is not None
                else None
            ),
            dataset_id=(
                facts.dataset_id
                if facts is not None
                else assessment.dataset_id
                if assessment is not None
                else None
            ),
            contract_id=(
                facts.contract_id
                if facts is not None
                else assessment.contract_id
                if assessment is not None
                else None
            ),
            assessment_status=(assessment.assessment_status if assessment is not None else None),
            facts=facts.facts if facts is not None else (),
            observations=facts.observations if facts is not None else (),
            limitations=facts.limitations if facts is not None else (),
            narrative=assessment.narrative if assessment is not None else None,
            narrative_source=assessment.narrative_source if assessment is not None else None,
            composer_model=assessment.composer_model if assessment is not None else None,
            prompt_version=assessment.prompt_version if assessment is not None else None,
            artifact_refs=tuple(
                ArtifactReference(
                    artifact_id=item.artifact_id,
                    artifact_type=item.artifact_type,
                    version=item.version,
                    validation_status=item.validation_status,
                )
                for item in result.generated_artifacts
            ),
            validation_errors=result.validation_errors,
            missing_data_requests=result.missing_data_requests,
            warnings=result.warnings,
            runtime_events=result.runtime_events,
        )


class RiskPreScanSummary(BaseModel):
    """Compact proof that TeamPack scanning completed before dependency wait."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_rule_ids: tuple[str, ...]
    case_alert_ids: tuple[str, ...]
    global_alert_ids: tuple[str, ...]
    global_signal_codes: tuple[str, ...]
    source_record_counts: dict[str, int]


class RiskAssessmentResponse(BaseModel):
    """Non-duplicating Risk response for Swagger and frontend clients."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: WorkflowStatus
    component_status: ComponentStatus
    current_node: str
    risk_run_id: str
    checkpoint_status: RiskRunStatus
    evaluation_case_id: str | None = None
    contract_id: str | None = None
    pending_dependencies: tuple[RiskDependency, ...] = ()
    pre_scan: RiskPreScanSummary | None = None
    rule_evaluations: tuple[RuleEvaluation, ...] = ()
    risk_assessment: InitialRiskAssessment | None = None
    approval_checkpoints: ApprovalCheckpointSet | None = None
    artifact_refs: tuple[ArtifactReference, ...] = ()
    validation_errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    runtime_events: tuple[dict[str, Any], ...] = ()

    @classmethod
    def from_execution_result(cls, result: RiskExecutionResult) -> "RiskAssessmentResponse":
        """Flatten Risk workflow state without repeating artifact payloads or evidence."""
        pre_scan = result.pre_scan
        assessment = result.risk_assessment
        return cls(
            status=result.status,
            component_status=result.component_status,
            current_node=result.current_node,
            risk_run_id=result.risk_run_id,
            checkpoint_status=result.checkpoint_status,
            evaluation_case_id=(
                assessment.evaluation_case_id
                if assessment is not None
                else pre_scan.evaluation_case_id
                if pre_scan is not None
                else None
            ),
            contract_id=(
                assessment.contract_id
                if assessment is not None
                else pre_scan.contract_id
                if pre_scan is not None
                else None
            ),
            pending_dependencies=result.pending_dependencies,
            pre_scan=(
                RiskPreScanSummary(
                    source_rule_ids=pre_scan.source_rule_ids,
                    case_alert_ids=tuple(item.alert_id for item in pre_scan.case_alerts),
                    global_alert_ids=tuple(item.alert_id for item in pre_scan.global_alerts),
                    global_signal_codes=tuple(
                        item.code for item in pre_scan.global_signals
                    ),
                    source_record_counts=pre_scan.source_record_counts,
                )
                if pre_scan is not None
                else None
            ),
            rule_evaluations=(
                result.rule_evaluations.evaluations
                if result.rule_evaluations is not None
                else ()
            ),
            risk_assessment=assessment,
            approval_checkpoints=result.approval_checkpoints,
            artifact_refs=tuple(
                ArtifactReference(
                    artifact_id=item.artifact_id,
                    artifact_type=item.artifact_type,
                    version=item.version,
                    validation_status=item.validation_status,
                )
                for item in result.generated_artifacts
            ),
            validation_errors=result.validation_errors,
            warnings=result.warnings,
            runtime_events=result.runtime_events,
        )
