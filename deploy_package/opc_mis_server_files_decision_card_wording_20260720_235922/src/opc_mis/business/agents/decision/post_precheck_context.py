"""Load exact approved proposal and precheck result artifacts for Decision."""

from dataclasses import dataclass

from pydantic import ValidationError

from opc_mis.domain.artifacts import ArtifactEnvelope
from opc_mis.domain.banking_precheck_execution_models import BankingPrecheckResultSet
from opc_mis.domain.banking_precheck_submission_models import (
    BankingPrecheckSubmissionProposal,
)
from opc_mis.domain.components import ExecutionContext
from opc_mis.domain.enums import ArtifactType, ValidationStatus
from opc_mis.ports.artifact_repository import ArtifactRepository


class DecisionPostPrecheckContextError(RuntimeError):
    """Raised when exact post-precheck lineage cannot be established."""


@dataclass(frozen=True)
class DecisionPostPrecheckContext:
    """Validated immutable inputs for deterministic result classification."""

    result_set_artifact: ArtifactEnvelope
    proposal_artifact: ArtifactEnvelope
    result_set: BankingPrecheckResultSet
    proposal: BankingPrecheckSubmissionProposal

    @property
    def source_artifact_ids(self) -> tuple[str, str]:
        return (
            self.result_set_artifact.artifact_id,
            self.proposal_artifact.artifact_id,
        )


class DecisionPostPrecheckContextLoader:
    """Resolve only explicit persisted artifacts; never reread Excel or fuzzy-match."""

    def __init__(self, *, artifacts: ArtifactRepository) -> None:
        self._artifacts = artifacts

    async def load(self, context: ExecutionContext) -> DecisionPostPrecheckContext:
        if context.evaluation_case_id is None:
            raise DecisionPostPrecheckContextError(
                "Decision post-precheck review requires evaluation_case_id."
            )
        if len(context.input_artifact_ids) != 2:
            raise DecisionPostPrecheckContextError(
                "Decision post-precheck review requires exactly one result set and "
                "its approved proposal."
            )
        loaded: list[ArtifactEnvelope] = []
        for artifact_id in context.input_artifact_ids:
            artifact = await self._artifacts.get(artifact_id)
            if artifact is None:
                raise DecisionPostPrecheckContextError(
                    f"Decision post-precheck review received unknown artifact: "
                    f"{artifact_id}."
                )
            if artifact.validation_status not in {
                ValidationStatus.VALID,
                ValidationStatus.VALID_WITH_WARNINGS,
            }:
                raise DecisionPostPrecheckContextError(
                    "Decision post-precheck review received an unvalidated artifact: "
                    f"{artifact_id}."
                )
            if artifact.evaluation_case_id != context.evaluation_case_id:
                raise DecisionPostPrecheckContextError(
                    "A post-precheck input envelope belongs to another case."
                )
            loaded.append(artifact)
        result_artifact = self._one(
            loaded, ArtifactType.BANKING_PRECHECK_RESULT_SET
        )
        proposal_artifact = self._one(
            loaded, ArtifactType.BANKING_PRECHECK_SUBMISSION_PROPOSAL
        )
        if context.input_artifact_ids != (
            result_artifact.artifact_id,
            proposal_artifact.artifact_id,
        ):
            raise DecisionPostPrecheckContextError(
                "Post-precheck inputs must preserve result-set then proposal order."
            )
        try:
            result_set = BankingPrecheckResultSet.model_validate(
                result_artifact.payload
            )
            proposal = BankingPrecheckSubmissionProposal.model_validate(
                proposal_artifact.payload
            )
        except ValidationError as exc:
            raise DecisionPostPrecheckContextError(
                "Invalid Decision post-precheck input schema."
            ) from exc
        expected_identity = (
            context.evaluation_case_id,
            context.dataset_id,
            proposal.contract_id,
        )
        if (
            proposal.evaluation_case_id,
            proposal.dataset_id,
            proposal.contract_id,
        ) != expected_identity:
            raise DecisionPostPrecheckContextError(
                "Approved proposal identity does not match Decision execution."
            )
        if (
            result_set.evaluation_case_id,
            result_set.dataset_id,
            result_set.contract_id,
        ) != expected_identity:
            raise DecisionPostPrecheckContextError(
                "Precheck result identity does not match its approved proposal."
            )
        if (
            result_set.proposal_artifact_id != proposal_artifact.artifact_id
            or result_set.proposal_id != proposal.proposal_id
            or result_set.candidate_option_ids != proposal.candidate_option_ids
        ):
            raise DecisionPostPrecheckContextError(
                "Precheck result does not bind the exact approved proposal."
            )
        proposal_pairs = tuple(
            (
                item.proposal_item_id,
                item.option_id,
                item.bank_product_id,
                item.api_id,
                item.api_provider,
            )
            for item in proposal.candidates
        )
        result_pairs = tuple(
            (
                item.proposal_item_id,
                item.option_id,
                item.bank_product_id,
                item.api_id,
                item.api_provider,
            )
            for item in result_set.results
        )
        if result_pairs != proposal_pairs:
            raise DecisionPostPrecheckContextError(
                "Precheck option/product lineage differs from the approved proposal."
            )
        if (
            not result_set.source_artifact_ids
            or result_set.source_artifact_ids[0] != proposal_artifact.artifact_id
        ):
            raise DecisionPostPrecheckContextError(
                "Precheck result lineage does not start with its approved proposal."
            )
        result_evidence_ids = tuple(
            item.evidence_id for item in result_artifact.evidence_refs
        )
        proposal_evidence_ids = tuple(
            item.evidence_id for item in proposal_artifact.evidence_refs
        )
        if result_set.evidence_ids != result_evidence_ids:
            raise DecisionPostPrecheckContextError(
                "Precheck result evidence index differs from its validated envelope."
            )
        if proposal.evidence_ids != proposal_evidence_ids:
            raise DecisionPostPrecheckContextError(
                "Approved proposal evidence index differs from its validated envelope."
            )
        result_evidence_set = set(result_evidence_ids)
        if any(
            not set(item.evidence_ids).issubset(result_evidence_set)
            for item in result_set.results
        ):
            raise DecisionPostPrecheckContextError(
                "A normalized precheck result references unavailable evidence."
            )
        return DecisionPostPrecheckContext(
            result_set_artifact=result_artifact,
            proposal_artifact=proposal_artifact,
            result_set=result_set,
            proposal=proposal,
        )

    @staticmethod
    def _one(
        artifacts: list[ArtifactEnvelope], artifact_type: ArtifactType
    ) -> ArtifactEnvelope:
        matches = tuple(
            item for item in artifacts if item.artifact_type is artifact_type
        )
        if len(matches) != 1:
            raise DecisionPostPrecheckContextError(
                "Decision post-precheck review requires exactly one validated "
                f"{artifact_type.value} artifact."
            )
        return matches[0]
