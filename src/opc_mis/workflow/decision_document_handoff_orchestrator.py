"""Validate and persist Decision's provider-result-to-Document handoff."""

from opc_mis.business.agents.decision.document_handoff_component import (
    DecisionDocumentHandoff,
)
from opc_mis.domain.artifacts import ArtifactDraft, ArtifactEnvelope
from opc_mis.domain.components import ExecutionContext
from opc_mis.domain.document_models import (
    DecisionDocumentHandoffExecutionResult,
    DocumentPreparationRequest,
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


class DecisionDocumentHandoffPersistenceError(RuntimeError):
    """Raised when a handoff artifact cannot be reused without ambiguity."""


class DecisionDocumentHandoffOrchestrator:
    """Own validation, persistence, and idempotency for Document requests."""

    def __init__(
        self,
        *,
        handoff: DecisionDocumentHandoff,
        artifacts: ArtifactRepository,
        evidence_validator: EvidenceValidator | None = None,
        artifact_factory: ArtifactFactory | None = None,
    ) -> None:
        self._handoff = handoff
        self._artifacts = artifacts
        self._validator = evidence_validator or EvidenceValidator()
        self._artifact_factory = artifact_factory or ArtifactFactory()

    async def run(
        self, context: ExecutionContext
    ) -> DecisionDocumentHandoffExecutionResult:
        """Persist every valid request only after all drafts pass validation."""
        result = await self._handoff.execute(context)
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
                requests=result.preparation_requests,
            )
        try:
            envelopes = tuple(
                [
                    await self._persist_or_reuse(draft, context, report)
                    for draft, report in zip(result.artifacts, reports, strict=True)
                ]
            )
        except DecisionDocumentHandoffPersistenceError as exc:
            return self._failed(
                (str(exc),),
                result.warnings,
                events,
                reports=reports,
                requests=result.preparation_requests,
            )
        requests = tuple(
            DocumentPreparationRequest.model_validate(item.payload)
            for item in envelopes
        )
        return DecisionDocumentHandoffExecutionResult(
            status=WorkflowStatus.COMPLETED,
            component_status=result.status,
            current_node=WorkflowNode.DECISION_DOCUMENT_HANDOFF.value,
            preparation_requests=requests,
            generated_artifacts=envelopes,
            validation_reports=reports,
            warnings=result.warnings,
            runtime_events=events,
        )

    @staticmethod
    def _contract_errors(
        result: object, context: ExecutionContext
    ) -> tuple[str, ...]:
        requests = tuple(getattr(result, "preparation_requests", ()))
        drafts = tuple(getattr(result, "artifacts", ()))
        if not requests:
            return (
                "Decision Document handoff must return at least one conditional request.",
            )
        if len(drafts) != len(requests) or any(
            item.artifact_type is not ArtifactType.DOCUMENT_PREPARATION_REQUEST
            for item in drafts
        ):
            return (
                "Decision Document handoff must return one request draft per typed request.",
            )
        if any(
            draft.payload != request.model_dump(mode="json")
            for request, draft in zip(requests, drafts, strict=True)
        ):
            return ("Document request values differ from their artifact drafts.",)
        if any(
            request.source_artifact_ids != context.input_artifact_ids
            for request in requests
        ):
            return (
                "Document request lineage differs from the exact execution inputs.",
            )
        if getattr(result, "missing_data_requests", ()):
            return ("Decision Document handoff cannot raise document-input gaps.",)
        if getattr(result, "approval_signals", ()) or getattr(
            result, "action_commands", ()
        ):
            return (
                "Decision Document handoff cannot approve or release documents.",
            )
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
            raise DecisionDocumentHandoffPersistenceError(
                "Document handoff artifact identity is ambiguous."
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
                raise DecisionDocumentHandoffPersistenceError(
                    "Existing Document request differs from its exact validated inputs."
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
        requests: tuple[DocumentPreparationRequest, ...] = (),
    ) -> DecisionDocumentHandoffExecutionResult:
        return DecisionDocumentHandoffExecutionResult(
            status=WorkflowStatus.FAILED_SAFE,
            component_status=ComponentStatus.FAILED_SAFE,
            current_node=WorkflowNode.DECISION_DOCUMENT_HANDOFF.value,
            preparation_requests=requests,
            validation_reports=reports,
            validation_errors=errors,
            warnings=warnings,
            runtime_events=events,
        )
