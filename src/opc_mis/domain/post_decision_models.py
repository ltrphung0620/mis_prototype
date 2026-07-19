"""Contracts for approved Decision routing and governed external release.

These models deliberately stop before any external adapter invocation.  A
Founder approval records one exact Decision Card outcome; a separate proposal
then gives Governance an exact, masked document-release subject to authorize.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictStr, model_validator

from opc_mis.domain.approvals import ApprovalRequest
from opc_mis.domain.artifacts import ArtifactEnvelope
from opc_mis.domain.components import ComponentResult
from opc_mis.domain.decision_models import (
    DecisionCard,
    DecisionDocumentReleaseSnapshot,
    DecisionRecommendation,
    ExactDecisionArtifactRef,
)
from opc_mis.domain.document_models import DocumentReleasePackage
from opc_mis.domain.enums import (
    ApprovalDecision,
    ApprovalRequestStatus,
    ArtifactType,
    ComponentStatus,
    ProtectedAction,
    WorkflowStatus,
)
from opc_mis.domain.lineage import deterministic_id
from opc_mis.domain.missing_data import MissingDataRequest
from opc_mis.domain.validation_reports import ValidationReport


class PostDecisionOutcome(StrEnum):
    """Deterministic route selected from the approved recommendation."""

    FINAL_DECISION_ACCEPTED = "FINAL_DECISION_ACCEPTED"
    NEGOTIATION_AUTHORIZED = "NEGOTIATION_AUTHORIZED"
    CASE_CLOSED_NO_EXTERNAL_ACTION = "CASE_CLOSED_NO_EXTERNAL_ACTION"


class ExternalSubmissionReadinessStatus(StrEnum):
    """The only honest result before an external connector exists."""

    READY_FOR_EXTERNAL_SUBMISSION = "READY_FOR_EXTERNAL_SUBMISSION"


class ApprovalResolutionInput(BaseModel):
    """Internal workflow input identifying a persisted Governance decision."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    approval_request_id: StrictStr = Field(min_length=1)


