"""Validate and persist post-Decision artifacts; stop before external execution."""

from __future__ import annotations

from opc_mis.business.agents.decision.post_decision_component import (
    ExternalDocumentSubmissionProposalComponent,
    ExternalSubmissionReadinessComponent,
    PostDecisionUpdateComponent,
)
from opc_mis.domain.artifacts import ArtifactDraft, ArtifactEnvelope
from opc_mis.domain.components import ComponentResult, ExecutionContext
from opc_mis.domain.enums import (
    ArtifactType,
    ComponentStatus,
    ValidationStatus,
    WorkflowStatus,
)
from opc_mis.domain.post_decision_models import (
    ExternalDocumentSubmissionProposal,
    ExternalDocumentSubmissionProposalExecutionResult,
    ExternalSubmissionReadinessExecutionResult,
    PostDecisionUpdate,
    PostDecisionUpdateExecutionResult,
)
from opc_mis.domain.validation_reports import ValidationReport
from opc_mis.domain.workflow import WorkflowNode
from opc_mis.governance.evidence_validator import EvidenceValidator
from opc_mis.ports.artifact_repository import ArtifactRepository
from opc_mis.workflow.artifact_factory import ArtifactFactory, artifact_input_hash


class PostDecisionPersistenceError(RuntimeError):
    """Raised when a post-Decision artifact cannot be safely reused."""


