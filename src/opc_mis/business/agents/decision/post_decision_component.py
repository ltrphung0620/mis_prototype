"""Side-effect-free post-decision routing and external-release components."""

from __future__ import annotations

from pydantic import ValidationError

from opc_mis.business.agents.decision.post_decision_context import (
    ApprovedDecisionCardContext,
    ApprovedDecisionCardContextLoader,
    ExternalReleaseProposalContext,
    ExternalReleaseProposalContextLoader,
    ExternalSubmissionReadinessContext,
    ExternalSubmissionReadinessContextLoader,
    PostDecisionContextError,
)
from opc_mis.domain.artifacts import ArtifactDraft, ArtifactEnvelope
from opc_mis.domain.components import ExecutionContext
from opc_mis.domain.decision_models import DecisionRecommendation, ExactDecisionArtifactRef
from opc_mis.domain.enums import ArtifactType, ComponentStatus
from opc_mis.domain.events import RuntimeEvent
from opc_mis.domain.evidence import EvidenceRef
from opc_mis.domain.post_decision_models import (
    SIGNED_CONTRACT_PENDING_FOUNDER_ACCEPTANCE,
    ExternalDocumentSubmissionProposal,
    ExternalDocumentSubmissionProposalComponentResult,
    ExternalSubmissionReadinessComponentResult,
    PostDecisionOutcome,
    PostDecisionUpdate,
    PostDecisionUpdateComponentResult,
    ReadyForExternalSubmission,
    approval_business_identity,
    contract_execution_status,
    external_document_submission_proposal_id,
    post_decision_outcome,
    post_decision_update_id,
    ready_for_external_submission_id,
)


class PostDecisionUpdateBuilder:
    """Build one deterministic route from an approved exact Decision Card."""

    @staticmethod
    def build(context: ApprovedDecisionCardContext) -> PostDecisionUpdate:
        card = context.card
        card_artifact = _artifact_ref(context.card_artifact)
        outcome = post_decision_outcome(card.recommendation)
        execution_status = contract_execution_status(card.recommendation)
        condition_ids = tuple(item.condition_id for item in card.conditions)
        evidence_ids = card.evidence_ids
        update_id = post_decision_update_id(
            decision_card_artifact=card_artifact,
            decision_card_id=card.decision_card_id,
            founder_approval=context.approval,
            recommendation=card.recommendation,
            outcome=outcome,
            contract_execution_status=execution_status,
            approved_condition_ids=condition_ids,
            approved_negotiation_strategy_ids=(card.selected_negotiation_strategy_ids),
            selected_option_ids=card.selected_option_ids,
            document_release_package=card.document_release_package,
            evidence_ids=evidence_ids,
        )
        return PostDecisionUpdate(
            update_id=update_id,
            evaluation_case_id=card.evaluation_case_id,
            dataset_id=card.dataset_id,
            contract_id=card.contract_id,
            decision_card_artifact=card_artifact,
            decision_card_id=card.decision_card_id,
            founder_approval=context.approval,
            recommendation=card.recommendation,
            outcome=outcome,
            contract_execution_status=execution_status,
            approved_condition_ids=condition_ids,
            approved_negotiation_strategy_ids=(card.selected_negotiation_strategy_ids),
            selected_option_ids=card.selected_option_ids,
            document_release_package=card.document_release_package,
            external_document_release_required=(
                card.recommendation is DecisionRecommendation.ACCEPT
                and card.document_release_package is not None
            ),
            evidence_ids=evidence_ids,
        )