class FinalDecisionApprovalReference(BaseModel):
    """Auditable Founder approval of one exact persisted Decision Card."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    approval_request_id: StrictStr = Field(min_length=1)
    workflow_run_id: StrictStr = Field(min_length=1)
    evaluation_case_id: StrictStr = Field(min_length=1)
    subject_artifact_id: StrictStr = Field(min_length=1)
    subject_artifact_version: int = Field(ge=1)
    subject_input_hash: StrictStr = Field(min_length=1)
    protected_action: ProtectedAction = (
        ProtectedAction.CONFIRM_FINAL_CONTRACT_DECISION
    )
    status: ApprovalRequestStatus
    decision: ApprovalDecision
    decided_by: StrictStr = Field(min_length=1)
    decision_reason: StrictStr = Field(min_length=1)
    decided_at: datetime
    checkpoint_ids: tuple[StrictStr, ...] = ()
    policy_artifact_id: StrictStr | None = None
    policy_artifact_version: int | None = Field(default=None, ge=1)
    policy_input_hash: StrictStr | None = None
    policy_coverage_ids: tuple[StrictStr, ...] = ()
    action_payload_hash: StrictStr = Field(min_length=1)
    approver_role: Literal["FOUNDER"] = "FOUNDER"

    @model_validator(mode="after")
    def validate_approval(self) -> FinalDecisionApprovalReference:
        if (
            self.protected_action
            is not ProtectedAction.CONFIRM_FINAL_CONTRACT_DECISION
            or self.status is not ApprovalRequestStatus.APPROVED
            or self.decision is not ApprovalDecision.APPROVE
        ):
            raise ValueError("Final Decision requires an affirmative Founder approval")
        if self.decided_at.tzinfo is None:
            raise ValueError("Final Decision approval time must be timezone-aware")
        for label, values in (
            ("checkpoint_ids", self.checkpoint_ids),
            ("policy_coverage_ids", self.policy_coverage_ids),
        ):
            if len(set(values)) != len(values):
                raise ValueError(f"{label} must be unique")
        policy_identity = (
            self.policy_artifact_id,
            self.policy_artifact_version,
            self.policy_input_hash,
        )
        if any(value is not None for value in policy_identity) and not all(
            value is not None for value in policy_identity
        ):
            raise ValueError("Approval policy artifact identity must be complete")
        return self


class ExternalReleaseAuthorizationReference(BaseModel):
    """Governance authorization for one exact release proposal artifact."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    approval_request_id: StrictStr = Field(min_length=1)
    workflow_run_id: StrictStr = Field(min_length=1)
    evaluation_case_id: StrictStr = Field(min_length=1)
    subject_artifact_id: StrictStr = Field(min_length=1)
    subject_artifact_version: int = Field(ge=1)
    subject_input_hash: StrictStr = Field(min_length=1)
    protected_action: ProtectedAction = (
        ProtectedAction.SEND_DOCUMENT_TO_EXTERNAL_PARTNER
    )
    status: ApprovalRequestStatus
    decision: ApprovalDecision
    authorized_by: StrictStr = Field(min_length=1)
    authorization_reason: StrictStr = Field(min_length=1)
    authorized_at: datetime
    checkpoint_ids: tuple[StrictStr, ...] = ()
    policy_artifact_id: StrictStr | None = None
    policy_artifact_version: int | None = Field(default=None, ge=1)
    policy_input_hash: StrictStr | None = None
    policy_coverage_ids: tuple[StrictStr, ...] = ()
    action_payload_hash: StrictStr = Field(min_length=1)

    @model_validator(mode="after")
    def validate_authorization(self) -> ExternalReleaseAuthorizationReference:
        if (
            self.protected_action
            is not ProtectedAction.SEND_DOCUMENT_TO_EXTERNAL_PARTNER
            or self.status is not ApprovalRequestStatus.APPROVED
            or self.decision is not ApprovalDecision.APPROVE
        ):
            raise ValueError("External release requires exact affirmative authorization")
        if self.authorized_at.tzinfo is None:
            raise ValueError("External release authorization time must be timezone-aware")
        for label, values in (
            ("checkpoint_ids", self.checkpoint_ids),
            ("policy_coverage_ids", self.policy_coverage_ids),
        ):
            if len(set(values)) != len(values):
                raise ValueError(f"{label} must be unique")
        policy_identity = (
            self.policy_artifact_id,
            self.policy_artifact_version,
            self.policy_input_hash,
        )
        if any(value is not None for value in policy_identity) and not all(
            value is not None for value in policy_identity
        ):
            raise ValueError("Authorization policy artifact identity must be complete")
        return self


