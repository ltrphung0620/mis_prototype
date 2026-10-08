"""Persistence and exact-input tests for external submission proposals."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from opc_mis.business.agents.decision.post_decision_component import (
    ExternalDocumentSubmissionProposalComponent,
    ExternalSubmissionReadinessComponent,
    PostDecisionUpdateBuilder,
    PostDecisionUpdateComponent,
)
from opc_mis.business.agents.decision.post_decision_context import (
    ApprovedDecisionCardContext,
    ApprovedDecisionCardContextLoader,
    ExternalReleaseProposalContextLoader,
    ExternalSubmissionReadinessContextLoader,
)
from opc_mis.business.skills.document.checklist_builder import (
    DocumentChecklistBuilder,
)
from opc_mis.business.skills.document.package_builder import DocumentPackageBuilder
from opc_mis.domain.artifacts import ArtifactEnvelope
from opc_mis.domain.components import ExecutionContext
from opc_mis.domain.decision_models import (
    DecisionCard,
    DecisionConfidence,
    DecisionReason,
    DecisionRecommendation,
    ExactDecisionArtifactRef,
    decision_card_id,
)
from opc_mis.domain.enums import (
    ApprovalDecision,
    ApprovalRequestStatus,
    ArtifactStatus,
    ArtifactType,
    MajorExceptionStatus,
    ProtectedAction,
    RiskLevel,
    ValidationStatus,
    WorkflowStatus,
)
from opc_mis.domain.evidence import EvidenceRef
from opc_mis.domain.post_decision_models import (
    FinalDecisionApprovalReference,
    release_snapshot_from_package,
)
from opc_mis.infrastructure.persistence.memory_approval_request_repository import (
    InMemoryApprovalRequestRepository,
)
from opc_mis.infrastructure.persistence.memory_artifact_repository import (
    InMemoryArtifactRepository,
)
from opc_mis.workflow.post_decision_orchestrator import PostDecisionOrchestrator
from tests.unit.test_document_skill_core import (
    REQUIRED_PROFILE_FIELDS,
    _policy,
    _ready_context,
)

NOW = datetime(2026, 7, 19, 9, 0, tzinfo=UTC)


def _artifact_ref(artifact: ArtifactEnvelope) -> ExactDecisionArtifactRef:
    return ExactDecisionArtifactRef(
        artifact_id=artifact.artifact_id,
        artifact_type=artifact.artifact_type,
        version=artifact.version,
        input_hash=artifact.input_hash,
    )


def _envelope(
    *,
    artifact_id: str,
    artifact_type: ArtifactType,
    payload: dict[str, object],
    evidence_refs: tuple[EvidenceRef, ...],
    input_artifact_ids: tuple[str, ...] = (),
) -> ArtifactEnvelope:
    return ArtifactEnvelope(
        artifact_id=artifact_id,
        artifact_type=artifact_type,
        evaluation_case_id="CASE-DOCUMENT-TEST",
        producer="TEST",
        version=1,
        status=ArtifactStatus.CREATED,
        payload=payload,
        evidence_refs=evidence_refs,
        input_artifact_ids=input_artifact_ids,
        input_hash=f"HASH-{artifact_id}",
        validation_status=ValidationStatus.VALID,
        validation_notes=(),
        created_at=NOW,
    )


def test_external_proposal_persists_three_exact_direct_inputs() -> None:
    async def scenario() -> None:
        document_context = _ready_context()
        checklist = DocumentChecklistBuilder(
            required_profile_fields=REQUIRED_PROFILE_FIELDS
        ).build(document_context)
        package_build = DocumentPackageBuilder(
            masking_service=_policy(),
            required_profile_fields=REQUIRED_PROFILE_FIELDS,
        ).build(document_context, checklist)
        release = package_build.release_package
        assert release is not None
        release_artifact = _envelope(
            artifact_id="ART-EXACT-RELEASE",
            artifact_type=ArtifactType.DOCUMENT_RELEASE_PACKAGE,
            payload=release.model_dump(mode="json"),
            evidence_refs=package_build.evidence_refs,
        )
        release_snapshot = release_snapshot_from_package(
            artifact=_artifact_ref(release_artifact),
            package=release,
        )
        evidence_id = release.evidence_ids[0]
        reason = DecisionReason(
            reason_id="DREASON-EXACT-RELEASE",
            code="EXACT_RELEASE_PACKAGE_READY",
            title="The exact masked package is ready",
            detail="The approved route references only the validated masked package.",
            source_reference_ids=(release.release_package_id,),
            evidence_ids=(evidence_id,),
        )
        card_payload: dict[str, object] = {
            "decision_card_id": "PENDING",
            "evaluation_case_id": release.evaluation_case_id,
            "dataset_id": release.dataset_id,
            "contract_id": release.contract_id,
            "ai_analysis_id": "AIDA-EXACT-RELEASE",
            "ai_analysis_artifact": ExactDecisionArtifactRef(
                artifact_id="ART-AI-EXACT-RELEASE",
                artifact_type=ArtifactType.AI_DECISION_ANALYSIS,
                version=1,
                input_hash="HASH-AI-EXACT-RELEASE",
            ),
            "internal_decision_package_artifact": ExactDecisionArtifactRef(
                artifact_id="ART-IDP-EXACT-RELEASE",
                artifact_type=ArtifactType.INTERNAL_DECISION_PACKAGE,
                version=1,
                input_hash="HASH-IDP-EXACT-RELEASE",
            ),
            "final_risk_artifact": ExactDecisionArtifactRef(
                artifact_id="ART-FR-EXACT-RELEASE",
                artifact_type=ArtifactType.FINAL_RISK_ASSESSMENT,
                version=1,
                input_hash="HASH-FR-EXACT-RELEASE",
            ),
            "recommendation": DecisionRecommendation.ACCEPT,
            "executive_summary": "Accept with the exact governed package route.",
            "reasons": (reason,),
            "conditions": (),
            "confidence": DecisionConfidence.MEDIUM,
            "selected_option_ids": (),
            "selected_options": (),
            "finance_metrics": (),
            "operations_metrics": (),
            "calculations": (),
            "residual_risk_level": RiskLevel.LOW,
            "major_exception_status": MajorExceptionStatus.NOT_DETECTED,
            "residual_findings": (),
            "required_controls": (),
            "limitations": (),
            "human_attention_points": (),
            "document_release_package": release_snapshot,
            "evidence_ids": release.evidence_ids,
        }
        provisional = DecisionCard.model_construct(**card_payload)
        card_payload["decision_card_id"] = decision_card_id(provisional)
        card = DecisionCard.model_validate(card_payload)
        card_artifact = _envelope(
            artifact_id="ART-CARD-EXACT-RELEASE",
            artifact_type=ArtifactType.DECISION_CARD,
            payload=card.model_dump(mode="json"),
            evidence_refs=package_build.evidence_refs,
            input_artifact_ids=("ART-AI-EXACT-RELEASE",),
        )
        approval = FinalDecisionApprovalReference(
            approval_request_id="APR-FINAL-EXACT-RELEASE",
            workflow_run_id="RUN-EXACT-RELEASE",
            evaluation_case_id=release.evaluation_case_id,
            subject_artifact_id=card_artifact.artifact_id,
            subject_artifact_version=card_artifact.version,
            subject_input_hash=card_artifact.input_hash,
            protected_action=ProtectedAction.CONFIRM_FINAL_CONTRACT_DECISION,
            status=ApprovalRequestStatus.APPROVED,
            decision=ApprovalDecision.APPROVE,
            decided_by="FOUNDER",
            decision_reason="HUMAN_REVIEW_COMPLETED",
            decided_at=NOW,
            checkpoint_ids=("ACP-FINAL-EXACT-RELEASE",),
            action_payload_hash="HASH-FINAL-ACTION",
        )
        update = PostDecisionUpdateBuilder.build(
            ApprovedDecisionCardContext(
                card_artifact=card_artifact,
                card=card,
                approval=approval,
            )
        )
        update_artifact = _envelope(
            artifact_id="ART-UPDATE-EXACT-RELEASE",
            artifact_type=ArtifactType.POST_DECISION_UPDATE,
            payload=update.model_dump(mode="json"),
            evidence_refs=package_build.evidence_refs,
            input_artifact_ids=(card_artifact.artifact_id,),
        )

        artifacts = InMemoryArtifactRepository()
        for artifact in (release_artifact, card_artifact, update_artifact):
            await artifacts.save(artifact)
        approvals = InMemoryApprovalRequestRepository()
        orchestrator = PostDecisionOrchestrator(
            update_component=PostDecisionUpdateComponent(
                context_loader=ApprovedDecisionCardContextLoader(
                    artifacts=artifacts,
                    approvals=approvals,
                )
            ),
            proposal_component=ExternalDocumentSubmissionProposalComponent(
                context_loader=ExternalReleaseProposalContextLoader(
                    artifacts=artifacts
                )
            ),
            readiness_component=ExternalSubmissionReadinessComponent(
                context_loader=ExternalSubmissionReadinessContextLoader(
                    artifacts=artifacts,
                    approvals=approvals,
                )
            ),
            artifacts=artifacts,
        )
        direct_inputs = (
            update_artifact.artifact_id,
            card_artifact.artifact_id,
            release_artifact.artifact_id,
        )
        context = ExecutionContext(
            evaluation_case_id=release.evaluation_case_id,
            dataset_id=release.dataset_id,
            workflow_run_id="RUN-EXACT-RELEASE",
            input_artifact_ids=direct_inputs,
            requested_scope=(),
            current_node="EXTERNAL_DOCUMENT_SUBMISSION_PROPOSAL",
        )

        result = await orchestrator.run_external_proposal(context)

        assert result.status is WorkflowStatus.COMPLETED
        assert result.proposal is not None
        assert result.proposal.source_artifact_ids == direct_inputs
        assert len(result.generated_artifacts) == 1
        assert result.generated_artifacts[0].input_artifact_ids == direct_inputs

        invalid = await orchestrator.run_external_proposal(
            context.model_copy(
                update={"input_artifact_ids": (update_artifact.artifact_id,)}
            )
        )
        assert invalid.status is WorkflowStatus.FAILED_SAFE
        assert invalid.generated_artifacts == ()

    asyncio.run(scenario())
