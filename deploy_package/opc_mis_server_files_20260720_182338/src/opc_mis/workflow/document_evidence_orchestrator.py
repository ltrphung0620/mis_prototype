"""Validation and persistence for reference-only Document evidence intake."""

from pydantic import ValidationError

from opc_mis.business.skills.document.evidence_intake import DocumentEvidenceIntake
from opc_mis.domain.artifacts import ArtifactDraft, ArtifactEnvelope
from opc_mis.domain.components import ExecutionContext
from opc_mis.domain.document_models import (
    DocumentEvidenceExecutionResult,
    DocumentEvidenceSupplement,
)
from opc_mis.domain.enums import (
    ArtifactType,
    ComponentStatus,
    ValidationStatus,
    WorkflowStatus,
)
from opc_mis.domain.validation_reports import ValidationReport
from opc_mis.domain.workflow import WorkflowNode
from opc_mis.governance.evidence_validator import EvidenceValidator
from opc_mis.ports.artifact_repository import ArtifactRepository
from opc_mis.workflow.artifact_factory import ArtifactFactory, artifact_input_hash


class DocumentEvidencePersistenceError(RuntimeError):
    """Raised when a supplement retry conflicts with accepted evidence metadata."""


class DocumentEvidenceOrchestrator:
    """Validate before persisting an immutable, metadata-only supplement."""

    def __init__(
        self,
        *,
        intake: DocumentEvidenceIntake,
        artifacts: ArtifactRepository,
        evidence_validator: EvidenceValidator | None = None,
        artifact_factory: ArtifactFactory | None = None,
    ) -> None:
        self._intake = intake
        self._artifacts = artifacts
        self._validator = evidence_validator or EvidenceValidator()
        self._artifact_factory = artifact_factory or ArtifactFactory()

    async def run(
        self, context: ExecutionContext
    ) -> DocumentEvidenceExecutionResult:
        """Persist one validated server-reference supplement or fail closed."""
        result = await self._intake.execute(context)
        events = tuple(item.model_dump(mode="json") for item in result.runtime_events)
        if result.status is ComponentStatus.FAILED_SAFE:
            return self._failed(
                tuple(item.message for item in result.runtime_events),
                result.warnings,
                events,
            )
        errors = self._contract_errors(result, context)
        if errors:
            return self._failed(errors, result.warnings, events)
        supplement = result.supplement
        draft = result.artifacts[0]
        if supplement is None:  # pragma: no cover - contract guard above
            return self._failed(
                ("Document evidence intake returned no supplement.",),
                result.warnings,
                events,
            )
        report = await self._validator.validate(draft)
        if report.status is ValidationStatus.BLOCKED:
            return self._failed(
                report.blocking_errors,
                result.warnings,
                events,
                reports=(report,),
                supplement=supplement,
            )
        try:
            envelope = await self._persist_or_reuse(
                draft=draft,
                context=context,
                report=report,
                supplement=supplement,
            )
        except DocumentEvidencePersistenceError as exc:
            return self._failed(
                (str(exc),),
                result.warnings,
                events,
                reports=(report,),
                supplement=supplement,
            )
        persisted = DocumentEvidenceSupplement.model_validate(envelope.payload)
        return DocumentEvidenceExecutionResult(
            status=WorkflowStatus.COMPLETED,
            component_status=result.status,
            current_node=WorkflowNode.DOCUMENT_INPUT_INTAKE.value,
            supplement=persisted,
            generated_artifacts=(envelope,),
            validation_reports=(report,),
            warnings=result.warnings,
            runtime_events=events,
        )

    @staticmethod
    def _contract_errors(
        result: object, context: ExecutionContext
    ) -> tuple[str, ...]:
        supplement = getattr(result, "supplement", None)
        drafts = tuple(getattr(result, "artifacts", ()))
        if not isinstance(supplement, DocumentEvidenceSupplement):
            return ("Document evidence intake must return a typed supplement.",)
        if len(drafts) != 1 or (
            drafts[0].artifact_type is not ArtifactType.DOCUMENT_EVIDENCE_SUPPLEMENT
        ):
            return ("Document evidence intake must return exactly one draft.",)
        if drafts[0].payload != supplement.model_dump(mode="json"):
            return ("Document evidence supplement and draft disagree.",)
        if tuple(item.evidence_id for item in drafts[0].evidence_refs) != (
            supplement.evidence_ids
        ):
            return ("Document supplement evidence index differs from its draft.",)
        if supplement.source_artifact_ids != context.input_artifact_ids:
            return (
                "Document supplement lineage differs from the exact package input.",
            )
        if getattr(result, "missing_data_requests", ()):
            return ("Document evidence intake cannot raise replacement data gaps.",)
        if getattr(result, "approval_signals", ()) or getattr(
            result, "action_commands", ()
        ):
            return ("Document evidence intake cannot authorize external release.",)
        return ()

    async def _persist_or_reuse(
        self,
        *,
        draft: ArtifactDraft,
        context: ExecutionContext,
        report: ValidationReport,
        supplement: DocumentEvidenceSupplement,
    ) -> ArtifactEnvelope:
        existing = await self._artifacts.list_by_case(draft.evaluation_case_id)
        current = self._current_for_request(
            existing,
            preparation_request_id=supplement.preparation_request_id,
            missing_request_id=supplement.missing_request_id,
        )
        input_hash = artifact_input_hash(draft, context)
        if current is not None:
            if (
                current.input_hash != input_hash
                or current.payload != draft.payload
                or current.evidence_refs != draft.evidence_refs
                or current.input_artifact_ids != context.input_artifact_ids
                or current.validation_status
                not in {
                    ValidationStatus.VALID,
                    ValidationStatus.VALID_WITH_WARNINGS,
                }
            ):
                raise DocumentEvidencePersistenceError(
                    "This Document request already has different accepted evidence metadata."
                )
            return current
        version = 1 + max(
            (
                item.version
                for item in existing
                if item.artifact_type
                is ArtifactType.DOCUMENT_EVIDENCE_SUPPLEMENT
            ),
            default=0,
        )
        envelope = self._artifact_factory.create(
            draft=draft,
            context=context,
            validation_report=report,
            version=version,
        )
        await self._artifacts.save(envelope)
        return envelope

    @staticmethod
    def _current_for_request(
        artifacts: tuple[ArtifactEnvelope, ...],
        *,
        preparation_request_id: str,
        missing_request_id: str,
    ) -> ArtifactEnvelope | None:
        matches: list[ArtifactEnvelope] = []
        for artifact in artifacts:
            if (
                artifact.artifact_type
                is not ArtifactType.DOCUMENT_EVIDENCE_SUPPLEMENT
            ):
                continue
            try:
                supplement = DocumentEvidenceSupplement.model_validate(
                    artifact.payload
                )
            except ValidationError as exc:
                raise DocumentEvidencePersistenceError(
                    "Stored Document evidence supplement has an invalid schema."
                ) from exc
            if (
                supplement.preparation_request_id == preparation_request_id
                and supplement.missing_request_id == missing_request_id
            ):
                matches.append(artifact)
        if len(matches) > 1:
            raise DocumentEvidencePersistenceError(
                "Current Document evidence supplement is ambiguous."
            )
        return matches[0] if matches else None

    @staticmethod
    def _failed(
        errors: tuple[str, ...],
        warnings: tuple[str, ...],
        events: tuple[dict[str, object], ...],
        *,
        reports: tuple[ValidationReport, ...] = (),
        supplement: DocumentEvidenceSupplement | None = None,
    ) -> DocumentEvidenceExecutionResult:
        return DocumentEvidenceExecutionResult(
            status=WorkflowStatus.FAILED_SAFE,
            component_status=ComponentStatus.FAILED_SAFE,
            current_node=WorkflowNode.DOCUMENT_INPUT_INTAKE.value,
            supplement=supplement,
            validation_reports=reports,
            validation_errors=errors,
            warnings=warnings,
            runtime_events=events,
        )
