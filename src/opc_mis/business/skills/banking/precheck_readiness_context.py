"""Load explicit inputs for deterministic Banking precheck readiness."""

from dataclasses import dataclass

from pydantic import ValidationError

from opc_mis.domain.artifacts import ArtifactEnvelope
from opc_mis.domain.banking_models import (
    BankingInputSupplement,
    BankingOptionMatrix,
)
from opc_mis.domain.components import ExecutionContext
from opc_mis.domain.dataset import DatasetRecord, DatasetSnapshot
from opc_mis.domain.enums import ArtifactType, ValidationStatus
from opc_mis.domain.planner_models import EvaluationCase
from opc_mis.domain.team_pack import SheetRegistry
from opc_mis.ports.artifact_repository import ArtifactRepository
from opc_mis.ports.dataset_port import DatasetNotFoundError, DatasetPort

_ALLOWED_TYPES = {
    ArtifactType.EVALUATION_CASE,
    ArtifactType.BANKING_OPTION_MATRIX,
    ArtifactType.BANKING_INPUT_SUPPLEMENT,
}
_VALID_STATUSES = {ValidationStatus.VALID, ValidationStatus.VALID_WITH_WARNINGS}


class BankingPrecheckReadinessContextError(RuntimeError):
    """Raised when authoritative readiness inputs are invalid or inconsistent."""


@dataclass(frozen=True)
class BankingPrecheckReadinessContext:
    """Validated artifacts and the exact OPC profile sheet projection."""

    dataset: DatasetSnapshot
    evaluation_case_artifact: ArtifactEnvelope
    matrix_artifact: ArtifactEnvelope
    supplement_artifact: ArtifactEnvelope | None
    evaluation_case: EvaluationCase
    matrix: BankingOptionMatrix
    supplement: BankingInputSupplement | None
    opc_profile_records: tuple[DatasetRecord, ...]

    @property
    def source_artifact_ids(self) -> tuple[str, ...]:
        """Return explicit artifact dependencies in stable semantic order."""
        return (
            self.evaluation_case_artifact.artifact_id,
            self.matrix_artifact.artifact_id,
            *(
                (self.supplement_artifact.artifact_id,)
                if self.supplement_artifact is not None
                else ()
            ),
        )