class PostDecisionUpdate(BaseModel):
    """Immutable routing result after Founder approves an exact Decision Card."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    update_id: StrictStr = Field(min_length=1)
    evaluation_case_id: StrictStr = Field(min_length=1)
    dataset_id: StrictStr = Field(min_length=1)
    contract_id: StrictStr = Field(min_length=1)
    decision_card_artifact: ExactDecisionArtifactRef
    decision_card_id: StrictStr = Field(min_length=1)
    founder_approval: FinalDecisionApprovalReference
    recommendation: DecisionRecommendation
    outcome: PostDecisionOutcome
    approved_condition_ids: tuple[StrictStr, ...] = ()
    approved_negotiation_strategy_ids: tuple[StrictStr, ...] = ()
    selected_option_ids: tuple[StrictStr, ...] = ()
    document_release_package: DecisionDocumentReleaseSnapshot | None = None
    external_document_release_required: bool
    evidence_ids: tuple[StrictStr, ...] = Field(min_length=1)
    founder_decision_recorded: Literal[True] = True
    external_document_submission_proposed: Literal[False] = False
    external_action_performed: Literal[False] = False

    @model_validator(mode="after")
    def validate_update(self) -> PostDecisionUpdate:
        if self.decision_card_artifact.artifact_type is not ArtifactType.DECISION_CARD:
            raise ValueError("Post-decision update must bind a Decision Card artifact")
        approval = self.founder_approval
        if approval.evaluation_case_id != self.evaluation_case_id:
            raise ValueError("Founder approval belongs to another case")
        if (
            approval.subject_artifact_id != self.decision_card_artifact.artifact_id
            or approval.subject_artifact_version
            != self.decision_card_artifact.version
            or approval.subject_input_hash != self.decision_card_artifact.input_hash
        ):
            raise ValueError("Founder approval does not bind the exact Decision Card")
        expected_outcome = post_decision_outcome(self.recommendation)
        if self.outcome is not expected_outcome:
            raise ValueError("Post-decision outcome contradicts the recommendation")
        expected_release = (
            self.recommendation is DecisionRecommendation.ACCEPT
            and self.document_release_package is not None
        )
        if self.external_document_release_required is not expected_release:
            raise ValueError("External-document route contradicts the approved Card")
        if (
            self.document_release_package is not None
            and not set(self.document_release_package.evidence_ids).issubset(
                self.evidence_ids
            )
        ):
            raise ValueError("Approved package evidence is absent from the Card lineage")
        for label, values in (
            ("approved_condition_ids", self.approved_condition_ids),
            (
                "approved_negotiation_strategy_ids",
                self.approved_negotiation_strategy_ids,
            ),
            ("selected_option_ids", self.selected_option_ids),
            ("evidence_ids", self.evidence_ids),
        ):
            if len(set(values)) != len(values):
                raise ValueError(f"{label} must be unique")
        expected_id = post_decision_update_id(
            decision_card_artifact=self.decision_card_artifact,
            decision_card_id=self.decision_card_id,
            founder_approval=self.founder_approval,
            recommendation=self.recommendation,
            outcome=self.outcome,
            approved_condition_ids=self.approved_condition_ids,
            approved_negotiation_strategy_ids=(
                self.approved_negotiation_strategy_ids
            ),
            selected_option_ids=self.selected_option_ids,
            document_release_package=self.document_release_package,
            evidence_ids=self.evidence_ids,
        )
        if self.update_id != expected_id:
            raise ValueError("Post-decision update_id is unstable")
        return self


class ExternalDocumentSubmissionProposal(BaseModel):
    """Exact masked release proposal; creation is not authorization or sending."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    proposal_id: StrictStr = Field(min_length=1)
    evaluation_case_id: StrictStr = Field(min_length=1)
    dataset_id: StrictStr = Field(min_length=1)
    contract_id: StrictStr = Field(min_length=1)
    post_decision_update_artifact: ExactDecisionArtifactRef
    post_decision_update_id: StrictStr = Field(min_length=1)
    decision_card_artifact: ExactDecisionArtifactRef
    decision_card_id: StrictStr = Field(min_length=1)
    document_release_package: DecisionDocumentReleaseSnapshot
    recipient: StrictStr = Field(min_length=1)
    purpose: StrictStr = Field(min_length=1)
    document_codes: tuple[StrictStr, ...] = Field(min_length=1)
    document_manifest_item_ids: tuple[StrictStr, ...] = Field(min_length=1)
    masking_manifest_id: StrictStr = Field(min_length=1)
    masking_manifest_item_ids: tuple[StrictStr, ...] = Field(min_length=1)
    approval_condition_codes: tuple[StrictStr, ...] = Field(min_length=1)
    limitation_codes: tuple[StrictStr, ...] = ()
    proposed_action: ProtectedAction = (
        ProtectedAction.SEND_DOCUMENT_TO_EXTERNAL_PARTNER
    )
    source_artifact_ids: tuple[StrictStr, StrictStr, StrictStr]
    evidence_ids: tuple[StrictStr, ...] = Field(min_length=1)
    governance_evaluated: Literal[False] = False
    approval_requested: Literal[False] = False
    release_authorized: Literal[False] = False
    external_submission_performed: Literal[False] = False

    @model_validator(mode="after")
    def validate_proposal(self) -> ExternalDocumentSubmissionProposal:
        if (
            self.post_decision_update_artifact.artifact_type
            is not ArtifactType.POST_DECISION_UPDATE
            or self.decision_card_artifact.artifact_type
            is not ArtifactType.DECISION_CARD
            or self.document_release_package.artifact.artifact_type
            is not ArtifactType.DOCUMENT_RELEASE_PACKAGE
        ):
            raise ValueError("External proposal has incorrect artifact types")
        if self.proposed_action is not ProtectedAction.SEND_DOCUMENT_TO_EXTERNAL_PARTNER:
            raise ValueError("External proposal has the wrong protected action")
        snapshot = self.document_release_package
        if not set(snapshot.evidence_ids).issubset(self.evidence_ids):
            raise ValueError("Release-package evidence is absent from proposal lineage")
        if (
            self.recipient != snapshot.recipient
            or self.purpose != snapshot.purpose
            or self.document_codes != snapshot.document_codes
            or self.masking_manifest_id != snapshot.masking_manifest_id
            or self.limitation_codes != snapshot.limitation_codes
        ):
            raise ValueError("External proposal metadata differs from the approved snapshot")
        expected_sources = (
            self.post_decision_update_artifact.artifact_id,
            self.decision_card_artifact.artifact_id,
            snapshot.artifact.artifact_id,
        )
        if self.source_artifact_ids != expected_sources or len(set(expected_sources)) != 3:
            raise ValueError("External proposal source artifacts are not exact and unique")
        for label, values in (
            ("document_codes", self.document_codes),
            ("document_manifest_item_ids", self.document_manifest_item_ids),
            ("masking_manifest_item_ids", self.masking_manifest_item_ids),
            ("approval_condition_codes", self.approval_condition_codes),
            ("limitation_codes", self.limitation_codes),
            ("evidence_ids", self.evidence_ids),
        ):
            if len(set(values)) != len(values):
                raise ValueError(f"{label} must be unique")
        expected_id = external_document_submission_proposal_id(
            post_decision_update_artifact=self.post_decision_update_artifact,
            post_decision_update_id=self.post_decision_update_id,
            decision_card_artifact=self.decision_card_artifact,
            decision_card_id=self.decision_card_id,
            document_release_package=self.document_release_package,
            document_manifest_item_ids=self.document_manifest_item_ids,
            masking_manifest_item_ids=self.masking_manifest_item_ids,
            approval_condition_codes=self.approval_condition_codes,
            evidence_ids=self.evidence_ids,
        )
        if self.proposal_id != expected_id:
            raise ValueError("External proposal_id is unstable")
        return self


