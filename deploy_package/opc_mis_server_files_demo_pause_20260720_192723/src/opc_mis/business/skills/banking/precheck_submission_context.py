"""Load exact artifacts for a side-effect-free Banking submission proposal."""

from dataclasses import dataclass

from pydantic import ValidationError

from opc_mis.domain.artifacts import ArtifactEnvelope
from opc_mis.domain.banking_models import (
    BankingOptionMatrix,
    BankingPrecheckReadiness,
)
from opc_mis.domain.components import ExecutionContext
from opc_mis.domain.decision_post_banking_models import DecisionPostBankingReview
from opc_mis.domain.enums import (
    ArtifactType,
    BankingCriterionStatus,
    BankingPrecheckFieldStatus,
    BankingPrecheckReadinessStatus,
    DecisionPostBankingOutcome,
    ValidationStatus,
)
from opc_mis.ports.artifact_repository import ArtifactRepository

_VALID_STATUSES = {ValidationStatus.VALID, ValidationStatus.VALID_WITH_WARNINGS}


class BankingPrecheckSubmissionProposalContextError(RuntimeError):
    """Raised when a proposal receives incomplete, stale, or inconsistent lineage."""


@dataclass(frozen=True)
class BankingPrecheckSubmissionProposalContext:
    """Validated proposal inputs in stable semantic order."""

    matrix_artifact: ArtifactEnvelope
    readiness_artifact: ArtifactEnvelope
    review_artifact: ArtifactEnvelope
    upstream_artifacts: tuple[ArtifactEnvelope, ...]
    matrix: BankingOptionMatrix
    readiness: BankingPrecheckReadiness
    review: DecisionPostBankingReview

    @property
    def source_artifacts(self) -> tuple[ArtifactEnvelope, ...]:
        """Return all exact proposal dependencies in stable identity order."""
        return (
            self.matrix_artifact,
            self.readiness_artifact,
            self.review_artifact,
            *self.upstream_artifacts,
        )

    @property
    def source_artifact_ids(self) -> tuple[str, ...]:
        """Return IDs matching ``source_artifacts`` exactly."""
        return tuple(item.artifact_id for item in self.source_artifacts)


