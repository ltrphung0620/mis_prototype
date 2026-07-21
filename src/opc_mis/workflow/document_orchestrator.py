"""Validate and persist masked internal Document preparation artifacts."""

from opc_mis.business.skills.document.component import DocumentSkill
from opc_mis.domain.artifacts import ArtifactDraft, ArtifactEnvelope
from opc_mis.domain.components import ExecutionContext
from opc_mis.domain.document_models import (
    DocumentChecklist,
    DocumentPackageDraft,
    DocumentReleasePackage,
    DocumentSkillExecutionResult,
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


class DocumentPersistenceError(RuntimeError):
    """Raised when a Document artifact cannot be safely persisted or reused."""


class DocumentOrchestrator:
    """Own validation, persistence, and idempotency for internal package drafts."""

    def __init__(
        self,
        *,
        document: DocumentSkill,
        artifacts: ArtifactRepository,
        evidence_validator: EvidenceValidator | None = None,
        artifact_factory: ArtifactFactory | None = None,
    ) -> None:
        self._document = document
        self._artifacts = artifacts
        self._validator = evidence_validator or EvidenceValidator()
        self._artifact_factory = artifact_factory or ArtifactFactory()

    async def run(self, context: ExecutionContext) -> DocumentSkillExecutionResult:
        """Validate every draft before persisting any Document output."""
        result = await self._document.execute(context)
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

        reports = tuple(
            [await self._validator.validate(draft) for draft in result.artifacts]
        )
        blocking = tuple(
            error
            for report in reports
            if report.status is ValidationStatus.BLOCKED
            for error in report.blocking_errors
        )
        if blocking:
            return self._failed(
                blocking,
                result.warnings,
                events,
                reports=reports,
                checklist=result.checklist,
                package=result.package_draft,
                release=result.release_package,
            )
        try:
            envelopes = tuple(
                [
                    await self._persist_or_reuse(draft, context, report)
                    for draft, report in zip(result.artifacts, reports, strict=True)
                ]
            )
        except DocumentPersistenceError as exc:
            return self._failed(
                (str(exc),),
                result.warnings,
                events,
                reports=reports,
                checklist=result.checklist,
                package=result.package_draft,
                release=result.release_package,
            )

        by_type = {item.artifact_type: item for item in envelopes}
        checklist = DocumentChecklist.model_validate(
            by_type[ArtifactType.DOCUMENT_CHECKLIST].payload
        )
        package = DocumentPackageDraft.model_validate(
            by_type[ArtifactType.DOCUMENT_PACKAGE_DRAFT].payload
        )
        release_artifact = by_type.get(ArtifactType.DOCUMENT_RELEASE_PACKAGE)
        release = (
            DocumentReleasePackage.model_validate(release_artifact.payload)
            if release_artifact is not None
            else None
        )
        workflow_status = (
            WorkflowStatus.WAITING_FOR_INPUT
            if result.status is ComponentStatus.WAITING_FOR_INPUT
            else WorkflowStatus.COMPLETED
        )
        return DocumentSkillExecutionResult(
            status=workflow_status,
            component_status=result.status,
            current_node=WorkflowNode.DOCUMENT_PREPARATION.value,
            checklist=checklist,
            package_draft=package,
            release_package=release,
            generated_artifacts=envelopes,
            validation_reports=reports,
            missing_data_requests=result.missing_data_requests,
            warnings=result.warnings,
            runtime_events=events,
        )

    @staticmethod
    def _contract_errors(
        result: object, context: ExecutionContext
    ) -> tuple[str, ...]:
        checklist = getattr(result, "checklist", None)
        package = getattr(result, "package_draft", None)
        release = getattr(result, "release_package", None)
        drafts = tuple(getattr(result, "artifacts", ()))
        if not isinstance(checklist, DocumentChecklist) or not isinstance(
            package, DocumentPackageDraft
        ):
            return ("Document Skill must return a typed checklist and package draft.",)
        expected_types = (
            ArtifactType.DOCUMENT_CHECKLIST,
            ArtifactType.DOCUMENT_PACKAGE_DRAFT,
            *((ArtifactType.DOCUMENT_RELEASE_PACKAGE,) if release is not None else ()),
        )
        actual_types = tuple(item.artifact_type for item in drafts)
        if actual_types != expected_types or len(set(actual_types)) != len(actual_types):
            return ("Document Skill returned an invalid artifact draft set.",)
        typed_values = (checklist, package, *((release,) if release is not None else ()))
        if any(
            draft.payload != value.model_dump(mode="json")
            for draft, value in zip(drafts, typed_values, strict=True)
        ):
            return ("Document typed outputs differ from their artifact drafts.",)
        if (
            checklist.source_artifact_ids != context.input_artifact_ids
            or package.source_artifact_ids != context.input_artifact_ids
            or (
                release is not None
                and release.source_artifact_ids != context.input_artifact_ids
            )
        ):
            return (
                "Document output lineage differs from the exact execution inputs.",
            )
        if (
            package.checklist_id != checklist.checklist_id
            or package.approval_condition_codes
            != checklist.approval_condition_codes
            or package.limitation_codes != checklist.limitation_codes
            or (
                release is not None
                and (
                    release.checklist_id != checklist.checklist_id
                    or release.package_draft_id != package.package_draft_id
                    or release.approval_condition_codes
                    != checklist.approval_condition_codes
                    or release.limitation_codes != checklist.limitation_codes
                    or tuple(
                        item.checklist_item_id
                        for item in release.document_manifest
                    )
                    != tuple(item.item_id for item in checklist.items)
                )
            )
        ):
            return (
                "Document checklist, package, conditions, and limitations differ.",
            )
        missing = tuple(getattr(result, "missing_data_requests", ()))
        if missing != package.missing_data_requests:
            return ("Document missing-data requests differ from its package draft.",)
        waiting = getattr(result, "status", None) is ComponentStatus.WAITING_FOR_INPUT
        if waiting != bool(missing) or waiting == (release is not None):
            return ("Document readiness, missing inputs, and release package disagree.",)
        if getattr(result, "approval_signals", ()) or getattr(
            result, "action_commands", ()
        ):
            return ("Document Skill cannot approve or release its package.",)
        return ()

    async def _persist_or_reuse(
        self,
        draft: ArtifactDraft,
        context: ExecutionContext,
        report: ValidationReport,
    ) -> ArtifactEnvelope:
        existing = await self._artifacts.list_by_case(draft.evaluation_case_id)
        input_hash = artifact_input_hash(draft, context)
        matches = tuple(
            item
            for item in existing
            if item.artifact_type is draft.artifact_type
            and item.input_hash == input_hash
        )
        if len(matches) > 1:
            raise DocumentPersistenceError(
                f"{draft.artifact_type.value} identity is ambiguous."
            )
        if matches:
            current = matches[0]
            if (
                current.validation_status
                not in {
                    ValidationStatus.VALID,
                    ValidationStatus.VALID_WITH_WARNINGS,
                }
                or current.payload != draft.payload
                or current.evidence_refs != draft.evidence_refs
                or current.input_artifact_ids != context.input_artifact_ids
            ):
                raise DocumentPersistenceError(
                    f"Existing {draft.artifact_type.value} differs from its inputs."
                )
            return current
        version = 1 + max(
            (
                item.version
                for item in existing
                if item.artifact_type is draft.artifact_type
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
    def _failed(
        errors: tuple[str, ...],
        warnings: tuple[str, ...],
        events: tuple[dict[str, object], ...],
        *,
        reports: tuple[ValidationReport, ...] = (),
        checklist: DocumentChecklist | None = None,
        package: DocumentPackageDraft | None = None,
        release: DocumentReleasePackage | None = None,
    ) -> DocumentSkillExecutionResult:
        return DocumentSkillExecutionResult(
            status=WorkflowStatus.FAILED_SAFE,
            component_status=ComponentStatus.FAILED_SAFE,
            current_node=WorkflowNode.DOCUMENT_PREPARATION.value,
            checklist=checklist,
            package_draft=package,
            release_package=release,
            validation_reports=reports,
            validation_errors=errors,
            warnings=warnings,
            runtime_events=events,
        )