class ReadyForExternalSubmission(BaseModel):
    """Execution-only transition proof; it is deliberately not a receipt."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    readiness_id: StrictStr = Field(min_length=1)
    evaluation_case_id: StrictStr = Field(min_length=1)
    dataset_id: StrictStr = Field(min_length=1)
    contract_id: StrictStr = Field(min_length=1)
    proposal_artifact: ExactDecisionArtifactRef
    proposal_id: StrictStr = Field(min_length=1)
    document_release_package: DecisionDocumentReleaseSnapshot
    authorization: ExternalReleaseAuthorizationReference
    status: ExternalSubmissionReadinessStatus = (
        ExternalSubmissionReadinessStatus.READY_FOR_EXTERNAL_SUBMISSION
    )
    evidence_ids: tuple[StrictStr, ...] = Field(min_length=1)
    adapter_invoked: Literal[False] = False
    submission_receipt_created: Literal[False] = False
    external_submission_performed: Literal[False] = False

    @model_validator(mode="after")
    def validate_readiness(self) -> ReadyForExternalSubmission:
        if (
            self.proposal_artifact.artifact_type
            is not ArtifactType.EXTERNAL_DOCUMENT_SUBMISSION_PROPOSAL
        ):
            raise ValueError("Readiness must bind an external submission proposal")
        authorization = self.authorization
        if authorization.evaluation_case_id != self.evaluation_case_id:
            raise ValueError("External authorization belongs to another case")
        if (
            authorization.subject_artifact_id != self.proposal_artifact.artifact_id
            or authorization.subject_artifact_version != self.proposal_artifact.version
            or authorization.subject_input_hash != self.proposal_artifact.input_hash
        ):
            raise ValueError("External authorization does not bind the exact proposal")
        if len(set(self.evidence_ids)) != len(self.evidence_ids):
            raise ValueError("Readiness evidence_ids must be unique")
        expected_id = ready_for_external_submission_id(
            proposal_artifact=self.proposal_artifact,
            proposal_id=self.proposal_id,
            document_release_package=self.document_release_package,
            authorization=self.authorization,
            evidence_ids=self.evidence_ids,
        )
        if self.readiness_id != expected_id:
            raise ValueError("External submission readiness_id is unstable")
        return self


class PostDecisionUpdateComponentResult(ComponentResult):
    """Side-effect-free post-decision result."""

    update: PostDecisionUpdate | None = None


class ExternalDocumentSubmissionProposalComponentResult(ComponentResult):
    """Side-effect-free proposal result for later Governance evaluation."""

    proposal: ExternalDocumentSubmissionProposal | None = None


class ExternalSubmissionReadinessComponentResult(ComponentResult):
    """No-artifact transition result after exact Governance authorization."""

    readiness: ReadyForExternalSubmission | None = None


class PostDecisionUpdateExecutionResult(BaseModel):
    """Validated post-decision result returned through workflow boundaries."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: WorkflowStatus
    component_status: ComponentStatus
    current_node: StrictStr = Field(min_length=1)
    update: PostDecisionUpdate | None = None
    generated_artifacts: tuple[ArtifactEnvelope, ...] = ()
    validation_reports: tuple[ValidationReport, ...] = ()
    validation_errors: tuple[StrictStr, ...] = ()
    missing_data_requests: tuple[MissingDataRequest, ...] = ()
    warnings: tuple[StrictStr, ...] = ()
    runtime_events: tuple[dict[str, Any], ...] = ()


