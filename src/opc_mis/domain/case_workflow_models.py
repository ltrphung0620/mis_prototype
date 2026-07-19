"""Durable Master Workflow state, node, event, and API summary contracts."""

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from opc_mis.domain.document_models import (
    DocumentPackageReadiness,
    DocumentRequirementCode,
)
from opc_mis.domain.enums import (
    ArtifactType,
    BankingDiscoveryStatus,
    BankingPrecheckExecutionMode,
    BankingPrecheckOutcome,
    BankingPrecheckReadinessStatus,
    BankingPrecheckResultAuthority,
    CurrencyCode,
    DecisionPostBankingOutcome,
    DecisionPostPrecheckOutcome,
    DecisionRouteOutcome,
    EvaluationScope,
    ProtectedAction,
    ProviderEligibilityStatus,
    ProviderGuaranteeDecision,
    ValidationStatus,
    WorkflowNodeStatus,
    WorkflowStatus,
)
from opc_mis.domain.workflow import WorkflowNode


class CaseWorkflowRun(BaseModel):
    """Persisted state for one automatic contract Initial Assessment."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    workflow_run_id: str
    dataset_id: str
    dataset_snapshot_hash: str
    evaluation_case_id: str | None = None
    contract_id: str
    status: WorkflowStatus
    current_stage: str
    requested_scope: tuple[EvaluationScope, ...]
    as_of_date: date | None = None
    pending_request_ids: tuple[str, ...] = ()
    resume_stage: str | None = None
    blocked_action: ProtectedAction | None = None
    failure_reason: str | None = None
    created_at: datetime
    updated_at: datetime


class WorkflowNodeState(BaseModel):
    """Durable, idempotent status for one node in a case workflow."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    workflow_run_id: str
    node: WorkflowNode
    status: WorkflowNodeStatus
    attempt: int = Field(ge=0)
    input_hash: str | None = None
    output_artifact_ids: tuple[str, ...] = ()
    waiting_for: tuple[str, ...] = ()
    failure_reason: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None


class WorkflowEvent(BaseModel):
    """Append-only, redaction-safe business event for frontend polling and audit."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    event_id: str
    workflow_run_id: str
    sequence: int = Field(ge=1)
    event_type: str
    node: WorkflowNode | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class WorkflowArtifactReference(BaseModel):
    """Compact immutable artifact reference in a Master Workflow summary."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    artifact_id: str
    artifact_type: ArtifactType
    version: int
    validation_status: ValidationStatus


class WorkflowRunSummary(BaseModel):
    """Non-duplicating status response for the automatic case workflow."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    workflow_run_id: str
    evaluation_case_id: str | None
    contract_id: str
    status: WorkflowStatus
    current_stage: str
    nodes: tuple[WorkflowNodeState, ...]
    artifact_refs: tuple[WorkflowArtifactReference, ...] = ()
    approval_checkpoint_count: int = 0
    decision_route_outcome: DecisionRouteOutcome | None = None
    banking_discovery_request_id: str | None = None
    banking_discovery_status: BankingDiscoveryStatus | None = None
    banking_discovery_result_id: str | None = None
    banking_option_matrix_id: str | None = None
    banking_option_advice_id: str | None = None
    banking_option_count: int = Field(default=0, ge=0)
    banking_input_supplement_id: str | None = None
    banking_precheck_readiness_id: str | None = None
    banking_precheck_readiness_status: BankingPrecheckReadinessStatus | None = None
    decision_post_banking_review_id: str | None = None
    decision_post_banking_outcome: DecisionPostBankingOutcome | None = None
    precheck_ready_option_ids: tuple[str, ...] = ()
    banking_precheck_submission_proposal_id: str | None = None
    banking_precheck_submission_candidate_ids: tuple[str, ...] = ()
    banking_precheck_result_set_id: str | None = None
    banking_precheck_normalized_result_ids: tuple[str, ...] = ()
    banking_precheck_outcomes: tuple[BankingPrecheckOutcome, ...] = ()
    banking_precheck_eligibility_statuses: tuple[
        ProviderEligibilityStatus, ...
    ] = ()
    banking_precheck_guarantee_decisions: tuple[
        ProviderGuaranteeDecision, ...
    ] = ()
    banking_precheck_supported_amounts: tuple[int | None, ...] = ()
    banking_precheck_currencies: tuple[CurrencyCode, ...] = ()
    banking_precheck_required_document_codes: tuple[
        tuple[str, ...], ...
    ] = ()
    banking_precheck_approval_condition_codes: tuple[
        tuple[str, ...], ...
    ] = ()
    banking_precheck_execution_mode: BankingPrecheckExecutionMode | None = None
    banking_precheck_result_authority: BankingPrecheckResultAuthority | None = None
    banking_precheck_external_bank_submission: bool | None = None
    banking_precheck_bank_approval_obtained: bool | None = None
    decision_post_precheck_review_id: str | None = None
    decision_post_precheck_outcome: DecisionPostPrecheckOutcome | None = None
    decision_post_precheck_candidate_option_ids: tuple[str, ...] = ()
    decision_post_precheck_candidate_product_ids: tuple[str, ...] = ()
    decision_post_precheck_conditional_option_ids: tuple[str, ...] = ()
    decision_post_precheck_inconclusive_option_ids: tuple[str, ...] = ()
    decision_post_precheck_evidence_required_option_ids: tuple[str, ...] = ()
    decision_post_precheck_not_eligible_option_ids: tuple[str, ...] = ()
    decision_post_precheck_unavailable_option_ids: tuple[str, ...] = ()
    document_preparation_request_ids: tuple[str, ...] = ()
    document_checklist_ids: tuple[str, ...] = ()
    document_package_draft_ids: tuple[str, ...] = ()
    document_package_readinesses: tuple[DocumentPackageReadiness, ...] = ()
    document_release_package_ids: tuple[str, ...] = ()
    document_evidence_supplement_ids: tuple[str, ...] = ()
    document_pending_codes: tuple[DocumentRequirementCode, ...] = ()
    document_release_package_ready: bool = False
    ready_for_internal_decision: bool = False
    document_release_authorized: bool = False
    document_external_release_performed: bool = False
    pending_approval_ids: tuple[str, ...] = ()
    pending_missing_data_ids: tuple[str, ...] = ()
    resume_stage: str | None = None
    blocked_action: ProtectedAction | None = None
    failure_reason: str | None = None


class WorkflowStartResult(BaseModel):
    """Immediate response after a durable workflow is created or reused."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    workflow_run_id: str
    evaluation_case_id: str | None
    contract_id: str
    status: WorkflowStatus
    status_url: str