class PostDecisionOrchestrator:
    """Own validation, versioning, persistence, and execution-only readiness."""

    def __init__(
        self,
        *,
        update_component: PostDecisionUpdateComponent,
        proposal_component: ExternalDocumentSubmissionProposalComponent,
        readiness_component: ExternalSubmissionReadinessComponent,
        artifacts: ArtifactRepository,
        evidence_validator: EvidenceValidator | None = None,
        artifact_factory: ArtifactFactory | None = None,
    ) -> None:
        self._update_component = update_component
        self._proposal_component = proposal_component
        self._readiness_component = readiness_component
        self._artifacts = artifacts
        self._validator = evidence_validator or EvidenceValidator()
        self._artifact_factory = artifact_factory or ArtifactFactory()

    async def run_update(
        self, context: ExecutionContext
    ) -> PostDecisionUpdateExecutionResult:
        """Persist the exact route selected by an approved Decision Card."""
        result = await self._update_component.execute(context)
        events = self._events(result)
        errors = self._artifact_contract_errors(
            result=result,
            context=context,
            artifact_type=ArtifactType.POST_DECISION_UPDATE,
            typed_value=result.update,
            expected_direct_input_count=1,
        )
        if (
            result.update is not None
            and context.input_artifact_ids
            and result.update.decision_card_artifact.artifact_id
            != context.input_artifact_ids[0]
        ):
            errors = (*errors, "Post-decision update binds another Decision Card.")
        if errors or result.update is None or not result.artifacts:
            return PostDecisionUpdateExecutionResult(
                status=WorkflowStatus.FAILED_SAFE,
                component_status=ComponentStatus.FAILED_SAFE,
                current_node=WorkflowNode.POST_DECISION_UPDATE.value,
                update=result.update,
                validation_errors=errors or ("Post-decision update failed safely.",),
                warnings=result.warnings,
                runtime_events=events,
            )
        report, envelope, failure = await self._validate_and_persist(
            result.artifacts[0], context
        )
        if failure is not None or envelope is None:
            return PostDecisionUpdateExecutionResult(
                status=WorkflowStatus.FAILED_SAFE,
                component_status=ComponentStatus.FAILED_SAFE,
                current_node=WorkflowNode.POST_DECISION_UPDATE.value,
                update=result.update,
                validation_reports=(report,),
                validation_errors=(failure or "Post-decision persistence failed.",),
                warnings=result.warnings,
                runtime_events=events,
            )
        update = PostDecisionUpdate.model_validate(envelope.payload)
        return PostDecisionUpdateExecutionResult(
            status=WorkflowStatus.COMPLETED,
            component_status=result.status,
            current_node=WorkflowNode.POST_DECISION_UPDATE.value,
            update=update,
            generated_artifacts=(envelope,),
            validation_reports=(report,),
            warnings=result.warnings,
            runtime_events=events,
        )

    async def run_external_proposal(
        self, context: ExecutionContext
    ) -> ExternalDocumentSubmissionProposalExecutionResult:
        """Persist an exact protected-action proposal, without requesting approval."""
        result = await self._proposal_component.execute(context)
        events = self._events(result)
        errors = self._artifact_contract_errors(
            result=result,
            context=context,
            artifact_type=ArtifactType.EXTERNAL_DOCUMENT_SUBMISSION_PROPOSAL,
            typed_value=result.proposal,
            expected_direct_input_count=3,
        )
        if (
            result.proposal is not None
            and context.input_artifact_ids
            and result.proposal.post_decision_update_artifact.artifact_id
            != context.input_artifact_ids[0]
        ):
            errors = (
                *errors,
                "External submission proposal binds another post-decision update.",
            )
        if errors or result.proposal is None or not result.artifacts:
            return ExternalDocumentSubmissionProposalExecutionResult(
                status=WorkflowStatus.FAILED_SAFE,
                component_status=ComponentStatus.FAILED_SAFE,
                current_node=WorkflowNode.EXTERNAL_DOCUMENT_SUBMISSION_PROPOSAL.value,
                proposal=result.proposal,
                validation_errors=errors
                or ("External submission proposal failed safely.",),
                warnings=result.warnings,
                runtime_events=events,
            )
        report, envelope, failure = await self._validate_and_persist(
            result.artifacts[0], context
        )
        if failure is not None or envelope is None:
            return ExternalDocumentSubmissionProposalExecutionResult(
                status=WorkflowStatus.FAILED_SAFE,
                component_status=ComponentStatus.FAILED_SAFE,
                current_node=WorkflowNode.EXTERNAL_DOCUMENT_SUBMISSION_PROPOSAL.value,
                proposal=result.proposal,
                validation_reports=(report,),
                validation_errors=(failure or "External proposal persistence failed.",),
                warnings=result.warnings,
                runtime_events=events,
            )
        proposal = ExternalDocumentSubmissionProposal.model_validate(envelope.payload)
        return ExternalDocumentSubmissionProposalExecutionResult(
            status=WorkflowStatus.COMPLETED,
            component_status=result.status,
            current_node=WorkflowNode.EXTERNAL_DOCUMENT_SUBMISSION_PROPOSAL.value,
            proposal=proposal,
            generated_artifacts=(envelope,),
            validation_reports=(report,),
            warnings=result.warnings,
            runtime_events=events,
        )

    async def run_external_readiness(
        self, context: ExecutionContext
    ) -> ExternalSubmissionReadinessExecutionResult:
        """Return an execution-only readiness proof after exact authorization."""
        result = await self._readiness_component.execute(context)
        events = self._events(result)
        errors: list[str] = []
        if result.status not in {
            ComponentStatus.COMPLETED,
            ComponentStatus.COMPLETED_WITH_WARNINGS,
        }:
            errors.append("External submission readiness did not complete.")
        if len(context.input_artifact_ids) != 1:
            errors.append("External submission readiness requires one proposal input.")
        if result.readiness is None:
            errors.append("External submission readiness returned no typed proof.")
        elif context.input_artifact_ids and (
            result.readiness.proposal_artifact.artifact_id
            != context.input_artifact_ids[0]
        ):
            errors.append("External readiness binds another proposal.")
        if result.artifacts:
            errors.append("External readiness must not create a receipt artifact.")
        if (
            result.missing_data_requests
            or result.approval_signals
            or result.action_commands
        ):
            errors.append("External readiness exceeds its execution-only boundary.")
        if errors:
            return ExternalSubmissionReadinessExecutionResult(
                status=WorkflowStatus.FAILED_SAFE,
                component_status=ComponentStatus.FAILED_SAFE,
                current_node=WorkflowNode.READY_FOR_EXTERNAL_SUBMISSION.value,
                readiness=result.readiness,
                validation_errors=tuple(errors),
                warnings=result.warnings,
                runtime_events=events,
            )
        return ExternalSubmissionReadinessExecutionResult(
            status=WorkflowStatus.COMPLETED,
            component_status=result.status,
            current_node=WorkflowNode.READY_FOR_EXTERNAL_SUBMISSION.value,
            readiness=result.readiness,
            warnings=result.warnings,
            runtime_events=events,
        )

    @staticmethod
    def _artifact_contract_errors(
        *,
        result: ComponentResult,
        context: ExecutionContext,
        artifact_type: ArtifactType,
        typed_value: PostDecisionUpdate | ExternalDocumentSubmissionProposal | None,
        expected_direct_input_count: int,
    ) -> tuple[str, ...]:
        errors: list[str] = []
        if result.status not in {
            ComponentStatus.COMPLETED,
            ComponentStatus.COMPLETED_WITH_WARNINGS,
        }:
            errors.append(f"{artifact_type.value} component did not complete.")
        if len(context.input_artifact_ids) != expected_direct_input_count:
            errors.append(
                f"{artifact_type.value} requires exactly "
                f"{expected_direct_input_count} direct input artifact(s)."
            )
        if typed_value is None:
            errors.append(f"{artifact_type.value} returned no typed payload.")
        if len(result.artifacts) != 1 or result.artifacts[0].artifact_type is not artifact_type:
            errors.append(f"{artifact_type.value} must return exactly one draft.")
        elif typed_value is not None and result.artifacts[0].payload != typed_value.model_dump(
            mode="json"
        ):
            errors.append(f"{artifact_type.value} typed payload and draft disagree.")
        if typed_value is not None and (
            typed_value.evaluation_case_id != context.evaluation_case_id
            or typed_value.dataset_id != context.dataset_id
        ):
            errors.append(f"{artifact_type.value} belongs to another scope.")
        if (
            result.missing_data_requests
            or result.approval_signals
            or result.action_commands
        ):
            errors.append(f"{artifact_type.value} exceeds its business-component boundary.")
        return tuple(errors)

    async def _validate_and_persist(
        self,
        draft: ArtifactDraft,
        context: ExecutionContext,
    ) -> tuple[ValidationReport, ArtifactEnvelope | None, str | None]:
        report = await self._validator.validate(draft)
        if report.status is ValidationStatus.BLOCKED:
            return (
                report,
                None,
                "; ".join(report.blocking_errors)
                or "Evidence Validator blocked the artifact.",
            )
        try:
            envelope = await self._persist_or_reuse(draft, context, report)
        except PostDecisionPersistenceError as exc:
            return report, None, str(exc)
        return report, envelope, None

    async def _persist_or_reuse(
        self,
        draft: ArtifactDraft,
        context: ExecutionContext,
        report: ValidationReport,
    ) -> ArtifactEnvelope:
        artifacts = await self._artifacts.list_by_case(draft.evaluation_case_id)
        expected_hash = artifact_input_hash(draft, context)
        matches = tuple(
            item
            for item in artifacts
            if item.artifact_type is draft.artifact_type
            and item.input_hash == expected_hash
        )
        if len(matches) > 1:
            raise PostDecisionPersistenceError(
                f"{draft.artifact_type.value} artifact identity is ambiguous."
            )
        if matches:
            existing = matches[0]
            if (
                existing.payload != draft.payload
                or existing.evidence_refs != draft.evidence_refs
                or existing.input_artifact_ids != context.input_artifact_ids
                or existing.validation_status
                not in {ValidationStatus.VALID, ValidationStatus.VALID_WITH_WARNINGS}
            ):
                raise PostDecisionPersistenceError(
                    f"Existing {draft.artifact_type.value} artifact is not reusable."
                )
            return existing
        version = 1 + max(
            (
                item.version
                for item in artifacts
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
    def _events(result: ComponentResult) -> tuple[dict[str, object], ...]:
        return tuple(item.model_dump(mode="json") for item in result.runtime_events)