class ExternalDocumentSubmissionProposalExecutionResult(BaseModel):
    """Validated protected-action proposal returned to workflow orchestration."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: WorkflowStatus
    component_status: ComponentStatus
    current_node: StrictStr = Field(min_length=1)
    proposal: ExternalDocumentSubmissionProposal | None = None
    generated_artifacts: tuple[ArtifactEnvelope, ...] = ()
    validation_reports: tuple[ValidationReport, ...] = ()
    validation_errors: tuple[StrictStr, ...] = ()
    missing_data_requests: tuple[MissingDataRequest, ...] = ()
    warnings: tuple[StrictStr, ...] = ()
    runtime_events: tuple[dict[str, Any], ...] = ()


class ExternalSubmissionReadinessExecutionResult(BaseModel):
    """Execution-only readiness result; no artifact or receipt is fabricated."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: WorkflowStatus
    component_status: ComponentStatus
    current_node: StrictStr = Field(min_length=1)
    readiness: ReadyForExternalSubmission | None = None
    generated_artifacts: tuple[ArtifactEnvelope, ...] = ()
    validation_reports: tuple[ValidationReport, ...] = ()
    validation_errors: tuple[StrictStr, ...] = ()
    missing_data_requests: tuple[MissingDataRequest, ...] = ()
    warnings: tuple[StrictStr, ...] = ()
    runtime_events: tuple[dict[str, Any], ...] = ()


def post_decision_outcome(
    recommendation: DecisionRecommendation,
) -> PostDecisionOutcome:
    """Map every approvable recommendation to one deterministic route."""

    mapping = {
        DecisionRecommendation.ACCEPT: PostDecisionOutcome.FINAL_DECISION_ACCEPTED,
        DecisionRecommendation.NEGOTIATE_CONDITIONS_TO_ACCEPT: (
            PostDecisionOutcome.NEGOTIATION_AUTHORIZED
        ),
        DecisionRecommendation.DO_NOT_ACCEPT: (
            PostDecisionOutcome.CASE_CLOSED_NO_EXTERNAL_ACTION
        ),
    }
    try:
        return mapping[recommendation]
    except KeyError as exc:
        raise ValueError("NOT_EVALUABLE cannot become an approved final decision") from exc


def final_decision_action_payload(card: DecisionCard) -> dict[str, object]:
    """Return the exact JSON-safe scope shown to Founder for approval."""

    release = card.document_release_package
    return {
        "final_decision_confirmation_requested": True,
        "decision_card_id": card.decision_card_id,
        "recommendation": card.recommendation.value,
        "condition_ids": [item.condition_id for item in card.conditions],
        "selected_negotiation_strategy_ids": list(
            card.selected_negotiation_strategy_ids
        ),
        "selected_option_ids": list(card.selected_option_ids),
        "document_release_package": (
            None
            if release is None
            else {
                "artifact_id": release.artifact.artifact_id,
                "version": release.artifact.version,
                "input_hash": release.artifact.input_hash,
                "release_package_id": release.release_package_id,
                "recipient": release.recipient,
                "purpose": release.purpose,
                "document_codes": list(release.document_codes),
                "masking_manifest_id": release.masking_manifest_id,
            }
        ),
    }


