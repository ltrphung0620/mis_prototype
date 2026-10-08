"""Load authoritative Banking artifacts for deterministic Decision review."""

from dataclasses import dataclass

from pydantic import ValidationError

from opc_mis.domain.artifacts import ArtifactEnvelope
from opc_mis.domain.banking_models import (
    BankingOptionMatrix,
    BankingPrecheckReadiness,
)
from opc_mis.domain.components import ExecutionContext
from opc_mis.domain.enums import ArtifactType, ValidationStatus
from opc_mis.ports.artifact_repository import ArtifactRepository


class DecisionPostBankingContextError(RuntimeError):
    """Raised when post-Banking inputs are missing, invalid, or inconsistent."""


@dataclass(frozen=True)
class DecisionPostBankingContext:
    """Validated deterministic Banking inputs used by Decision."""

    matrix_artifact: ArtifactEnvelope
    readiness_artifact: ArtifactEnvelope
    matrix: BankingOptionMatrix
    readiness: BankingPrecheckReadiness

    @property
    def source_artifact_ids(self) -> tuple[str, str]:
        return (
            self.matrix_artifact.artifact_id,
            self.readiness_artifact.artifact_id,
        )


class DecisionPostBankingContextLoader:
    """Resolve one matrix and one readiness artifact without reading source data."""

    def __init__(self, *, artifacts: ArtifactRepository) -> None:
        self._artifacts = artifacts

    async def load(self, context: ExecutionContext) -> DecisionPostBankingContext:
        if context.evaluation_case_id is None:
            raise DecisionPostBankingContextError(
                "Decision post-Banking review requires evaluation_case_id."
            )
        upstream: list[ArtifactEnvelope] = []
        for artifact_id in context.input_artifact_ids:
            artifact = await self._artifacts.get(artifact_id)
            if artifact is None:
                raise DecisionPostBankingContextError(
                    f"Decision post-Banking review received unknown artifact: {artifact_id}."
                )
            if artifact.validation_status not in {
                ValidationStatus.VALID,
                ValidationStatus.VALID_WITH_WARNINGS,
            }:
                raise DecisionPostBankingContextError(
                    "Decision post-Banking review received unvalidated artifact: "
                    f"{artifact_id}."
                )
            upstream.append(artifact)
        matrix_artifact = self._one(upstream, ArtifactType.BANKING_OPTION_MATRIX)
        readiness_artifact = self._one(
            upstream,
            ArtifactType.BANKING_PRECHECK_READINESS,
        )
        if len(upstream) != 2:
            unexpected = tuple(
                item.artifact_type.value
                for item in upstream
                if item.artifact_type
                not in {
                    ArtifactType.BANKING_OPTION_MATRIX,
                    ArtifactType.BANKING_PRECHECK_READINESS,
                }
            )
            raise DecisionPostBankingContextError(
                "Decision post-Banking review received unexpected artifacts: "
                + ", ".join(unexpected)
            )
        try:
            matrix = BankingOptionMatrix.model_validate(matrix_artifact.payload)
            readiness = BankingPrecheckReadiness.model_validate(
                readiness_artifact.payload
            )
        except ValidationError as exc:
            raise DecisionPostBankingContextError(
                f"Invalid Decision post-Banking input schema: {exc}"
            ) from exc
        expected = (
            context.evaluation_case_id,
            context.dataset_id,
            matrix.contract_id,
        )
        if (matrix.evaluation_case_id, matrix.dataset_id, matrix.contract_id) != expected:
            raise DecisionPostBankingContextError(
                "Banking matrix identity does not match Decision execution."
            )
        if (
            readiness.evaluation_case_id,
            readiness.dataset_id,
            readiness.contract_id,
        ) != expected:
            raise DecisionPostBankingContextError(
                "Banking readiness identity does not match the option matrix."
            )
        if any(
            artifact.evaluation_case_id != context.evaluation_case_id
            for artifact in (matrix_artifact, readiness_artifact)
        ):
            raise DecisionPostBankingContextError(
                "A post-Banking input envelope belongs to another case."
            )
        if readiness.matrix_id != matrix.matrix_id:
            raise DecisionPostBankingContextError(
                "Banking readiness references a different option matrix."
            )
        if matrix_artifact.artifact_id not in readiness.source_artifact_ids:
            raise DecisionPostBankingContextError(
                "Banking readiness is missing matrix artifact lineage."
            )
        matrix_option_ids = tuple(item.option_id for item in matrix.candidates)
        readiness_option_ids = tuple(
            item.option_id for item in readiness.option_readiness
        )
        if matrix_option_ids != readiness_option_ids:
            raise DecisionPostBankingContextError(
                "Banking readiness option index does not match the matrix."
            )
        return DecisionPostBankingContext(
            matrix_artifact=matrix_artifact,
            readiness_artifact=readiness_artifact,
            matrix=matrix,
            readiness=readiness,
        )

    @staticmethod
    def _one(
        artifacts: list[ArtifactEnvelope], artifact_type: ArtifactType
    ) -> ArtifactEnvelope:
        matches = tuple(
            item for item in artifacts if item.artifact_type is artifact_type
        )
        if len(matches) != 1:
            raise DecisionPostBankingContextError(
                "Decision post-Banking review requires exactly one validated "
                f"{artifact_type.value} artifact."
            )
        return matches[0]
