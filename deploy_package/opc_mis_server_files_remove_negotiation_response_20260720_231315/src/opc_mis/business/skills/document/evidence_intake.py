"""Reference-only intake for one blocking Document evidence request."""

from typing import Any

from pydantic import ValidationError

from opc_mis.domain.artifacts import ArtifactDraft, ArtifactEnvelope
from opc_mis.domain.components import ExecutionContext
from opc_mis.domain.document_models import (
    DocumentEvidenceCommand,
    DocumentEvidenceIntakeComponentResult,
    DocumentEvidenceSupplement,
    DocumentPackageDraft,
    DocumentPackageReadiness,
)
from opc_mis.domain.enums import (
    ArtifactType,
    ComponentStatus,
    MissingRequestStatus,
    MissingSeverity,
    SourceType,
    ValidationStatus,
)
from opc_mis.domain.events import RuntimeEvent
from opc_mis.domain.evidence import EvidenceRef
from opc_mis.domain.lineage import deterministic_id
from opc_mis.domain.serialization import json_safe
from opc_mis.ports.artifact_repository import ArtifactRepository
from opc_mis.ports.text_redaction_service import TextRedactionService

_VALID_STATUSES = {ValidationStatus.VALID, ValidationStatus.VALID_WITH_WARNINGS}


class DocumentEvidenceIntakeError(ValueError):
    """Raised for stale, mismatched, or unsafe Document evidence input."""


