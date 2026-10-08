"""Load one persisted deterministic Banking matrix for optional advice."""

from dataclasses import dataclass

from pydantic import ValidationError

from opc_mis.domain.artifacts import ArtifactEnvelope
from opc_mis.domain.banking_models import BankingOptionMatrix
from opc_mis.domain.components import ExecutionContext
from opc_mis.domain.enums import ArtifactType, ValidationStatus
from opc_mis.ports.artifact_repository import ArtifactRepository


class BankingAdvisorContextError(RuntimeError):
    """Raised when the advisor does not receive one validated option matrix."""


@dataclass(frozen=True)
class BankingAdvisorContext:
    """Validated matrix and immutable envelope consumed by the advisor."""

    matrix_artifact: ArtifactEnvelope
    matrix: BankingOptionMatrix


class BankingAdvisorContextLoader:
    """Resolve only the persisted matrix explicitly supplied by Workflow."""

    def __init__(self, *, artifacts: ArtifactRepository) -> None:
        self._artifacts = artifacts

    async def load(self, context: ExecutionContext) -> BankingAdvisorContext:
        if context.evaluation_case_id is None:
            raise BankingAdvisorContextError(
                "Banking option advisor requires evaluation_case_id."
            )
        upstream: list[ArtifactEnvelope] = []
        for artifact_id in context.input_artifact_ids:
            artifact = await self._artifacts.get(artifact_id)
            if artifact is None:
                raise BankingAdvisorContextError(
                    f"Banking advisor received an unknown artifact: {artifact_id}."
                )
            if artifact.validation_status not in {
                ValidationStatus.VALID,
                ValidationStatus.VALID_WITH_WARNINGS,
            }:
                raise BankingAdvisorContextError(
                    f"Banking advisor received an unvalidated artifact: {artifact_id}."
                )
            upstream.append(artifact)

        matrices = tuple(
            item
            for item in upstream
            if item.artifact_type is ArtifactType.BANKING_OPTION_MATRIX
        )
        unexpected = tuple(
            item.artifact_type
            for item in upstream
            if item.artifact_type is not ArtifactType.BANKING_OPTION_MATRIX
        )
        if unexpected:
            raise BankingAdvisorContextError(
                "Banking advisor received unexpected artifacts: "
                + ", ".join(item.value for item in unexpected)
            )
        if len(matrices) != 1:
            raise BankingAdvisorContextError(
                "Banking option advisor requires exactly one validated "
                "BANKING_OPTION_MATRIX artifact."
            )
        matrix_artifact = matrices[0]
        try:
            matrix = BankingOptionMatrix.model_validate(matrix_artifact.payload)
        except ValidationError as exc:
            raise BankingAdvisorContextError(
                f"Invalid Banking option matrix schema: {exc}"
            ) from exc
        if matrix_artifact.evaluation_case_id != context.evaluation_case_id:
            raise BankingAdvisorContextError(
                "Banking matrix envelope belongs to a different evaluation case."
            )
        if (
            matrix.evaluation_case_id != context.evaluation_case_id
            or matrix.dataset_id != context.dataset_id
        ):
            raise BankingAdvisorContextError(
                "Banking matrix identity does not match the advisor execution context."
            )
        return BankingAdvisorContext(
            matrix_artifact=matrix_artifact,
            matrix=matrix,
        )