def external_document_release_action_payload(
    proposal: ExternalDocumentSubmissionProposal,
) -> dict[str, object]:
    """Return the exact policy scope; this helper never emits an ActionCommand."""

    return {
        "document_sent_to_partner": True,
        "proposal_id": proposal.proposal_id,
        "decision_card_id": proposal.decision_card_id,
        "post_decision_update_id": proposal.post_decision_update_id,
        "release_package_artifact_id": (
            proposal.document_release_package.artifact.artifact_id
        ),
        "release_package_artifact_version": (
            proposal.document_release_package.artifact.version
        ),
        "release_package_input_hash": (
            proposal.document_release_package.artifact.input_hash
        ),
        "release_package_id": proposal.document_release_package.release_package_id,
        "recipient": proposal.recipient,
        "purpose": proposal.purpose,
        "document_codes": list(proposal.document_codes),
        "document_manifest_item_ids": list(proposal.document_manifest_item_ids),
        "masking_manifest_id": proposal.masking_manifest_id,
        "masking_manifest_item_ids": list(proposal.masking_manifest_item_ids),
    }


def approval_reference_from_request(
    request: ApprovalRequest,
    *,
    card: DecisionCard,
) -> FinalDecisionApprovalReference:
    """Validate and copy a persisted Founder approval without runtime mutation."""

    decision = request.decision_record
    expected_payload = final_decision_action_payload(card)
    if (
        request.status is not ApprovalRequestStatus.APPROVED
        or decision is None
        or decision.decision is not ApprovalDecision.APPROVE
        or request.command.action_type
        is not ProtectedAction.CONFIRM_FINAL_CONTRACT_DECISION
        or request.command.evaluation_case_id != request.evaluation_case_id
        or request.command.payload_artifact_id != request.subject_artifact_id
        or request.command.payload != expected_payload
    ):
        raise ValueError("Approval request is not the exact approved Decision Card scope")
    return FinalDecisionApprovalReference(
        approval_request_id=request.request_id,
        workflow_run_id=request.workflow_run_id,
        evaluation_case_id=request.evaluation_case_id,
        subject_artifact_id=request.subject_artifact_id,
        subject_artifact_version=request.subject_artifact_version,
        subject_input_hash=request.subject_input_hash,
        protected_action=request.command.action_type,
        status=request.status,
        decision=decision.decision,
        decided_by=decision.decided_by,
        decision_reason=decision.reason,
        decided_at=decision.decided_at,
        checkpoint_ids=request.checkpoint_ids,
        policy_artifact_id=request.policy_artifact_id,
        policy_artifact_version=request.policy_artifact_version,
        policy_input_hash=request.policy_input_hash,
        policy_coverage_ids=request.policy_coverage_ids,
        action_payload_hash=deterministic_id("FDAP", expected_payload),
    )


def external_authorization_from_request(
    request: ApprovalRequest,
    *,
    proposal: ExternalDocumentSubmissionProposal,
) -> ExternalReleaseAuthorizationReference:
    """Validate and copy exact Founder authorization of a release proposal."""

    decision = request.decision_record
    expected_payload = external_document_release_action_payload(proposal)
    if (
        request.status is not ApprovalRequestStatus.APPROVED
        or decision is None
        or decision.decision is not ApprovalDecision.APPROVE
        or request.command.action_type
        is not ProtectedAction.SEND_DOCUMENT_TO_EXTERNAL_PARTNER
        or request.command.evaluation_case_id != request.evaluation_case_id
        or request.command.payload_artifact_id != request.subject_artifact_id
        or request.command.payload != expected_payload
    ):
        raise ValueError("Approval request is not the exact external release scope")
    return ExternalReleaseAuthorizationReference(
        approval_request_id=request.request_id,
        workflow_run_id=request.workflow_run_id,
        evaluation_case_id=request.evaluation_case_id,
        subject_artifact_id=request.subject_artifact_id,
        subject_artifact_version=request.subject_artifact_version,
        subject_input_hash=request.subject_input_hash,
        protected_action=request.command.action_type,
        status=request.status,
        decision=decision.decision,
        authorized_by=decision.decided_by,
        authorization_reason=decision.reason,
        authorized_at=decision.decided_at,
        checkpoint_ids=request.checkpoint_ids,
        policy_artifact_id=request.policy_artifact_id,
        policy_artifact_version=request.policy_artifact_version,
        policy_input_hash=request.policy_input_hash,
        policy_coverage_ids=request.policy_coverage_ids,
        action_payload_hash=deterministic_id("EDRAP", expected_payload),
    )