class DocumentEvidenceIntake:
    """Turn caller-declared opaque document metadata into an immutable draft."""

    component_id = "DOCUMENT_EVIDENCE_INTAKE"

    def __init__(
        self,
        *,
        artifacts: ArtifactRepository,
        redactor: TextRedactionService,
    ) -> None:
        self._artifacts = artifacts
        self._redactor = redactor

    async def execute(
        self, context: ExecutionContext
    ) -> DocumentEvidenceIntakeComponentResult:
        try:
            command = DocumentEvidenceCommand.model_validate(context.component_input)
            package_artifact, package = await self._load(context)
            supplement, evidence_refs = self._build(
                context=context,
                command=command,
                package_artifact=package_artifact,
                package=package,
            )
        except ValidationError:
            return self._failed_safe(
                "Document evidence submission failed schema validation."
            )
        except DocumentEvidenceIntakeError as exc:
            return self._failed_safe(str(exc))

        draft = ArtifactDraft(
            artifact_type=ArtifactType.DOCUMENT_EVIDENCE_SUPPLEMENT,
            evaluation_case_id=supplement.evaluation_case_id,
            producer=self.component_id,
            payload=supplement.model_dump(mode="json"),
            evidence_refs=evidence_refs,
            identity_inputs={
                "preparation_request_id": supplement.preparation_request_id,
                "missing_request_id": supplement.missing_request_id,
                "document_reference_id": supplement.document_reference_id,
                "content_sha256": supplement.content_sha256,
                "document_type": supplement.document_type,
                "source_package_artifact_id": (
                    supplement.source_package_artifact_id
                ),
            },
        )
        return DocumentEvidenceIntakeComponentResult(
            status=ComponentStatus.COMPLETED,
            supplement=supplement,
            artifacts=(draft,),
            runtime_events=(
                RuntimeEvent(
                    event_type="DOCUMENT_EVIDENCE_SUPPLEMENT_PREPARED",
                    message=(
                        "A reference-only Document evidence supplement was prepared; "
                        "no file path or raw content was accepted."
                    ),
                    metadata={
                        "supplement_id": supplement.supplement_id,
                        "document_type": supplement.document_type.value,
                        "missing_request_id": supplement.missing_request_id,
                    },
                ),
            ),
        )

    async def _load(
        self, context: ExecutionContext
    ) -> tuple[ArtifactEnvelope, DocumentPackageDraft]:
        if context.evaluation_case_id is None:
            raise DocumentEvidenceIntakeError(
                "Document evidence intake requires evaluation_case_id."
            )
        if len(context.input_artifact_ids) != 1:
            raise DocumentEvidenceIntakeError(
                "Document evidence intake requires exactly one package draft."
            )
        artifact_id = context.input_artifact_ids[0]
        artifact = await self._artifacts.get(artifact_id)
        if artifact is None:
            raise DocumentEvidenceIntakeError(
                f"Document evidence intake received unknown artifact: {artifact_id}."
            )
        if artifact.artifact_type is not ArtifactType.DOCUMENT_PACKAGE_DRAFT:
            raise DocumentEvidenceIntakeError(
                "Document evidence intake requires a DOCUMENT_PACKAGE_DRAFT."
            )
        if artifact.validation_status not in _VALID_STATUSES:
            raise DocumentEvidenceIntakeError(
                "Document evidence intake requires a validated package draft."
            )
        if artifact.evaluation_case_id != context.evaluation_case_id:
            raise DocumentEvidenceIntakeError(
                "Document package draft belongs to another case."
            )
        try:
            package = DocumentPackageDraft.model_validate(artifact.payload)
        except ValidationError as exc:
            raise DocumentEvidenceIntakeError(
                "Invalid Document package draft schema."
            ) from exc
        if (
            package.evaluation_case_id != context.evaluation_case_id
            or package.dataset_id != context.dataset_id
        ):
            raise DocumentEvidenceIntakeError(
                "Document package identity does not match intake execution."
            )
        if package.readiness is not DocumentPackageReadiness.WAITING_FOR_INPUT:
            raise DocumentEvidenceIntakeError(
                "Document package is not waiting for evidence input."
            )
        return artifact, package

    def _build(
        self,
        *,
        context: ExecutionContext,
        command: DocumentEvidenceCommand,
        package_artifact: ArtifactEnvelope,
        package: DocumentPackageDraft,
    ) -> tuple[DocumentEvidenceSupplement, tuple[EvidenceRef, ...]]:
        submission = command.submission
        if submission.workflow_run_id != context.workflow_run_id:
            raise DocumentEvidenceIntakeError(
                "Document submission workflow_run_id does not match execution."
            )
        if submission.missing_request_id != command.allowed_pending_request_id:
            raise DocumentEvidenceIntakeError(
                "Document submission does not resolve the allowed pending request."
            )
        matches = tuple(
            item
            for item in package.missing_data_requests
            if item.request_id == submission.missing_request_id
        )
        if len(matches) != 1:
            raise DocumentEvidenceIntakeError(
                "Submitted missing_request_id is not present exactly once in the package."
            )
        request = matches[0]
        if (
            request.status is not MissingRequestStatus.OPEN
            or request.severity is not MissingSeverity.BLOCKING
            or request.raised_by != "DOCUMENT_SKILL"
            or request.evaluation_case_id != context.evaluation_case_id
            or request.target_record != package.preparation_request_id
            or request.field != submission.document_type.value
        ):
            raise DocumentEvidenceIntakeError(
                "Submitted document type does not match the exact open request."
            )
        redaction = self._redactor.redact(
            submission.evidence_note,
            exact_identifiers={
                "contract_id": package.contract_id,
                "preparation_request_id": package.preparation_request_id,
                "missing_request_id": submission.missing_request_id,
                "document_reference_id": submission.document_reference_id,
            },
        )
        if redaction.text != submission.evidence_note or redaction.findings:
            raise DocumentEvidenceIntakeError(
                "Document evidence_note contains restricted identifiers, secrets, "
                "contact data, URLs, or filesystem paths."
            )
        supplement_id = deterministic_id(
            "DES",
            package.evaluation_case_id,
            package.preparation_request_id,
            package_artifact.artifact_id,
            submission.missing_request_id,
            submission.document_reference_id,
            submission.content_sha256,
            submission.document_type,
            submission.provided_by,
            submission.evidence_note,
        )
        values: tuple[tuple[str, Any], ...] = (
            ("missing_request_id", submission.missing_request_id),
            ("document_reference_id", submission.document_reference_id),
            ("content_sha256", submission.content_sha256),
            ("document_type", submission.document_type.value),
            ("provided_by", submission.provided_by),
            ("evidence_note", submission.evidence_note),
        )
        evidence_refs = tuple(
            self._user_evidence(
                dataset_id=package.dataset_id,
                supplement_id=supplement_id,
                field=field,
                value=value,
            )
            for field, value in values
        )
        supplement = DocumentEvidenceSupplement(
            supplement_id=supplement_id,
            evaluation_case_id=package.evaluation_case_id,
            dataset_id=package.dataset_id,
            contract_id=package.contract_id,
            preparation_request_id=package.preparation_request_id,
            missing_request_id=submission.missing_request_id,
            document_reference_id=submission.document_reference_id,
            content_sha256=submission.content_sha256,
            document_type=submission.document_type,
            provided_by=submission.provided_by,
            evidence_note=submission.evidence_note,
            source_package_artifact_id=package_artifact.artifact_id,
            source_artifact_ids=(package_artifact.artifact_id,),
            evidence_ids=tuple(item.evidence_id for item in evidence_refs),
        )
        return supplement, evidence_refs

    @staticmethod
    def _user_evidence(
        *, dataset_id: str, supplement_id: str, field: str, value: Any
    ) -> EvidenceRef:
        display = json_safe(value)
        return EvidenceRef(
            evidence_id=deterministic_id(
                "EVD", dataset_id, SourceType.USER_INPUT, supplement_id, field, display
            ),
            source_type=SourceType.USER_INPUT,
            sheet="DOCUMENT_EVIDENCE_SUPPLEMENT",
            row_number=0,
            record_id=supplement_id,
            field=field,
            display_value=display,
        )

    @staticmethod
    def _failed_safe(message: str) -> DocumentEvidenceIntakeComponentResult:
        return DocumentEvidenceIntakeComponentResult(
            status=ComponentStatus.FAILED_SAFE,
            runtime_events=(
                RuntimeEvent(
                    event_type="DOCUMENT_EVIDENCE_INTAKE_FAILED_SAFE",
                    message=message,
                ),
            ),
        )
