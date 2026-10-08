"""Load Document preparation inputs from exact artifacts and dataset keys."""

from dataclasses import dataclass

from pydantic import ValidationError

from opc_mis.domain.artifacts import ArtifactEnvelope
from opc_mis.domain.components import ExecutionContext
from opc_mis.domain.dataset import DatasetRecord, DatasetSnapshot
from opc_mis.domain.document_models import (
    DocumentEvidenceSupplement,
    DocumentPreparationRequest,
)
from opc_mis.domain.enums import ArtifactType, ValidationStatus
from opc_mis.domain.planner_models import EvaluationCase
from opc_mis.domain.team_pack import SheetRegistry
from opc_mis.ports.artifact_repository import ArtifactRepository
from opc_mis.ports.dataset_port import DatasetNotFoundError, DatasetPort

_VALID_STATUSES = {ValidationStatus.VALID, ValidationStatus.VALID_WITH_WARNINGS}
_ALLOWED_TYPES = {
    ArtifactType.EVALUATION_CASE,
    ArtifactType.DOCUMENT_PREPARATION_REQUEST,
    ArtifactType.DOCUMENT_EVIDENCE_SUPPLEMENT,
}


class DocumentContextError(RuntimeError):
    """Raised when Document inputs are incomplete or internally inconsistent."""


@dataclass(frozen=True)
class DocumentContext:
    """Validated immutable inputs for one provider-specific document package."""

    dataset: DatasetSnapshot
    evaluation_case_artifact: ArtifactEnvelope
    request_artifact: ArtifactEnvelope
    supplement_artifacts: tuple[ArtifactEnvelope, ...]
    evaluation_case: EvaluationCase
    request: DocumentPreparationRequest
    supplements: tuple[DocumentEvidenceSupplement, ...]
    contract: DatasetRecord
    opc_profile_records: tuple[DatasetRecord, ...]
    cashflow_records: tuple[DatasetRecord, ...]

    @property
    def source_artifact_ids(self) -> tuple[str, ...]:
        """Return semantic dependency order for stable artifact identity."""
        return (
            self.evaluation_case_artifact.artifact_id,
            self.request_artifact.artifact_id,
            *(item.artifact_id for item in self.supplement_artifacts),
        )