class ExternalDocumentSubmissionProposalBuilder:
    """Build an exact Governance subject without requesting or executing release."""

    @staticmethod
    def build(
        context: ExternalReleaseProposalContext,
    ) -> ExternalDocumentSubmissionProposal:
        update = context.update
        card = context.card
        package = context.release_package
        snapshot = update.document_release_package
        if (
            update.outcome is not PostDecisionOutcome.FINAL_DECISION_ACCEPTED
            or update.recommendation is not DecisionRecommendation.ACCEPT
            or not update.external_document_release_required
            or snapshot is None
        ):
            raise ValueError(
                "Only an approved ACCEPT route with an exact package may propose release"
            )
        if (
            card.decision_card_id != update.decision_card_id
            or card.document_release_package != snapshot
        ):
            raise ValueError("External release does not bind the approved Decision Card")
        if update.contract_execution_status.value != "SIGNED":
            raise ValueError("External release requires a signed contract disposition")
        if "SIGNED_CONTRACT" not in {item.value for item in package.document_codes}:
            raise ValueError("External release package lacks SIGNED_CONTRACT")
        resolved_limitations = tuple(
            item
            for item in snapshot.limitation_codes
            if item == SIGNED_CONTRACT_PENDING_FOUNDER_ACCEPTANCE
        )
        effective_limitations = tuple(
            item
            for item in snapshot.limitation_codes
            if item not in set(resolved_limitations)
        )
        update_ref = _artifact_ref(context.update_artifact)
        card_ref = _artifact_ref(context.card_artifact)
        evidence_refs = _evidence_union(
            context.update_artifact,
            context.card_artifact,
            context.release_artifact,
        )
        evidence_ids = tuple(item.evidence_id for item in evidence_refs)
        manifest_ids = tuple(item.manifest_item_id for item in package.document_manifest)
        proposal_id = external_document_submission_proposal_id(
            post_decision_update_artifact=update_ref,
            post_decision_update_id=update.update_id,
            decision_card_artifact=card_ref,
            decision_card_id=card.decision_card_id,
            document_release_package=snapshot,
            document_manifest_item_ids=manifest_ids,
            masking_manifest_item_ids=package.masking_manifest_item_ids,
            approval_condition_codes=package.approval_condition_codes,
            contract_execution_status=update.contract_execution_status,
            resolved_limitation_codes=resolved_limitations,
            evidence_ids=evidence_ids,
        )
        return ExternalDocumentSubmissionProposal(
            proposal_id=proposal_id,
            evaluation_case_id=update.evaluation_case_id,
            dataset_id=update.dataset_id,
            contract_id=update.contract_id,
            post_decision_update_artifact=update_ref,
            post_decision_update_id=update.update_id,
            decision_card_artifact=card_ref,
            decision_card_id=card.decision_card_id,
            contract_execution_status=update.contract_execution_status,
            signed_contract_completed=True,
            resolved_limitation_codes=resolved_limitations,
            document_release_package=snapshot,
            recipient=package.recipient,
            purpose=package.purpose,
            document_codes=tuple(item.value for item in package.document_codes),
            document_manifest_item_ids=manifest_ids,
            masking_manifest_id=package.masking_manifest_id,
            masking_manifest_item_ids=package.masking_manifest_item_ids,
            approval_condition_codes=package.approval_condition_codes,
            limitation_codes=effective_limitations,
            source_artifact_ids=(
                context.update_artifact.artifact_id,
                context.card_artifact.artifact_id,
                context.release_artifact.artifact_id,
            ),
            evidence_ids=evidence_ids,
        )


class ExternalSubmissionReadinessBuilder:
    """Build an execution transition proof without invoking the connector."""

    @staticmethod
    def build(
        context: ExternalSubmissionReadinessContext,
    ) -> ReadyForExternalSubmission:
        proposal = context.proposal
        proposal_ref = _artifact_ref(context.proposal_artifact)
        readiness_id = ready_for_external_submission_id(
            proposal_artifact=proposal_ref,
            proposal_id=proposal.proposal_id,
            document_release_package=proposal.document_release_package,
            authorization=context.authorization,
            evidence_ids=proposal.evidence_ids,
        )
        return ReadyForExternalSubmission(
            readiness_id=readiness_id,
            evaluation_case_id=proposal.evaluation_case_id,
            dataset_id=proposal.dataset_id,
            contract_id=proposal.contract_id,
            proposal_artifact=proposal_ref,
            proposal_id=proposal.proposal_id,
            document_release_package=proposal.document_release_package,
            authorization=context.authorization,
            evidence_ids=proposal.evidence_ids,
        )


