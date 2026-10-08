"""Load exact Decision review and Banking result inputs for Document handoff."""

from dataclasses import dataclass

from pydantic import ValidationError

from opc_mis.domain.artifacts import ArtifactEnvelope
from opc_mis.domain.banking_precheck_execution_models import BankingPrecheckResultSet
from opc_mis.domain.components import ExecutionContext
from opc_mis.domain.decision_post_precheck_models import DecisionPostPrecheckReview
from opc_mis.domain.enums import ArtifactType, ValidationStatus
from opc_mis.ports.artifact_repository import ArtifactRepository

_VALID_STATUSES = {ValidationStatus.VALID, ValidationStatus.VALID_WITH_WARNINGS}


class DecisionDocumentHandoffContextError(RuntimeError):
    """Raised when exact post-precheck lineage cannot be established."""


@dataclass(frozen=True)
class DecisionDocumentHandoffContext:
    """Validated non-binding provider result and its Decision review."""

    review_artifact: ArtifactEnvelope
    result_set_artifact: ArtifactEnvelope
    review: DecisionPostPrecheckReview
    result_set: BankingPrecheckResultSet

    @property
    def source_artifact_ids(self) -> tuple[str, str]:
        """Return stable semantic input order for downstream identity."""
        return (self.review_artifact.artifact_id, self.result_set_artifact.artifact_id)


class DecisionDocumentHandoffContextLoader:
    """Resolve validated artifacts only; never query Excel or fuzzy-match entities."""

    def __init__(self, *, artifacts: ArtifactRepository) -> None:
        self._artifacts = artifacts

    async def load(
        self, context: ExecutionContext
    ) -> DecisionDocumentHandoffContext:
        if context.evaluation_case_id is None:
            raise DecisionDocumentHandoffContextError(
                "Decision Document handoff requires evaluation_case_id."
            )
        if len(context.input_artifact_ids) != 2:
            raise DecisionDocumentHandoffContextError(
                "Decision Document handoff requires exactly one review and its result set."
            )
        loaded: list[ArtifactEnvelope] = []
        for artifact_id in context.input_artifact_ids:
            artifact = await self._artifacts.get(artifact_id)
            if artifact is None:
                raise DecisionDocumentHandoffContextError(
                    f"Decision Document handoff received unknown artifact: {artifact_id}."
                )
            if artifact.validation_status not in _VALID_STATUSES:
                raise DecisionDocumentHandoffContextError(
                    "Decision Document handoff received an unvalidated artifact: "
                    f"{artifact_id}."
                )
            if artifact.evaluation_case_id != context.evaluation_case_id:
                raise DecisionDocumentHandoffContextError(
                    "A Decision Document handoff artifact belongs to another case."
                )
            loaded.append(artifact)

        review_artifact = self._one(
            loaded, ArtifactType.DECISION_POST_PRECHECK_REVIEW
        )
        result_artifact = self._one(
            loaded, ArtifactType.BANKING_PRECHECK_RESULT_SET
        )
        if context.input_artifact_ids != (
            review_artifact.artifact_id,
            result_artifact.artifact_id,
        ):
            raise DecisionDocumentHandoffContextError(
                "Document handoff inputs must preserve review then result-set order."
            )
        try:
            review = DecisionPostPrecheckReview.model_validate(review_artifact.payload)
            result_set = BankingPrecheckResultSet.model_validate(result_artifact.payload)
        except ValidationError as exc:
            raise DecisionDocumentHandoffContextError(
                "Invalid Decision Document handoff input schema."
            ) from exc

        expected_identity = (
            context.evaluation_case_id,
            context.dataset_id,
            review.contract_id,
        )
        if (
            review.evaluation_case_id,
            review.dataset_id,
            review.contract_id,
        ) != expected_identity:
            raise DecisionDocumentHandoffContextError(
                "Decision review identity does not match Document handoff execution."
            )
        if (
            result_set.evaluation_case_id,
            result_set.dataset_id,
            result_set.contract_id,
        ) != expected_identity:
            raise DecisionDocumentHandoffContextError(
                "Banking result identity does not match the Decision review."
            )
        if (
            review.result_set_artifact_id != result_artifact.artifact_id
            or review.result_set_id != result_set.result_set_id
        ):
            raise DecisionDocumentHandoffContextError(
                "Decision review does not bind the exact Banking result envelope."
            )
        result_keys = tuple(
            (
                item.normalized_result_id,
                item.proposal_item_id,
                item.option_id,
                item.bank_product_id,
                item.api_id,
                item.api_provider,
                item.outcome,
            )
            for item in result_set.results
        )
        review_keys = tuple(
            (
                item.normalized_result_id,
                item.proposal_item_id,
                item.option_id,
                item.bank_product_id,
                item.api_id,
                item.api_provider,
                item.source_outcome,
            )
            for item in review.option_reviews
        )
        if result_keys != review_keys:
            raise DecisionDocumentHandoffContextError(
                "Decision option reviews differ from normalized Banking results."
            )
        if review.evidence_ids != tuple(
            item.evidence_id for item in review_artifact.evidence_refs
        ):
            raise DecisionDocumentHandoffContextError(
                "Decision review evidence index differs from its envelope."
            )
        if result_set.evidence_ids != tuple(
            item.evidence_id for item in result_artifact.evidence_refs
        ):
            raise DecisionDocumentHandoffContextError(
                "Banking result evidence index differs from its envelope."
            )
        return DecisionDocumentHandoffContext(
            review_artifact=review_artifact,
            result_set_artifact=result_artifact,
            review=review,
            result_set=result_set,
        )

    @staticmethod
    def _one(
        artifacts: list[ArtifactEnvelope], artifact_type: ArtifactType
    ) -> ArtifactEnvelope:
        matches = tuple(
            item for item in artifacts if item.artifact_type is artifact_type
        )
        if len(matches) != 1:
            raise DecisionDocumentHandoffContextError(
                "Decision Document handoff requires exactly one validated "
                f"{artifact_type.value} artifact."
            )
        return matches[0]