class BankingPrecheckSubmissionProposalContextLoader:
    """Resolve all declared lineage without inspecting datasets or external systems."""

    def __init__(self, *, artifacts: ArtifactRepository) -> None:
        self._artifacts = artifacts

    async def load(
        self,
        context: ExecutionContext,
    ) -> BankingPrecheckSubmissionProposalContext:
        """Load one matrix, readiness and Decision review plus exact upstreams."""
        if context.evaluation_case_id is None:
            raise BankingPrecheckSubmissionProposalContextError(
                "Banking precheck submission proposal requires evaluation_case_id."
            )
        if len(set(context.input_artifact_ids)) != len(context.input_artifact_ids):
            raise BankingPrecheckSubmissionProposalContextError(
                "Banking precheck submission proposal rejects duplicate artifact IDs."
            )

        supplied_items: list[ArtifactEnvelope] = []
        for artifact_id in context.input_artifact_ids:
            supplied_items.append(await self._required_artifact(artifact_id))
        supplied = tuple(supplied_items)
        matrix_artifact = self._one(supplied, ArtifactType.BANKING_OPTION_MATRIX)
        readiness_artifact = self._one(
            supplied,
            ArtifactType.BANKING_PRECHECK_READINESS,
        )
        review_artifact = self._one(
            supplied,
            ArtifactType.DECISION_POST_BANKING_REVIEW,
        )
        try:
            matrix = BankingOptionMatrix.model_validate(matrix_artifact.payload)
            readiness = BankingPrecheckReadiness.model_validate(
                readiness_artifact.payload
            )
            review = DecisionPostBankingReview.model_validate(review_artifact.payload)
        except ValidationError as exc:
            raise BankingPrecheckSubmissionProposalContextError(
                f"Invalid Banking precheck submission context: {exc}"
            ) from exc

        core_artifacts = (matrix_artifact, readiness_artifact, review_artifact)
        core_ids = tuple(item.artifact_id for item in core_artifacts)
        declared_upstream_ids = self._declared_upstream_ids(
            core_ids=core_ids,
            matrix=matrix,
            readiness=readiness,
            review=review,
        )
        expected_input_ids = (*core_ids, *declared_upstream_ids)
        if context.input_artifact_ids != expected_input_ids:
            raise BankingPrecheckSubmissionProposalContextError(
                "Banking precheck submission artifacts must exactly match stable "
                "matrix/readiness/review/upstream order."
            )
        supplied_by_id = {item.artifact_id: item for item in supplied}
        upstream_artifacts = tuple(
            supplied_by_id[artifact_id] for artifact_id in declared_upstream_ids
        )
        proposal_context = BankingPrecheckSubmissionProposalContext(
            matrix_artifact=matrix_artifact,
            readiness_artifact=readiness_artifact,
            review_artifact=review_artifact,
            upstream_artifacts=upstream_artifacts,
            matrix=matrix,
            readiness=readiness,
            review=review,
        )
        self._validate_identity(context, proposal_context)
        self._validate_ready_batch(proposal_context)
        self._validate_evidence(proposal_context)
        return proposal_context

    async def _required_artifact(self, artifact_id: str) -> ArtifactEnvelope:
        artifact = await self._artifacts.get(artifact_id)
        if artifact is None:
            raise BankingPrecheckSubmissionProposalContextError(
                f"Banking precheck submission received unknown artifact: {artifact_id}."
            )
        if artifact.validation_status not in _VALID_STATUSES:
            raise BankingPrecheckSubmissionProposalContextError(
                "Banking precheck submission received an unvalidated artifact: "
                f"{artifact_id}."
            )
        return artifact

    @staticmethod
    def _one(
        artifacts: tuple[ArtifactEnvelope, ...],
        artifact_type: ArtifactType,
    ) -> ArtifactEnvelope:
        matches = tuple(
            item for item in artifacts if item.artifact_type is artifact_type
        )
        if len(matches) != 1:
            raise BankingPrecheckSubmissionProposalContextError(
                "Banking precheck submission requires exactly one validated "
                f"{artifact_type.value} artifact."
            )
        return matches[0]

    @staticmethod
    def _declared_upstream_ids(
        *,
        core_ids: tuple[str, str, str],
        matrix: BankingOptionMatrix,
        readiness: BankingPrecheckReadiness,
        review: DecisionPostBankingReview,
    ) -> tuple[str, ...]:
        upstream: list[str] = []
        for artifact_id in (
            *matrix.source_artifact_ids,
            *readiness.source_artifact_ids,
            *review.source_artifact_ids,
        ):
            if artifact_id not in core_ids and artifact_id not in upstream:
                upstream.append(artifact_id)
        return tuple(upstream)

    @staticmethod
    def _validate_identity(
        execution: ExecutionContext,
        context: BankingPrecheckSubmissionProposalContext,
    ) -> None:
        matrix = context.matrix
        readiness = context.readiness
        review = context.review
        expected = (
            execution.evaluation_case_id,
            execution.dataset_id,
            matrix.contract_id,
        )
        if (matrix.evaluation_case_id, matrix.dataset_id, matrix.contract_id) != expected:
            raise BankingPrecheckSubmissionProposalContextError(
                "Banking matrix identity does not match proposal execution."
            )
        if (
            readiness.evaluation_case_id,
            readiness.dataset_id,
            readiness.contract_id,
        ) != expected:
            raise BankingPrecheckSubmissionProposalContextError(
                "Banking readiness identity does not match the matrix."
            )
        if (review.evaluation_case_id, review.dataset_id, review.contract_id) != expected:
            raise BankingPrecheckSubmissionProposalContextError(
                "Decision review identity does not match Banking readiness."
            )
        if any(
            artifact.evaluation_case_id != execution.evaluation_case_id
            for artifact in context.source_artifacts
        ):
            raise BankingPrecheckSubmissionProposalContextError(
                "A Banking precheck submission artifact belongs to another case."
            )
        if readiness.matrix_id != matrix.matrix_id:
            raise BankingPrecheckSubmissionProposalContextError(
                "Banking readiness references a different matrix."
            )
        if (
            review.matrix_id != matrix.matrix_id
            or review.readiness_id != readiness.readiness_id
            or review.banking_request_id != matrix.request_id
        ):
            raise BankingPrecheckSubmissionProposalContextError(
                "Decision review references a different Banking request or assessment."
            )
        if context.matrix_artifact.artifact_id not in readiness.source_artifact_ids:
            raise BankingPrecheckSubmissionProposalContextError(
                "Banking readiness is missing matrix artifact lineage."
            )
        if (
            context.matrix_artifact.artifact_id not in review.source_artifact_ids
            or context.readiness_artifact.artifact_id not in review.source_artifact_ids
        ):
            raise BankingPrecheckSubmissionProposalContextError(
                "Decision review is missing matrix/readiness artifact lineage."
            )
        if set(matrix.source_artifact_ids) & set(
            (
                context.matrix_artifact.artifact_id,
                context.readiness_artifact.artifact_id,
                context.review_artifact.artifact_id,
            )
        ):
            raise BankingPrecheckSubmissionProposalContextError(
                "Banking matrix lineage cannot reference current or downstream artifacts."
            )
        if set(readiness.source_artifact_ids) & {
            context.readiness_artifact.artifact_id,
            context.review_artifact.artifact_id,
        }:
            raise BankingPrecheckSubmissionProposalContextError(
                "Banking readiness lineage cannot reference itself or Decision review."
            )
        if context.review_artifact.artifact_id in review.source_artifact_ids:
            raise BankingPrecheckSubmissionProposalContextError(
                "Decision review lineage cannot reference itself."
            )

    @staticmethod
    def _validate_ready_batch(
        context: BankingPrecheckSubmissionProposalContext,
    ) -> None:
        matrix = context.matrix
        readiness = context.readiness
        review = context.review
        matrix_option_ids = tuple(item.option_id for item in matrix.candidates)
        readiness_option_ids = tuple(
            item.option_id for item in readiness.option_readiness
        )
        if matrix_option_ids != readiness_option_ids:
            raise BankingPrecheckSubmissionProposalContextError(
                "Banking readiness option order does not match the matrix."
            )
        if review.candidate_option_ids != matrix_option_ids:
            raise BankingPrecheckSubmissionProposalContextError(
                "Decision review candidate order does not match the matrix."
            )
        expected_ready_ids = tuple(
            item.option_id
            for item in readiness.option_readiness
            if item.status is BankingPrecheckReadinessStatus.READY
        )
        expected_pending_ids = tuple(
            item.option_id
            for item in readiness.option_readiness
            if item.status is not BankingPrecheckReadinessStatus.READY
        )
        if (
            readiness.ready_option_ids != expected_ready_ids
            or readiness.pending_option_ids != expected_pending_ids
        ):
            raise BankingPrecheckSubmissionProposalContextError(
                "Banking readiness indexes must include every READY option in matrix order."
            )
        if (
            review.precheck_ready_option_ids != readiness.ready_option_ids
            or review.pending_option_ids != readiness.pending_option_ids
        ):
            raise BankingPrecheckSubmissionProposalContextError(
                "Decision review readiness indexes are stale."
            )
        if review.outcome is not DecisionPostBankingOutcome.BANKING_PRECHECK_READY:
            raise BankingPrecheckSubmissionProposalContextError(
                "Decision review has not authorized proposal preparation."
            )
        if review.required_input_fields or review.missing_data_requests:
            raise BankingPrecheckSubmissionProposalContextError(
                "A ready Decision review cannot retain blocking input requests."
            )
        if not readiness.ready_option_ids:
            raise BankingPrecheckSubmissionProposalContextError(
                "Banking precheck submission requires at least one READY option."
            )
        if readiness.status not in {
            BankingPrecheckReadinessStatus.READY,
            BankingPrecheckReadinessStatus.PARTIALLY_READY,
        }:
            raise BankingPrecheckSubmissionProposalContextError(
                "Banking readiness status cannot support a submission proposal."
            )
        if matrix.requested_amount is None:
            raise BankingPrecheckSubmissionProposalContextError(
                "Banking precheck submission requires an explicit matrix amount."
            )
        if matrix.requested_amount_currency is not readiness.requested_amount_currency:
            raise BankingPrecheckSubmissionProposalContextError(
                "Banking readiness currency does not match the matrix."
            )
        ready_ids = set(readiness.ready_option_ids)
        for option in readiness.option_readiness:
            if option.option_id not in ready_ids:
                continue
            if option.status is not BankingPrecheckReadinessStatus.READY:
                raise BankingPrecheckSubmissionProposalContextError(
                    f"Option {option.option_id} is indexed READY but is not READY."
                )
            if option.api_id is None:
                raise BankingPrecheckSubmissionProposalContextError(
                    f"READY option {option.option_id} has no precheck API reference."
                )
            if tuple(item.required_field for item in option.field_resolutions) != (
                option.required_fields
            ):
                raise BankingPrecheckSubmissionProposalContextError(
                    f"READY option {option.option_id} has inconsistent field bindings."
                )
            if any(
                item.status is not BankingPrecheckFieldStatus.RESOLVED
                for item in option.field_resolutions
            ):
                raise BankingPrecheckSubmissionProposalContextError(
                    f"READY option {option.option_id} contains unresolved fields."
                )
            if option.failed_requirement_codes or any(
                item.status is BankingCriterionStatus.FAIL
                for item in option.requirement_checks
            ):
                raise BankingPrecheckSubmissionProposalContextError(
                    f"READY option {option.option_id} failed a product requirement."
                )

    @staticmethod
    def _validate_evidence(
        context: BankingPrecheckSubmissionProposalContext,
    ) -> None:
        checks = (
            (
                "matrix",
                context.matrix.evidence_ids,
                context.matrix_artifact,
            ),
            (
                "readiness",
                context.readiness.evidence_ids,
                context.readiness_artifact,
            ),
            (
                "review",
                context.review.evidence_ids,
                context.review_artifact,
            ),
        )
        for label, evidence_ids, artifact in checks:
            available = {item.evidence_id for item in artifact.evidence_refs}
            if not set(evidence_ids).issubset(available):
                raise BankingPrecheckSubmissionProposalContextError(
                    f"Banking {label} references evidence absent from its envelope."
                )
        matrix_declared = set(context.matrix.evidence_ids)
        matrix_nested = {
            evidence_id
            for candidate in context.matrix.candidates
            for evidence_id in (
                *candidate.evidence_ids,
                *(
                    item
                    for criterion in candidate.criteria
                    for item in criterion.evidence_ids
                ),
                *(
                    candidate.precheck.evidence_ids
                    if candidate.precheck is not None
                    else ()
                ),
            )
        }
        if not matrix_nested.issubset(matrix_declared):
            raise BankingPrecheckSubmissionProposalContextError(
                "A Banking matrix candidate references undeclared matrix evidence."
            )
        readiness_declared = set(context.readiness.evidence_ids)
        readiness_nested = {
            evidence_id
            for option in context.readiness.option_readiness
            for evidence_id in (
                *option.evidence_ids,
                *(
                    item
                    for resolution in option.field_resolutions
                    for item in resolution.evidence_ids
                ),
                *(
                    item
                    for requirement in option.requirement_checks
                    for item in requirement.evidence_ids
                ),
            )
        }
        if not readiness_nested.issubset(readiness_declared):
            raise BankingPrecheckSubmissionProposalContextError(
                "A Banking readiness option references undeclared readiness evidence."
            )