class PostDecisionUpdateComponent:
    """Create a post-decision draft; never persist or change workflow state."""

    component_id = "POST_DECISION_UPDATE"

    def __init__(self, *, context_loader: ApprovedDecisionCardContextLoader) -> None:
        self._context_loader = context_loader

    async def execute(self, context: ExecutionContext) -> PostDecisionUpdateComponentResult:
        try:
            loaded = await self._context_loader.load(context)
            update = PostDecisionUpdateBuilder.build(loaded)
        except (PostDecisionContextError, ValidationError, ValueError) as exc:
            return self._failed_safe(str(exc))
        draft = ArtifactDraft(
            artifact_type=ArtifactType.POST_DECISION_UPDATE,
            evaluation_case_id=update.evaluation_case_id,
            producer=self.component_id,
            payload=update.model_dump(mode="json"),
            evidence_refs=loaded.card_artifact.evidence_refs,
            identity_inputs={
                "decision_card_artifact": update.decision_card_artifact.model_dump(mode="json"),
                "decision_card_id": update.decision_card_id,
                "founder_approval": approval_business_identity(update.founder_approval),
                "recommendation": update.recommendation,
                "outcome": update.outcome,
                "contract_execution_status": update.contract_execution_status,
                "approved_condition_ids": update.approved_condition_ids,
                "approved_negotiation_strategy_ids": (update.approved_negotiation_strategy_ids),
                "selected_option_ids": update.selected_option_ids,
                "document_release_package": (
                    None
                    if update.document_release_package is None
                    else update.document_release_package.model_dump(mode="json")
                ),
            },
        )
        return PostDecisionUpdateComponentResult(
            status=ComponentStatus.COMPLETED,
            update=update,
            artifacts=(draft,),
            runtime_events=(
                RuntimeEvent(
                    event_type="POST_DECISION_UPDATE_CREATED",
                    message=(
                        "The exact Founder-approved Decision Card was routed without "
                        "executing a protected action."
                    ),
                    metadata={
                        "outcome": update.outcome.value,
                        "contract_execution_status": (update.contract_execution_status.value),
                        "external_document_release_required": (
                            update.external_document_release_required
                        ),
                    },
                ),
            ),
        )

    @staticmethod
    def _failed_safe(message: str) -> PostDecisionUpdateComponentResult:
        return PostDecisionUpdateComponentResult(
            status=ComponentStatus.FAILED_SAFE,
            runtime_events=(
                RuntimeEvent(
                    event_type="POST_DECISION_UPDATE_FAILED_SAFE",
                    message=message,
                ),
            ),
        )


