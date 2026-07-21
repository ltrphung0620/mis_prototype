"""Load exact validated inputs for post-decision and external-release nodes."""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import ValidationError

from opc_mis.domain.artifacts import ArtifactEnvelope
from opc_mis.domain.components import ExecutionContext
from opc_mis.domain.decision_models import DecisionCard, ExactDecisionArtifactRef
from opc_mis.domain.document_models import DocumentReleasePackage
from opc_mis.domain.enums import ArtifactType, ValidationStatus
from opc_mis.domain.post_decision_models import (
    ApprovalResolutionInput,
    ExternalDocumentSubmissionProposal,
    ExternalReleaseAuthorizationReference,
    FinalDecisionApprovalReference,
    PostDecisionUpdate,
    approval_reference_from_request,
    external_authorization_from_request,
    release_snapshot_from_package,
)
from opc_mis.ports.approval_request_repository import ApprovalRequestRepository
from opc_mis.ports.artifact_repository import ArtifactRepository

_VALID_STATUSES = {ValidationStatus.VALID, ValidationStatus.VALID_WITH_WARNINGS}


class PostDecisionContextError(RuntimeError):
    """Raised when exact validated lineage or approval cannot be established."""


@dataclass(frozen=True)
class ApprovedDecisionCardContext:
    """One validated Card and its exact affirmative Founder approval."""

    card_artifact: ArtifactEnvelope
    card: DecisionCard
    approval: FinalDecisionApprovalReference


@dataclass(frozen=True)
class ExternalReleaseProposalContext:
    """Exact accepted update, approved Card, and masked release package."""

    update_artifact: ArtifactEnvelope
    update: PostDecisionUpdate
    card_artifact: ArtifactEnvelope
    card: DecisionCard
    release_artifact: ArtifactEnvelope
    release_package: DocumentReleasePackage


@dataclass(frozen=True)
class ExternalSubmissionReadinessContext:
    """Exact proposal and affirmative Governance authorization."""

    proposal_artifact: ArtifactEnvelope
    proposal: ExternalDocumentSubmissionProposal
    authorization: ExternalReleaseAuthorizationReference


class ApprovedDecisionCardContextLoader:
    """Resolve a validated Card and its exact persisted Founder approval."""

    def __init__(
        self,
        *,
        artifacts: ArtifactRepository,
        approvals: ApprovalRequestRepository,
    ) -> None:
        self._artifacts = artifacts
        self._approvals = approvals

    async def load(self, context: ExecutionContext) -> ApprovedDecisionCardContext:
        request = _approval_input(context)
        card_artifact = await _one_artifact(
            self._artifacts,
            context,
            expected_type=ArtifactType.DECISION_CARD,
        )
        card = _parse_card(card_artifact, context)
        approval_request = await self._approvals.get(request.approval_request_id)
        if approval_request is None:
            raise PostDecisionContextError("Final Decision approval request does not exist.")
        if approval_request.workflow_run_id != context.workflow_run_id:
            raise PostDecisionContextError("Final Decision approval belongs to another run.")
        _require_subject(approval_request, card_artifact)
        try:
            approval = approval_reference_from_request(approval_request, card=card)
        except ValueError as exc:
            raise PostDecisionContextError(str(exc)) from exc
        return ApprovedDecisionCardContext(
            card_artifact=card_artifact,
            card=card,
            approval=approval,
        )


