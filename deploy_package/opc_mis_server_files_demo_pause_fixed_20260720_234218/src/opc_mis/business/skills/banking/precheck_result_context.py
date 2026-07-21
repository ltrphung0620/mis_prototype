"""Load exact authorized proposal lineage for Banking precheck result normalization."""

from dataclasses import dataclass

from pydantic import ValidationError

from opc_mis.domain.artifacts import ArtifactEnvelope
from opc_mis.domain.banking_precheck_submission_models import (
    BankingPrecheckSubmissionProposal,
)
from opc_mis.domain.components import ExecutionContext
from opc_mis.domain.enums import ArtifactType, ValidationStatus
from opc_mis.ports.artifact_repository import ArtifactRepository

_VALID_STATUSES = {ValidationStatus.VALID, ValidationStatus.VALID_WITH_WARNINGS}


class BankingPrecheckResultContextError(RuntimeError):
    """Raised when Phase B1 receives incomplete or stale proposal lineage."""


@dataclass(frozen=True)
class BankingPrecheckResultContext:
    """Validated proposal envelope and every explicitly declared upstream artifact."""

    proposal_artifact: ArtifactEnvelope
    upstream_artifacts: tuple[ArtifactEnvelope, ...]
    proposal: BankingPrecheckSubmissionProposal

    @property
    def source_artifacts(self) -> tuple[ArtifactEnvelope, ...]:
        return (self.proposal_artifact, *self.upstream_artifacts)

    @property
    def source_artifact_ids(self) -> tuple[str, ...]:
        return tuple(item.artifact_id for item in self.source_artifacts)


class BankingPrecheckResultContextLoader:
    """Resolve one validated proposal plus its exact declared artifact dependencies."""

    def __init__(self, *, artifacts: ArtifactRepository) -> None:
        self._artifacts = artifacts

    async def load(self, context: ExecutionContext) -> BankingPrecheckResultContext:
        if context.evaluation_case_id is None:
            raise BankingPrecheckResultContextError(
                "Banking precheck result requires evaluation_case_id."
            )
        if len(set(context.input_artifact_ids)) != len(context.input_artifact_ids):
            raise BankingPrecheckResultContextError(
                "Banking precheck result rejects duplicate artifact IDs."
            )
        supplied_items: list[ArtifactEnvelope] = []
        for artifact_id in context.input_artifact_ids:
            artifact = await self._artifacts.get(artifact_id)
            if artifact is None:
                raise BankingPrecheckResultContextError(
                    f"Banking precheck result received unknown artifact: {artifact_id}."
                )
            if artifact.validation_status not in _VALID_STATUSES:
                raise BankingPrecheckResultContextError(
                    "Banking precheck result received an unvalidated artifact: "
                    f"{artifact_id}."
                )
            supplied_items.append(artifact)
        supplied = tuple(supplied_items)
        proposal_matches = tuple(
            item
            for item in supplied
            if item.artifact_type
            is ArtifactType.BANKING_PRECHECK_SUBMISSION_PROPOSAL
        )
        if len(proposal_matches) != 1:
            raise BankingPrecheckResultContextError(
                "Banking precheck result requires exactly one validated "
                "BANKING_PRECHECK_SUBMISSION_PROPOSAL artifact."
            )
        proposal_artifact = proposal_matches[0]
        try:
            proposal = BankingPrecheckSubmissionProposal.model_validate(
                proposal_artifact.payload
            )
        except ValidationError as exc:
            raise BankingPrecheckResultContextError(
                f"Invalid Banking precheck proposal schema: {exc}"
            ) from exc
        expected_input_ids = (
            proposal_artifact.artifact_id,
            *proposal.source_artifact_ids,
        )
        if context.input_artifact_ids != expected_input_ids:
            raise BankingPrecheckResultContextError(
                "Banking precheck result artifacts must exactly match proposal-first "
                "declared lineage order."
            )
        if proposal_artifact.artifact_id in proposal.source_artifact_ids:
            raise BankingPrecheckResultContextError(
                "Banking precheck proposal cannot reference its own envelope."
            )
        if (
            proposal.evaluation_case_id != context.evaluation_case_id
            or proposal.dataset_id != context.dataset_id
        ):
            raise BankingPrecheckResultContextError(
                "Banking precheck proposal identity does not match execution."
            )
        if any(
            item.evaluation_case_id != context.evaluation_case_id
            for item in supplied
        ):
            raise BankingPrecheckResultContextError(
                "A Banking precheck result input belongs to another case."
            )
        available_evidence = {
            item.evidence_id for item in proposal_artifact.evidence_refs
        }
        if set(proposal.evidence_ids) != available_evidence:
            raise BankingPrecheckResultContextError(
                "Banking precheck proposal evidence index is not exact."
            )
        return BankingPrecheckResultContext(
            proposal_artifact=proposal_artifact,
            upstream_artifacts=supplied[1:],
            proposal=proposal,
        )
