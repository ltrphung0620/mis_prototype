"""Post-decision routing and external-release boundary tests."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from opc_mis.business.agents.decision.post_decision_component import (
    ExternalDocumentSubmissionProposalBuilder,
    ExternalDocumentSubmissionProposalComponent,
    ExternalSubmissionReadinessBuilder,
    PostDecisionUpdateBuilder,
    PostDecisionUpdateComponent,
)
from opc_mis.business.agents.decision.post_decision_context import (
    ApprovedDecisionCardContext,
    ExternalReleaseProposalContext,
    ExternalSubmissionReadinessContext,
)
from opc_mis.domain.artifacts import ArtifactEnvelope
from opc_mis.domain.components import ExecutionContext
from opc_mis.domain.decision_models import (
    DecisionCard,
    DecisionConfidence,
    DecisionDocumentReleaseSnapshot,
    DecisionReason,
    DecisionRecommendation,
    ExactDecisionArtifactRef,
    decision_card_id,
)
from opc_mis.domain.document_models import (
    DocumentReleaseManifestItem,
    DocumentReleasePackage,
    DocumentRequirementCode,
)
from opc_mis.domain.enums import (
    ApprovalDecision,
    ApprovalRequestStatus,
    ArtifactStatus,
    ArtifactType,
    ComponentStatus,
    MajorExceptionStatus,
    ProtectedAction,
    RiskLevel,
    SourceType,
    ValidationStatus,
)
from opc_mis.domain.evidence import EvidenceRef
from opc_mis.domain.post_decision_models import (
    ContractExecutionStatus,
    ExternalReleaseAuthorizationReference,
    ExternalSubmissionReadinessStatus,
    FinalDecisionApprovalReference,
    PostDecisionOutcome,
    external_document_release_action_payload,
    final_decision_action_payload,
)

NOW = datetime(2026, 7, 19, 8, 0, tzinfo=UTC)


def _evidence(evidence_id: str) -> EvidenceRef:
    return EvidenceRef(
        evidence_id=evidence_id,
        source_type=SourceType.DERIVED,
        sheet="TEST",
        row_number=0,
        record_id=evidence_id,
        field="value",
        display_value=evidence_id,
    )


def _artifact_ref(
    artifact_id: str,
    artifact_type: ArtifactType,
    *,
    version: int = 1,
    input_hash: str | None = None,
) -> ExactDecisionArtifactRef:
    return ExactDecisionArtifactRef(
        artifact_id=artifact_id,
        artifact_type=artifact_type,
        version=version,
        input_hash=input_hash or f"HASH-{artifact_id}",
    )


def _release_snapshot() -> DecisionDocumentReleaseSnapshot:
    return DecisionDocumentReleaseSnapshot(
        artifact=_artifact_ref("ART-DRP", ArtifactType.DOCUMENT_RELEASE_PACKAGE),
        release_package_id="DRP-1",
        recipient="VIETINBANK",
        purpose="PERFORMANCE_BOND_APPLICATION",
        document_codes=("SIGNED_CONTRACT",),
        masking_manifest_id="MASK-1",
        limitation_codes=(
            "SIGNED_CONTRACT_PENDING_FOUNDER_ACCEPTANCE",
            "NON_BINDING_PROVIDER_RESULT",
        ),
        evidence_ids=("EVD-DRP",),
    )


def _card(
    recommendation: DecisionRecommendation,
    *,
    with_release: bool = False,
) -> DecisionCard:
    reason = DecisionReason(
        reason_id="REASON-1",
        code="EVIDENCE_BOUND_REASON",
        title="Evidence-bound reason",
        detail="The recommendation preserves the validated evidence.",
        source_reference_ids=("REF-1",),
        evidence_ids=("EVD-CARD",),
    )
    payload = {
        "decision_card_id": "TEMP",
        "evaluation_case_id": "CASE-1",
        "dataset_id": "DATASET-1",
        "contract_id": "CON-TEST",
        "ai_analysis_id": "AIDA-1",
        "ai_analysis_artifact": _artifact_ref(
            "ART-AI", ArtifactType.AI_DECISION_ANALYSIS
        ),
        "internal_decision_package_artifact": _artifact_ref(
            "ART-IDP", ArtifactType.INTERNAL_DECISION_PACKAGE
        ),
        "final_risk_artifact": _artifact_ref(
            "ART-FR", ArtifactType.FINAL_RISK_ASSESSMENT
        ),
        "recommendation": recommendation,
        "executive_summary": "Founder-facing summary.",
        "reasons": (reason,),
        "conditions": (),
        "confidence": DecisionConfidence.MEDIUM,
        "selected_option_ids": (),
        "selected_options": (),
        "finance_metrics": (),
        "operations_metrics": (),
        "calculations": (),
        "residual_risk_level": RiskLevel.HIGH,
        "major_exception_status": MajorExceptionStatus.NOT_EVALUABLE,
        "residual_findings": (),
        "required_controls": (),
        "limitations": (),
        "human_attention_points": (),
        "document_release_package": _release_snapshot() if with_release else None,
        "evidence_ids": (
            ("EVD-CARD", "EVD-DRP") if with_release else ("EVD-CARD",)
        ),
    }
    provisional = DecisionCard.model_construct(**payload)
    payload["decision_card_id"] = decision_card_id(provisional)
    return DecisionCard.model_validate(payload)


def _envelope(
    artifact_id: str,
    artifact_type: ArtifactType,
    payload: dict[str, object],
    evidence_ids: tuple[str, ...],
) -> ArtifactEnvelope:
    return ArtifactEnvelope(
        artifact_id=artifact_id,
        artifact_type=artifact_type,
        evaluation_case_id="CASE-1",
        producer="TEST",
        version=1,
        status=ArtifactStatus.CREATED,
        payload=payload,
        evidence_refs=tuple(_evidence(item) for item in evidence_ids),
        input_artifact_ids=(),
        input_hash=f"HASH-{artifact_id}",
        validation_status=ValidationStatus.VALID,
        validation_notes=(),
        created_at=NOW,
    )


def _approval(card_artifact: ArtifactEnvelope) -> FinalDecisionApprovalReference:
    return FinalDecisionApprovalReference(
        approval_request_id="APR-FINAL-1",
        workflow_run_id="RUN-1",
        evaluation_case_id="CASE-1",
        subject_artifact_id=card_artifact.artifact_id,
        subject_artifact_version=card_artifact.version,
        subject_input_hash=card_artifact.input_hash,
        protected_action=ProtectedAction.CONFIRM_FINAL_CONTRACT_DECISION,
        status=ApprovalRequestStatus.APPROVED,
        decision=ApprovalDecision.APPROVE,
        decided_by="FOUNDER-1",
        decision_reason="HUMAN_REVIEW_COMPLETED",
        decided_at=NOW,
        checkpoint_ids=("CHK-FINAL",),
        action_payload_hash="FINAL-PAYLOAD-HASH",
    )


def _approved_context(
    recommendation: DecisionRecommendation,
    *,
    with_release: bool = False,
) -> ApprovedDecisionCardContext:
    card = _card(recommendation, with_release=with_release)
    artifact = _envelope(
        "ART-CARD",
        ArtifactType.DECISION_CARD,
        card.model_dump(mode="json"),
        card.evidence_ids,
    )
    return ApprovedDecisionCardContext(
        card_artifact=artifact,
        card=card,
        approval=_approval(artifact),
    )


@pytest.mark.parametrize(
    ("recommendation", "outcome", "execution_status"),
    (
        (
            DecisionRecommendation.ACCEPT,
            PostDecisionOutcome.FINAL_DECISION_ACCEPTED,
            ContractExecutionStatus.SIGNED,
        ),
        (
            DecisionRecommendation.NEGOTIATE_CONDITIONS_TO_ACCEPT,
            PostDecisionOutcome.NEGOTIATION_AUTHORIZED,
            ContractExecutionStatus.PENDING_NEGOTIATION,
        ),
        (
            DecisionRecommendation.DO_NOT_ACCEPT,
            PostDecisionOutcome.CASE_CLOSED_NO_EXTERNAL_ACTION,
            ContractExecutionStatus.NOT_SIGNED,
        ),
    ),
)
def test_post_decision_routes_approved_recommendations_deterministically(
    recommendation: DecisionRecommendation,
    outcome: PostDecisionOutcome,
    execution_status: ContractExecutionStatus,
) -> None:
    context = _approved_context(
        recommendation,
        with_release=recommendation is DecisionRecommendation.ACCEPT,
    )

    update = PostDecisionUpdateBuilder.build(context)

    assert update.outcome is outcome
    assert update.contract_execution_status is execution_status
    assert update.external_document_release_required is (
        recommendation is DecisionRecommendation.ACCEPT
    )
    assert update.external_action_performed is False


def test_not_evaluable_cannot_become_an_approved_final_decision() -> None:
    context = _approved_context(DecisionRecommendation.NOT_EVALUABLE)

    with pytest.raises(ValueError, match="NOT_EVALUABLE"):
        PostDecisionUpdateBuilder.build(context)


def test_final_decision_scope_contains_exact_card_and_governance_trigger() -> None:
    card = _card(DecisionRecommendation.ACCEPT, with_release=True)

    payload = final_decision_action_payload(card)

    assert payload["final_decision_confirmation_requested"] is True
    assert payload["decision_card_id"] == card.decision_card_id
    assert payload["document_release_package"] == {
        "artifact_id": "ART-DRP",
        "version": 1,
        "input_hash": "HASH-ART-DRP",
        "release_package_id": "DRP-1",
        "recipient": "VIETINBANK",
        "purpose": "PERFORMANCE_BOND_APPLICATION",
        "document_codes": ["SIGNED_CONTRACT"],
        "masking_manifest_id": "MASK-1",
    }


def _release_package() -> DocumentReleasePackage:
    manifest = DocumentReleaseManifestItem.model_construct(
        manifest_item_id="DRMI-1",
        checklist_item_id="DCLI-1",
        document_code=DocumentRequirementCode.SIGNED_CONTRACT,
        status="AVAILABLE",
        limitation_codes=(
            "SIGNED_CONTRACT_PENDING_FOUNDER_ACCEPTANCE",
            "NON_BINDING_PROVIDER_RESULT",
        ),
        source_reference_ids=("DOCREF-1",),
        evidence_ids=("EVD-DRP",),
    )
    return DocumentReleasePackage.model_construct(
        release_package_id="DRP-1",
        package_draft_id="DPD-1",
        evaluation_case_id="CASE-1",
        dataset_id="DATASET-1",
        contract_id="CON-TEST",
        preparation_request_id="DPR-1",
        checklist_id="DCL-1",
        approval_condition_codes=("FOUNDER_APPROVAL",),
        limitation_codes=("NON_BINDING_PROVIDER_RESULT",),
        recipient="VIETINBANK",
        purpose="PERFORMANCE_BOND_APPLICATION",
        document_codes=(DocumentRequirementCode.SIGNED_CONTRACT,),
        document_manifest=(manifest,),
        sanitized_payload={},
        classification_decisions=(),
        masking_manifest=None,
        classification_decision_ids=(),
        masking_manifest_id="MASK-1",
        masking_manifest_item_ids=("MASKI-1",),
        source_artifact_ids=("ART-DRAFT",),
        evidence_ids=("EVD-DRP",),
        release_authorized=False,
        external_release_performed=False,
    )


def _proposal_context() -> ExternalReleaseProposalContext:
    approved = _approved_context(DecisionRecommendation.ACCEPT, with_release=True)
    update = PostDecisionUpdateBuilder.build(approved)
    update_artifact = _envelope(
        "ART-UPDATE",
        ArtifactType.POST_DECISION_UPDATE,
        update.model_dump(mode="json"),
        update.evidence_ids,
    )
    release = _release_package()
    release_artifact = _envelope(
        "ART-DRP",
        ArtifactType.DOCUMENT_RELEASE_PACKAGE,
        {},
        release.evidence_ids,
    )
    return ExternalReleaseProposalContext(
        update_artifact=update_artifact,
        update=update,
        card_artifact=approved.card_artifact,
        card=approved.card,
        release_artifact=release_artifact,
        release_package=release,
    )


def test_external_proposal_is_exact_and_never_authorizes_or_sends() -> None:
    context = _proposal_context()

    proposal = ExternalDocumentSubmissionProposalBuilder.build(context)
    action_payload = external_document_release_action_payload(proposal)

    assert proposal.proposed_action is ProtectedAction.SEND_DOCUMENT_TO_EXTERNAL_PARTNER
    assert proposal.source_artifact_ids == ("ART-UPDATE", "ART-CARD", "ART-DRP")
    assert proposal.governance_evaluated is False
    assert proposal.approval_requested is False
    assert proposal.release_authorized is False
    assert proposal.external_submission_performed is False
    assert proposal.contract_execution_status is ContractExecutionStatus.SIGNED
    assert proposal.signed_contract_completed is True
    assert proposal.resolved_limitation_codes == (
        "SIGNED_CONTRACT_PENDING_FOUNDER_ACCEPTANCE",
    )
    assert proposal.limitation_codes == ("NON_BINDING_PROVIDER_RESULT",)
    assert action_payload["document_sent_to_partner"] is True
    assert action_payload["release_package_input_hash"] == "HASH-ART-DRP"
    assert "sanitized_payload" not in proposal.model_dump(mode="json")


def test_external_proposal_allows_sent_conditional_terms_with_exact_package() -> None:
    approved = _approved_context(
        DecisionRecommendation.NEGOTIATE_CONDITIONS_TO_ACCEPT,
        with_release=True,
    )
    update = PostDecisionUpdateBuilder.build(approved)
    context = _proposal_context()
    negotiated = ExternalReleaseProposalContext(
        update_artifact=_envelope(
            "ART-UPDATE",
            ArtifactType.POST_DECISION_UPDATE,
            update.model_dump(mode="json"),
            update.evidence_ids,
        ),
        update=update,
        card_artifact=approved.card_artifact,
        card=approved.card,
        release_artifact=context.release_artifact,
        release_package=context.release_package,
    )

    proposal = ExternalDocumentSubmissionProposalBuilder.build(negotiated)

    assert update.outcome is PostDecisionOutcome.NEGOTIATION_AUTHORIZED
    assert update.contract_execution_status is ContractExecutionStatus.PENDING_NEGOTIATION
    assert proposal.contract_execution_status is ContractExecutionStatus.SIGNED
    assert proposal.proposed_action is ProtectedAction.SEND_DOCUMENT_TO_EXTERNAL_PARTNER


def test_external_proposal_rejects_non_accept_route() -> None:
    approved = _approved_context(DecisionRecommendation.NEGOTIATE_CONDITIONS_TO_ACCEPT)
    update = PostDecisionUpdateBuilder.build(approved)
    context = _proposal_context()
    invalid = ExternalReleaseProposalContext(
        update_artifact=context.update_artifact,
        update=update,
        card_artifact=approved.card_artifact,
        card=approved.card,
        release_artifact=context.release_artifact,
        release_package=context.release_package,
    )

    with pytest.raises(ValueError, match="exact package"):
        ExternalDocumentSubmissionProposalBuilder.build(invalid)


def test_readiness_requires_exact_authorization_and_creates_no_receipt() -> None:
    proposal_context = _proposal_context()
    proposal = ExternalDocumentSubmissionProposalBuilder.build(proposal_context)
    proposal_artifact = _envelope(
        "ART-EXT-PROP",
        ArtifactType.EXTERNAL_DOCUMENT_SUBMISSION_PROPOSAL,
        proposal.model_dump(mode="json"),
        proposal.evidence_ids,
    )
    authorization = ExternalReleaseAuthorizationReference(
        approval_request_id="APR-RELEASE-1",
        workflow_run_id="RUN-1",
        evaluation_case_id="CASE-1",
        subject_artifact_id=proposal_artifact.artifact_id,
        subject_artifact_version=proposal_artifact.version,
        subject_input_hash=proposal_artifact.input_hash,
        status=ApprovalRequestStatus.APPROVED,
        decision=ApprovalDecision.APPROVE,
        authorized_by="FOUNDER-1",
        authorization_reason="HUMAN_REVIEW_COMPLETED",
        authorized_at=NOW,
        checkpoint_ids=("CHK-RELEASE",),
        action_payload_hash="EXTERNAL-PAYLOAD-HASH",
    )
    context = ExternalSubmissionReadinessContext(
        proposal_artifact=proposal_artifact,
        proposal=proposal,
        authorization=authorization,
    )

    readiness = ExternalSubmissionReadinessBuilder.build(context)

    assert (
        readiness.status
        is ExternalSubmissionReadinessStatus.READY_FOR_EXTERNAL_SUBMISSION
    )
    assert readiness.adapter_invoked is False
    assert readiness.submission_receipt_created is False
    assert readiness.external_submission_performed is False

    tampered = authorization.model_copy(
        update={"subject_input_hash": "DIFFERENT-HASH"}
    )
    with pytest.raises(ValueError, match="exact proposal"):
        ExternalSubmissionReadinessBuilder.build(
            ExternalSubmissionReadinessContext(
                proposal_artifact=proposal_artifact,
                proposal=proposal,
                authorization=tampered,
            )
        )


def test_post_decision_identity_ignores_runtime_request_id_and_timestamp() -> None:
    context = _approved_context(DecisionRecommendation.ACCEPT, with_release=True)
    first = PostDecisionUpdateBuilder.build(context)
    replayed = context.approval.model_copy(
        update={
            "approval_request_id": "APR-FINAL-REPLAY",
            "workflow_run_id": "RUN-REPLAY",
            "decided_at": NOW + timedelta(hours=1),
        }
    )
    second = PostDecisionUpdateBuilder.build(
        ApprovedDecisionCardContext(
            card_artifact=context.card_artifact,
            card=context.card,
            approval=replayed,
        )
    )

    assert second.update_id == first.update_id


def test_business_components_emit_drafts_but_no_governance_commands() -> None:
    approved = _approved_context(DecisionRecommendation.ACCEPT, with_release=True)

    class ApprovedLoader:
        async def load(self, _context: ExecutionContext) -> ApprovedDecisionCardContext:
            return approved

    post_result = asyncio.run(
        PostDecisionUpdateComponent(context_loader=ApprovedLoader()).execute(
            _execution_context(("ART-CARD",), {"approval_request_id": "APR-FINAL-1"})
        )
    )
    assert post_result.status is ComponentStatus.COMPLETED
    assert len(post_result.artifacts) == 1
    assert post_result.approval_signals == ()
    assert post_result.action_commands == ()

    proposal_context = _proposal_context()

    class ProposalLoader:
        async def load(self, _context: ExecutionContext) -> ExternalReleaseProposalContext:
            return proposal_context

    proposal_result = asyncio.run(
        ExternalDocumentSubmissionProposalComponent(
            context_loader=ProposalLoader()
        ).execute(_execution_context(("ART-UPDATE",), {}))
    )
    assert proposal_result.status is ComponentStatus.COMPLETED
    assert len(proposal_result.artifacts) == 1
    assert proposal_result.approval_signals == ()
    assert proposal_result.action_commands == ()


def _execution_context(
    artifact_ids: tuple[str, ...],
    component_input: dict[str, object],
) -> ExecutionContext:
    return ExecutionContext(
        evaluation_case_id="CASE-1",
        dataset_id="DATASET-1",
        workflow_run_id="RUN-1",
        input_artifact_ids=artifact_ids,
        requested_scope=(),
        component_input=component_input,
        current_node="TEST",
    )
