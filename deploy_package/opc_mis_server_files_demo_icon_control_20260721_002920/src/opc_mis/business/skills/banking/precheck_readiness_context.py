"""Load explicit inputs for deterministic Banking precheck readiness."""

from dataclasses import dataclass

from pydantic import ValidationError

from opc_mis.domain.artifacts import ArtifactEnvelope
from opc_mis.domain.banking_models import (
    BankingDiscoveryRequest,
    BankingInputSupplement,
    BankingOptionMatrix,
)
from opc_mis.domain.components import ExecutionContext
from opc_mis.domain.dataset import DatasetRecord, DatasetSnapshot
from opc_mis.domain.enums import ArtifactType, SourceType, ValidationStatus
from opc_mis.domain.planner_models import EvaluationCase
from opc_mis.domain.team_pack import SheetRegistry
from opc_mis.ports.artifact_repository import ArtifactRepository
from opc_mis.ports.dataset_port import DatasetNotFoundError, DatasetPort

_ALLOWED_TYPES = {
    ArtifactType.EVALUATION_CASE,
    ArtifactType.BANKING_DISCOVERY_REQUEST,
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
    request_artifact: ArtifactEnvelope
    matrix_artifact: ArtifactEnvelope
    supplement_artifact: ArtifactEnvelope | None
    evaluation_case: EvaluationCase
    request: BankingDiscoveryRequest
    matrix: BankingOptionMatrix
    supplement: BankingInputSupplement | None
    opc_profile_records: tuple[DatasetRecord, ...]

    @property
    def source_artifact_ids(self) -> tuple[str, ...]:
        """Return explicit artifact dependencies in stable semantic order."""
        return (
            self.evaluation_case_artifact.artifact_id,
            self.request_artifact.artifact_id,
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
        request_artifact = self._one(
            upstream, ArtifactType.BANKING_DISCOVERY_REQUEST
        )
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
            request = BankingDiscoveryRequest.model_validate(request_artifact.payload)
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
            request_artifact=request_artifact,
            matrix_artifact=matrix_artifact,
            supplement_artifact=supplement_artifact,
            evaluation_case=evaluation_case,
            request=request,
            matrix=matrix,
            supplement=supplement,
        )
        return BankingPrecheckReadinessContext(
            dataset=dataset,
            evaluation_case_artifact=case_artifact,
            request_artifact=request_artifact,
            matrix_artifact=matrix_artifact,
            supplement_artifact=supplement_artifact,
            evaluation_case=evaluation_case,
            request=request,
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
        request_artifact: ArtifactEnvelope,
        matrix_artifact: ArtifactEnvelope,
        supplement_artifact: ArtifactEnvelope | None,
        evaluation_case: EvaluationCase,
        request: BankingDiscoveryRequest,
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
        if (request.evaluation_case_id, request.dataset_id, request.contract_id) != expected:
            raise BankingPrecheckReadinessContextError(
                "Banking discovery request identity does not match EvaluationCase."
            )
        if request.request_id != matrix.request_id:
            raise BankingPrecheckReadinessContextError(
                "Banking option matrix belongs to a different discovery request."
            )
        if dataset.dataset_id != context.dataset_id:
            raise BankingPrecheckReadinessContextError(
                "Dataset snapshot identity does not match readiness execution."
            )
        if any(
            artifact.evaluation_case_id != context.evaluation_case_id
            for artifact in (
                case_artifact,
                request_artifact,
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
        if (
            case_artifact.artifact_id not in matrix.source_artifact_ids
            or request_artifact.artifact_id not in matrix.source_artifact_ids
        ):
            raise BankingPrecheckReadinessContextError(
                "Banking option matrix is missing EvaluationCase or discovery-request "
                "lineage."
            )
        request_evidence = {
            item.evidence_id: item for item in request_artifact.evidence_refs
        }
        matrix_evidence = {
            item.evidence_id: item for item in matrix_artifact.evidence_refs
        }
        if not set(request.evidence_ids).issubset(request_evidence):
            raise BankingPrecheckReadinessContextError(
                "Banking discovery request references evidence absent from its envelope."
            )
        if not set(request.amount_evidence_ids).issubset(matrix_evidence):
            raise BankingPrecheckReadinessContextError(
                "Banking option matrix does not retain its request amount evidence."
            )
        if request.requested_amount is not None:
            amount_evidence = tuple(
                request_evidence[evidence_id]
                for evidence_id in request.amount_evidence_ids
            )
            if (
                len(amount_evidence) != 1
                or amount_evidence[0].source_type is not SourceType.TEAM_PACK
                or amount_evidence[0].sheet
                != SheetRegistry.CREDIT_PROFILES.sheet_name
                or amount_evidence[0].record_id != request.credit_case_id
                or amount_evidence[0].field != "requested_amount"
                or amount_evidence[0].display_value != request.requested_amount
                or matrix_evidence[amount_evidence[0].evidence_id]
                != amount_evidence[0]
            ):
                raise BankingPrecheckReadinessContextError(
                    "Banking readiness amount must retain one exact credit-profile "
                    "requested_amount evidence item."
                )
            if (
                matrix.requested_amount != request.requested_amount
                or matrix.requested_amount_currency
                is not request.requested_amount_currency
            ):
                raise BankingPrecheckReadinessContextError(
                    "Banking matrix amount does not match its authoritative discovery "
                    "request."
                )
            if request.credit_case_id not in evaluation_case.related_credit_case_ids:
                raise BankingPrecheckReadinessContextError(
                    "Banking request amount credit case is not an explicit "
                    "EvaluationCase relationship."
                )
            requirements = tuple(
                item
                for item in evaluation_case.contract_requirements
                if item.requirement_id == request.requirement_id
            )
            if len(requirements) != 1:
                raise BankingPrecheckReadinessContextError(
                    "Banking request amount does not reference one exact EvaluationCase "
                    "contract requirement."
                )
            requirement = requirements[0]
            if (
                len(request.need_types) != 1
                or requirement.requirement_type.value
                != request.need_types[0].value
                or requirement.credit_case_id != request.credit_case_id
                or requirement.requested_amount != request.requested_amount
                or requirement.requested_amount_currency
                is not request.requested_amount_currency
                or requirement.amount_semantics is not request.amount_semantics
                or not set(request.amount_evidence_ids).issubset(
                    requirement.evidence_ids
                )
            ):
                raise BankingPrecheckReadinessContextError(
                    "Banking request amount does not match its exact EvaluationCase "
                    "contract requirement."
                )
            case_evidence = {
                item.evidence_id: item for item in case_artifact.evidence_refs
            }
            if any(
                case_evidence.get(evidence_id)
                != request_evidence[evidence_id]
                for evidence_id in request.amount_evidence_ids
            ):
                raise BankingPrecheckReadinessContextError(
                    "EvaluationCase artifact does not retain the Banking request amount "
                    "evidence."
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
            if request.requested_amount is None and (
                matrix.requested_amount != supplement.requested_amount
                or matrix.requested_amount_currency
                is not supplement.requested_amount_currency
            ):
                raise BankingPrecheckReadinessContextError(
                    "Legacy Banking matrix amount does not match its immutable supplement."
                )
            if request.requested_amount is not None and (
                supplement.requested_amount != request.requested_amount
                or supplement.requested_amount_currency
                is not request.requested_amount_currency
            ):
                raise BankingPrecheckReadinessContextError(
                    "A legacy Banking supplement conflicts with the authoritative "
                    "discovery request."
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
        elif request.requested_amount is None and matrix.requested_amount is not None:
            raise BankingPrecheckReadinessContextError(
                "Banking matrix contains an amount without a discovery-request or legacy "
                "supplement source."
            )