class ExternalReleaseProposalContextLoader:
    """Resolve exact immutable artifacts without issuing a protected command."""

    def __init__(self, *, artifacts: ArtifactRepository) -> None:
        self._artifacts = artifacts

    async def load(self, context: ExecutionContext) -> ExternalReleaseProposalContext:
        update_artifact, card_artifact, release_artifact = (
            await self._explicit_source_artifacts(context)
        )
        try:
            update = PostDecisionUpdate.model_validate(update_artifact.payload)
        except ValidationError as exc:
            raise PostDecisionContextError(
                f"Post-decision update payload is invalid: {exc}"
            ) from exc
        _require_identity(update, context)
        if update.evidence_ids != _evidence_ids(update_artifact):
            raise PostDecisionContextError(
                "Post-decision evidence differs from its persisted envelope."
            )

        self._require_reference(
            card_artifact,
            update.decision_card_artifact,
        )
        card = _parse_card(card_artifact, context)
        if card.decision_card_id != update.decision_card_id:
            raise PostDecisionContextError("Post-decision update references another Card.")
        if card.document_release_package is None:
            if update.external_document_release_required:
                raise PostDecisionContextError(
                    "Accepted Card has no exact external release package."
                )
            raise PostDecisionContextError(
                "No external document release is required for this approved decision."
            )
        snapshot = update.document_release_package
        if snapshot is None or snapshot != card.document_release_package:
            raise PostDecisionContextError(
                "Post-decision update does not preserve the approved package snapshot."
            )
        self._require_reference(release_artifact, snapshot.artifact)
        try:
            release_package = DocumentReleasePackage.model_validate(
                release_artifact.payload
            )
        except ValidationError as exc:
            raise PostDecisionContextError(
                f"Document Release Package payload is invalid: {exc}"
            ) from exc
        if (
            release_package.evaluation_case_id != context.evaluation_case_id
            or release_package.dataset_id != context.dataset_id
            or release_snapshot_from_package(
                artifact=snapshot.artifact,
                package=release_package,
            )
            != snapshot
            or release_package.evidence_ids != _evidence_ids(release_artifact)
        ):
            raise PostDecisionContextError(
                "Document Release Package differs from the approved Card snapshot."
            )
        return ExternalReleaseProposalContext(
            update_artifact=update_artifact,
            update=update,
            card_artifact=card_artifact,
            card=card,
            release_artifact=release_artifact,
            release_package=release_package,
        )

    async def _explicit_source_artifacts(
        self,
        context: ExecutionContext,
    ) -> tuple[ArtifactEnvelope, ArtifactEnvelope, ArtifactEnvelope]:
        if context.evaluation_case_id is None:
            raise PostDecisionContextError("External proposal requires a case ID.")
        if len(context.input_artifact_ids) != 3:
            raise PostDecisionContextError(
                "External proposal requires exact update, Card, and package artifacts."
            )
        loaded: list[ArtifactEnvelope] = []
        for artifact_id in context.input_artifact_ids:
            artifact = await self._artifacts.get(artifact_id)
            if artifact is None:
                raise PostDecisionContextError(
                    f"External proposal source does not exist: {artifact_id}."
                )
            if artifact.validation_status not in _VALID_STATUSES:
                raise PostDecisionContextError(
                    "External proposal source was not validated."
                )
            if artifact.evaluation_case_id != context.evaluation_case_id:
                raise PostDecisionContextError(
                    "External proposal source belongs to another case."
                )
            loaded.append(artifact)
        by_type = {item.artifact_type: item for item in loaded}
        expected = {
            ArtifactType.POST_DECISION_UPDATE,
            ArtifactType.DECISION_CARD,
            ArtifactType.DOCUMENT_RELEASE_PACKAGE,
        }
        if set(by_type) != expected or len(by_type) != len(loaded):
            raise PostDecisionContextError(
                "External proposal sources must contain one update, Card, and package."
            )
        return (
            by_type[ArtifactType.POST_DECISION_UPDATE],
            by_type[ArtifactType.DECISION_CARD],
            by_type[ArtifactType.DOCUMENT_RELEASE_PACKAGE],
        )

    @staticmethod
    def _require_reference(
        artifact: ArtifactEnvelope,
        reference: ExactDecisionArtifactRef,
    ) -> None:
        if artifact.artifact_type is not reference.artifact_type:
            raise PostDecisionContextError("Referenced artifact type has changed.")
        if artifact.version != reference.version or artifact.input_hash != reference.input_hash:
            raise PostDecisionContextError(
                "Referenced artifact version or business input hash has changed."
            )
        if artifact.artifact_id != reference.artifact_id:
            raise PostDecisionContextError("Referenced artifact identity has changed.")