class DocumentContextLoader:
    """Resolve exact case/request artifacts without reading Excel directly."""

    def __init__(self, *, datasets: DatasetPort, artifacts: ArtifactRepository) -> None:
        self._datasets = datasets
        self._artifacts = artifacts

    async def load(self, context: ExecutionContext) -> DocumentContext:
        if context.evaluation_case_id is None:
            raise DocumentContextError("Document preparation requires evaluation_case_id.")
        loaded: list[ArtifactEnvelope] = []
        for artifact_id in context.input_artifact_ids:
            artifact = await self._artifacts.get(artifact_id)
            if artifact is None:
                raise DocumentContextError(
                    f"Document preparation received unknown artifact: {artifact_id}."
                )
            if artifact.validation_status not in _VALID_STATUSES:
                raise DocumentContextError(
                    f"Document preparation received unvalidated artifact: {artifact_id}."
                )
            if artifact.artifact_type not in _ALLOWED_TYPES:
                raise DocumentContextError(
                    "Document preparation received unexpected artifact type: "
                    f"{artifact.artifact_type.value}."
                )
            if artifact.evaluation_case_id != context.evaluation_case_id:
                raise DocumentContextError(
                    "A Document preparation artifact belongs to another case."
                )
            loaded.append(artifact)

        case_artifact = self._one(loaded, ArtifactType.EVALUATION_CASE)
        request_artifact = self._one(
            loaded, ArtifactType.DOCUMENT_PREPARATION_REQUEST
        )
        supplement_artifacts = tuple(
            item
            for item in loaded
            if item.artifact_type is ArtifactType.DOCUMENT_EVIDENCE_SUPPLEMENT
        )
        expected_order = (
            case_artifact.artifact_id,
            request_artifact.artifact_id,
            *(item.artifact_id for item in supplement_artifacts),
        )
        if context.input_artifact_ids != expected_order:
            raise DocumentContextError(
                "Document inputs must preserve case, request, then supplement order."
            )
        try:
            evaluation_case = EvaluationCase.model_validate(case_artifact.payload)
            request = DocumentPreparationRequest.model_validate(request_artifact.payload)
            supplements = tuple(
                DocumentEvidenceSupplement.model_validate(item.payload)
                for item in supplement_artifacts
            )
            dataset = await self._datasets.get_snapshot(context.dataset_id)
        except (ValidationError, DatasetNotFoundError) as exc:
            raise DocumentContextError(
                f"Invalid Document preparation context: {exc}"
            ) from exc

        expected_identity = (
            context.evaluation_case_id,
            context.dataset_id,
            evaluation_case.contract_id,
        )
        if (
            evaluation_case.evaluation_case_id,
            evaluation_case.dataset_id,
            evaluation_case.contract_id,
        ) != expected_identity:
            raise DocumentContextError(
                "EvaluationCase identity does not match Document preparation."
            )
        if (request.evaluation_case_id, request.dataset_id, request.contract_id) != (
            expected_identity
        ):
            raise DocumentContextError(
                "Document request identity does not match EvaluationCase."
            )
        if request.evidence_ids != tuple(
            item.evidence_id for item in request_artifact.evidence_refs
            if item.evidence_id in set(request.evidence_ids)
        ):
            missing = set(request.evidence_ids) - {
                item.evidence_id for item in request_artifact.evidence_refs
            }
            if missing:
                raise DocumentContextError(
                    "Document request references evidence absent from its envelope."
                )
        required_codes = set(request.required_document_codes)
        seen_types: set[object] = set()
        for supplement, artifact in zip(
            supplements, supplement_artifacts, strict=True
        ):
            if (
                supplement.evaluation_case_id,
                supplement.dataset_id,
                supplement.contract_id,
            ) != expected_identity:
                raise DocumentContextError(
                    "A Document evidence supplement belongs to another case."
                )
            if supplement.preparation_request_id != request.request_id:
                raise DocumentContextError(
                    "A Document evidence supplement belongs to another request."
                )
            if supplement.document_type not in required_codes:
                raise DocumentContextError(
                    "A Document evidence supplement resolves an unrequested type."
                )
            if supplement.document_type in seen_types:
                raise DocumentContextError(
                    "Document preparation received duplicate supplements for one type."
                )
            seen_types.add(supplement.document_type)
            if not set(supplement.evidence_ids).issubset(
                {item.evidence_id for item in artifact.evidence_refs}
            ):
                raise DocumentContextError(
                    "A Document supplement references evidence absent from its envelope."
                )
        contract_matches = dataset.lookup(
            SheetRegistry.CONTRACTS, evaluation_case.contract_id
        )
        if len(contract_matches) != 1:
            raise DocumentContextError(
                "Document preparation requires exactly one explicit contract record."
            )
        return DocumentContext(
            dataset=dataset,
            evaluation_case_artifact=case_artifact,
            request_artifact=request_artifact,
            supplement_artifacts=supplement_artifacts,
            evaluation_case=evaluation_case,
            request=request,
            supplements=supplements,
            contract=contract_matches[0],
            opc_profile_records=tuple(dataset.records(SheetRegistry.OPC_PROFILE)),
            cashflow_records=tuple(dataset.records(SheetRegistry.CASHFLOW)),
        )

    @staticmethod
    def _one(
        artifacts: list[ArtifactEnvelope], artifact_type: ArtifactType
    ) -> ArtifactEnvelope:
        matches = tuple(
            item for item in artifacts if item.artifact_type is artifact_type
        )
        if len(matches) != 1:
            raise DocumentContextError(
                "Document preparation requires exactly one validated "
                f"{artifact_type.value} artifact."
            )
        return matches[0]