def post_decision_update_id(
    *,
    decision_card_artifact: ExactDecisionArtifactRef,
    decision_card_id: str,
    founder_approval: FinalDecisionApprovalReference,
    recommendation: DecisionRecommendation,
    outcome: PostDecisionOutcome,
    approved_condition_ids: tuple[str, ...],
    approved_negotiation_strategy_ids: tuple[str, ...],
    selected_option_ids: tuple[str, ...],
    document_release_package: DecisionDocumentReleaseSnapshot | None,
    evidence_ids: tuple[str, ...],
) -> str:
    """Build identity from business inputs, excluding runtime/request IDs and time."""

    return deterministic_id(
        "PDU",
        decision_card_artifact.model_dump(mode="json"),
        decision_card_id,
        approval_business_identity(founder_approval),
        recommendation,
        outcome,
        approved_condition_ids,
        approved_negotiation_strategy_ids,
        selected_option_ids,
        (
            None
            if document_release_package is None
            else document_release_package.model_dump(mode="json")
        ),
        evidence_ids,
    )


def external_document_submission_proposal_id(
    *,
    post_decision_update_artifact: ExactDecisionArtifactRef,
    post_decision_update_id: str,
    decision_card_artifact: ExactDecisionArtifactRef,
    decision_card_id: str,
    document_release_package: DecisionDocumentReleaseSnapshot,
    document_manifest_item_ids: tuple[str, ...],
    masking_manifest_item_ids: tuple[str, ...],
    approval_condition_codes: tuple[str, ...],
    evidence_ids: tuple[str, ...],
) -> str:
    """Build an exact idempotent protected-action proposal identity."""

    return deterministic_id(
        "EDSP",
        post_decision_update_artifact.model_dump(mode="json"),
        post_decision_update_id,
        decision_card_artifact.model_dump(mode="json"),
        decision_card_id,
        document_release_package.model_dump(mode="json"),
        document_manifest_item_ids,
        masking_manifest_item_ids,
        approval_condition_codes,
        evidence_ids,
    )


def ready_for_external_submission_id(
    *,
    proposal_artifact: ExactDecisionArtifactRef,
    proposal_id: str,
    document_release_package: DecisionDocumentReleaseSnapshot,
    authorization: ExternalReleaseAuthorizationReference,
    evidence_ids: tuple[str, ...],
) -> str:
    """Build a stable readiness identity without claiming an external receipt."""

    return deterministic_id(
        "RFES",
        proposal_artifact.model_dump(mode="json"),
        proposal_id,
        document_release_package.model_dump(mode="json"),
        approval_business_identity(authorization),
        evidence_ids,
    )


def approval_business_identity(
    reference: FinalDecisionApprovalReference | ExternalReleaseAuthorizationReference,
) -> dict[str, Any]:
    """Exclude workflow/request IDs and timestamps from stable artifact identity."""

    payload = reference.model_dump(mode="json")
    for field in (
        "approval_request_id",
        "workflow_run_id",
        "decided_at",
        "authorized_at",
    ):
        payload.pop(field, None)
    return payload


def release_snapshot_from_package(
    *,
    artifact: ExactDecisionArtifactRef,
    package: DocumentReleasePackage,
) -> DecisionDocumentReleaseSnapshot:
    """Create the exact reference-only snapshot used by Card and proposal checks."""

    if artifact.artifact_type is not ArtifactType.DOCUMENT_RELEASE_PACKAGE:
        raise ValueError("Document snapshot requires a release-package artifact")
    return DecisionDocumentReleaseSnapshot(
        artifact=artifact,
        release_package_id=package.release_package_id,
        recipient=package.recipient,
        purpose=package.purpose,
        document_codes=tuple(item.value for item in package.document_codes),
        masking_manifest_id=package.masking_manifest_id,
        limitation_codes=package.limitation_codes,
        evidence_ids=package.evidence_ids,
    )