class ExternalSubmissionReadinessContextLoader:
    """Resolve exact release authorization without calling an external adapter."""

    def __init__(
        self,
        *,
        artifacts: ArtifactRepository,
        approvals: ApprovalRequestRepository,
    ) -> None:
        self._artifacts = artifacts
        self._approvals = approvals

    async def load(
        self,
        context: ExecutionContext,
    ) -> ExternalSubmissionReadinessContext:
        request = _approval_input(context)
        proposal_artifact = await _one_artifact(
            self._artifacts,
            context,
            expected_type=ArtifactType.EXTERNAL_DOCUMENT_SUBMISSION_PROPOSAL,
        )
        try:
            proposal = ExternalDocumentSubmissionProposal.model_validate(
                proposal_artifact.payload
            )
        except ValidationError as exc:
            raise PostDecisionContextError(
                f"External submission proposal payload is invalid: {exc}"
            ) from exc
        _require_identity(proposal, context)
        if proposal.evidence_ids != _evidence_ids(proposal_artifact):
            raise PostDecisionContextError(
                "External proposal evidence differs from its persisted envelope."
            )
        approval_request = await self._approvals.get(request.approval_request_id)
        if approval_request is None:
            raise PostDecisionContextError(
                "External release approval request does not exist."
            )
        if approval_request.workflow_run_id != context.workflow_run_id:
            raise PostDecisionContextError(
                "External release approval belongs to another run."
            )
        _require_subject(approval_request, proposal_artifact)
        try:
            authorization = external_authorization_from_request(
                approval_request,
                proposal=proposal,
            )
        except ValueError as exc:
            raise PostDecisionContextError(str(exc)) from exc
        return ExternalSubmissionReadinessContext(
            proposal_artifact=proposal_artifact,
            proposal=proposal,
            authorization=authorization,
        )


def _approval_input(context: ExecutionContext) -> ApprovalResolutionInput:
    try:
        return ApprovalResolutionInput.model_validate(context.component_input)
    except ValidationError as exc:
        raise PostDecisionContextError(
            f"An exact approval_request_id is required: {exc}"
        ) from exc


async def _one_artifact(
    repository: ArtifactRepository,
    context: ExecutionContext,
    *,
    expected_type: ArtifactType,
) -> ArtifactEnvelope:
    if context.evaluation_case_id is None:
        raise PostDecisionContextError("Post-decision execution requires a case ID.")
    if len(context.input_artifact_ids) != 1:
        raise PostDecisionContextError(
            f"{expected_type.value} execution requires exactly one input artifact."
        )
    artifact = await repository.get(context.input_artifact_ids[0])
    if artifact is None:
        raise PostDecisionContextError("Post-decision input artifact does not exist.")
    _require_envelope(artifact, context, expected_type=expected_type)
    return artifact


def _require_envelope(
    artifact: ArtifactEnvelope,
    context: ExecutionContext,
    *,
    expected_type: ArtifactType,
) -> None:
    if artifact.artifact_type is not expected_type:
        raise PostDecisionContextError(
            f"Expected {expected_type.value}, received {artifact.artifact_type.value}."
        )
    if artifact.validation_status not in _VALID_STATUSES:
        raise PostDecisionContextError("Post-decision input was not validated.")
    if artifact.evaluation_case_id != context.evaluation_case_id:
        raise PostDecisionContextError("Post-decision input belongs to another case.")


def _parse_card(
    artifact: ArtifactEnvelope,
    context: ExecutionContext,
) -> DecisionCard:
    try:
        card = DecisionCard.model_validate(artifact.payload)
    except ValidationError as exc:
        raise PostDecisionContextError(f"Decision Card payload is invalid: {exc}") from exc
    _require_identity(card, context)
    if card.evidence_ids != _evidence_ids(artifact):
        raise PostDecisionContextError(
            "Decision Card evidence differs from its persisted envelope."
        )
    if (
        card.document_release_package is not None
        and not set(card.document_release_package.evidence_ids).issubset(
            card.evidence_ids
        )
    ):
        raise PostDecisionContextError(
            "Decision Card package evidence is absent from Card lineage."
        )
    return card


def _require_identity(model: object, context: ExecutionContext) -> None:
    if (
        getattr(model, "evaluation_case_id", None) != context.evaluation_case_id
        or getattr(model, "dataset_id", None) != context.dataset_id
    ):
        raise PostDecisionContextError("Post-decision payload identity does not match.")


def _require_subject(request: object, artifact: ArtifactEnvelope) -> None:
    if (
        getattr(request, "subject_artifact_id", None) != artifact.artifact_id
        or getattr(request, "subject_artifact_version", None) != artifact.version
        or getattr(request, "subject_input_hash", None) != artifact.input_hash
    ):
        raise PostDecisionContextError(
            "Governance decision does not bind the exact subject artifact."
        )


def _evidence_ids(artifact: ArtifactEnvelope) -> tuple[str, ...]:
    return tuple(item.evidence_id for item in artifact.evidence_refs)