class BankingPrecheckReadinessContextLoader:
    """Resolve exact artifacts and OPC profile records; never inspect credit profiles."""

    def __init__(self, *, datasets: DatasetPort, artifacts: ArtifactRepository) -> None:
        self._datasets = datasets
        self._artifacts = artifacts

    async def load(
        self, context: ExecutionContext
    ) -> BankingPrecheckReadinessContext:
        if context.evaluation_case_id is None:
            raise BankingPrecheckReadinessContextError(
                "Banking precheck readiness requires evaluation_case_id."
            )
        upstream: list[ArtifactEnvelope] = []
        for artifact_id in context.input_artifact_ids:
            artifact = await self._artifacts.get(artifact_id)
            if artifact is None:
                raise BankingPrecheckReadinessContextError(
                    f"Banking readiness received an unknown artifact: {artifact_id}."
                )
            if artifact.validation_status not in _VALID_STATUSES:
                raise BankingPrecheckReadinessContextError(
                    f"Banking readiness received an unvalidated artifact: {artifact_id}."
                )
            if artifact.artifact_type not in _ALLOWED_TYPES:
                raise BankingPrecheckReadinessContextError(
                    "Banking readiness received an unexpected artifact: "
                    f"{artifact.artifact_type.value}."
                )
            upstream.append(artifact)

        case_artifact = self._one(upstream, ArtifactType.EVALUATION_CASE)
        matrix_artifact = self._one(upstream, ArtifactType.BANKING_OPTION_MATRIX)
        supplements = tuple(
            item
            for item in upstream
            if item.artifact_type is ArtifactType.BANKING_INPUT_SUPPLEMENT
        )
        if len(supplements) > 1:
            raise BankingPrecheckReadinessContextError(
                "Banking readiness accepts at most one immutable input supplement."
            )
        supplement_artifact = supplements[0] if supplements else None
        try:
            evaluation_case = EvaluationCase.model_validate(case_artifact.payload)
            matrix = BankingOptionMatrix.model_validate(matrix_artifact.payload)
            supplement = (
                BankingInputSupplement.model_validate(supplement_artifact.payload)
                if supplement_artifact is not None
                else None
            )
            dataset = await self._datasets.get_snapshot(context.dataset_id)
        except (ValidationError, DatasetNotFoundError) as exc:
            raise BankingPrecheckReadinessContextError(
                f"Invalid Banking readiness context: {exc}"
            ) from exc

        self._validate_identity(
            context=context,
            dataset=dataset,
            case_artifact=case_artifact,
            matrix_artifact=matrix_artifact,
            supplement_artifact=supplement_artifact,
            evaluation_case=evaluation_case,
            matrix=matrix,
            supplement=supplement,
        )
        return BankingPrecheckReadinessContext(
            dataset=dataset,
            evaluation_case_artifact=case_artifact,
            matrix_artifact=matrix_artifact,
            supplement_artifact=supplement_artifact,
            evaluation_case=evaluation_case,
            matrix=matrix,
            supplement=supplement,
            opc_profile_records=tuple(dataset.records(SheetRegistry.OPC_PROFILE)),
        )

    @staticmethod
    def _one(
        artifacts: list[ArtifactEnvelope], artifact_type: ArtifactType
    ) -> ArtifactEnvelope:
        matches = tuple(
            item for item in artifacts if item.artifact_type is artifact_type
        )
        if len(matches) != 1:
            raise BankingPrecheckReadinessContextError(
                "Banking readiness requires exactly one validated "
                f"{artifact_type.value} artifact."
            )
        return matches[0]

    @staticmethod
    def _validate_identity(
        *,
        context: ExecutionContext,
        dataset: DatasetSnapshot,
        case_artifact: ArtifactEnvelope,
        matrix_artifact: ArtifactEnvelope,
        supplement_artifact: ArtifactEnvelope | None,
        evaluation_case: EvaluationCase,
        matrix: BankingOptionMatrix,
        supplement: BankingInputSupplement | None,
    ) -> None:
        expected = (
            context.evaluation_case_id,
            context.dataset_id,
            evaluation_case.contract_id,
        )
        if (
            evaluation_case.evaluation_case_id,
            evaluation_case.dataset_id,
            evaluation_case.contract_id,
        ) != expected:
            raise BankingPrecheckReadinessContextError(
                "EvaluationCase identity does not match the readiness execution."
            )
        if (matrix.evaluation_case_id, matrix.dataset_id, matrix.contract_id) != expected:
            raise BankingPrecheckReadinessContextError(
                "Banking option matrix identity does not match EvaluationCase."
            )
        if dataset.dataset_id != context.dataset_id:
            raise BankingPrecheckReadinessContextError(
                "Dataset snapshot identity does not match readiness execution."
            )
        if any(
            artifact.evaluation_case_id != context.evaluation_case_id
            for artifact in (
                case_artifact,
                matrix_artifact,
                *(
                    (supplement_artifact,)
                    if supplement_artifact is not None
                    else ()
                ),
            )
        ):
            raise BankingPrecheckReadinessContextError(
                "A Banking readiness envelope belongs to another case."
            )
        if case_artifact.artifact_id not in matrix.source_artifact_ids:
            raise BankingPrecheckReadinessContextError(
                "Banking option matrix is missing EvaluationCase lineage."
            )
        if supplement is not None:
            if (
                supplement.evaluation_case_id,
                supplement.dataset_id,
                supplement.contract_id,
            ) != expected:
                raise BankingPrecheckReadinessContextError(
                    "Banking input supplement identity does not match EvaluationCase."
                )
            if supplement.banking_request_id != matrix.request_id:
                raise BankingPrecheckReadinessContextError(
                    "Banking input supplement belongs to a different Banking request."
                )
            if (
                matrix.requested_amount != supplement.requested_amount
                or matrix.requested_amount_currency
                is not supplement.requested_amount_currency
            ):
                raise BankingPrecheckReadinessContextError(
                    "Banking matrix amount does not match its immutable supplement."
                )
            if case_artifact.artifact_id not in supplement.source_artifact_ids:
                raise BankingPrecheckReadinessContextError(
                    "Banking input supplement is missing EvaluationCase lineage."
                )
            supplement_evidence = {
                item.evidence_id
                for item in supplement_artifact.evidence_refs  # type: ignore[union-attr]
            }
            if not set(supplement.evidence_ids).issubset(supplement_evidence):
                raise BankingPrecheckReadinessContextError(
                    "Banking input supplement references evidence absent from its envelope."
                )
        elif matrix.requested_amount is not None:
            raise BankingPrecheckReadinessContextError(
                "Banking matrix contains an amount without an input supplement."
            )