class ExternalDocumentSubmissionProposalComponent:
    """Create a release proposal; Governance owns any ActionCommand or approval."""

    component_id = "EXTERNAL_DOCUMENT_SUBMISSION_PROPOSAL"

    def __init__(self, *, context_loader: ExternalReleaseProposalContextLoader) -> None:
        self._context_loader = context_loader

    async def execute(
        self,
        context: ExecutionContext,
    ) -> ExternalDocumentSubmissionProposalComponentResult:
        try:
            loaded = await self._context_loader.load(context)
            proposal = ExternalDocumentSubmissionProposalBuilder.build(loaded)
        except (PostDecisionContextError, ValidationError, ValueError) as exc:
            return self._failed_safe(str(exc))
        evidence_refs = _evidence_union(
            loaded.update_artifact,
            loaded.card_artifact,
            loaded.release_artifact,
        )
        draft = ArtifactDraft(
            artifact_type=ArtifactType.EXTERNAL_DOCUMENT_SUBMISSION_PROPOSAL,
            evaluation_case_id=proposal.evaluation_case_id,
            producer=self.component_id,
            payload=proposal.model_dump(mode="json"),
            evidence_refs=evidence_refs,
            identity_inputs={
                "post_decision_update_artifact": (
                    proposal.post_decision_update_artifact.model_dump(mode="json")
                ),
                "post_decision_update_id": proposal.post_decision_update_id,
                "decision_card_artifact": proposal.decision_card_artifact.model_dump(mode="json"),
                "decision_card_id": proposal.decision_card_id,
                "document_release_package": (
                    proposal.document_release_package.model_dump(mode="json")
                ),
                "document_manifest_item_ids": proposal.document_manifest_item_ids,
                "masking_manifest_item_ids": proposal.masking_manifest_item_ids,
                "approval_condition_codes": proposal.approval_condition_codes,
                "contract_execution_status": proposal.contract_execution_status,
                "resolved_limitation_codes": proposal.resolved_limitation_codes,
            },
        )
        return ExternalDocumentSubmissionProposalComponentResult(
            status=ComponentStatus.COMPLETED,
            proposal=proposal,
            artifacts=(draft,),
            runtime_events=(
                RuntimeEvent(
                    event_type="EXTERNAL_DOCUMENT_SUBMISSION_PROPOSAL_CREATED",
                    message=(
                        "An exact masked-package proposal was created for later "
                        "Governance evaluation; no document was sent."
                    ),
                    metadata={
                        "recipient": proposal.recipient,
                        "document_count": len(proposal.document_codes),
                        "signed_contract_completed": (proposal.signed_contract_completed),
                    },
                ),
            ),
        )

    @staticmethod
    def _failed_safe(
        message: str,
    ) -> ExternalDocumentSubmissionProposalComponentResult:
        return ExternalDocumentSubmissionProposalComponentResult(
            status=ComponentStatus.FAILED_SAFE,
            runtime_events=(
                RuntimeEvent(
                    event_type="EXTERNAL_DOCUMENT_SUBMISSION_PROPOSAL_FAILED_SAFE",
                    message=message,
                ),
            ),
        )


class ExternalSubmissionReadinessComponent:
    """Return READY only after exact approval; never call an external adapter."""

    component_id = "EXTERNAL_SUBMISSION_READINESS"

    def __init__(
        self,
        *,
        context_loader: ExternalSubmissionReadinessContextLoader,
    ) -> None:
        self._context_loader = context_loader

    async def execute(
        self,
        context: ExecutionContext,
    ) -> ExternalSubmissionReadinessComponentResult:
        try:
            loaded = await self._context_loader.load(context)
            readiness = ExternalSubmissionReadinessBuilder.build(loaded)
        except (PostDecisionContextError, ValidationError, ValueError) as exc:
            return ExternalSubmissionReadinessComponentResult(
                status=ComponentStatus.FAILED_SAFE,
                runtime_events=(
                    RuntimeEvent(
                        event_type="EXTERNAL_SUBMISSION_READINESS_FAILED_SAFE",
                        message=str(exc),
                    ),
                ),
            )
        return ExternalSubmissionReadinessComponentResult(
            status=ComponentStatus.COMPLETED,
            readiness=readiness,
            runtime_events=(
                RuntimeEvent(
                    event_type="READY_FOR_EXTERNAL_SUBMISSION",
                    message=(
                        "The exact masked package is authorized and ready for a "
                        "future connector; no adapter call or receipt was created."
                    ),
                    metadata={
                        "proposal_id": readiness.proposal_id,
                        "recipient": readiness.document_release_package.recipient,
                    },
                ),
            ),
        )


def _artifact_ref(artifact: ArtifactEnvelope) -> ExactDecisionArtifactRef:
    return ExactDecisionArtifactRef(
        artifact_id=artifact.artifact_id,
        artifact_type=artifact.artifact_type,
        version=artifact.version,
        input_hash=artifact.input_hash,
    )


def _evidence_union(*artifacts: ArtifactEnvelope) -> tuple[EvidenceRef, ...]:
    seen: set[str] = set()
    evidence: list[EvidenceRef] = []
    for artifact in artifacts:
        for item in artifact.evidence_refs:
            if item.evidence_id in seen:
                continue
            seen.add(item.evidence_id)
            evidence.append(item)
    return tuple(evidence)
