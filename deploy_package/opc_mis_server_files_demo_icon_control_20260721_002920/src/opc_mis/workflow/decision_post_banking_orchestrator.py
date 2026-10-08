"""Workflow validation and persistence for Decision post-Banking review."""

from opc_mis.business.agents.decision.post_banking_component import (
    DecisionPostBankingReviewer,
)
from opc_mis.domain.artifacts import ArtifactDraft, ArtifactEnvelope
from opc_mis.domain.components import ExecutionContext
from opc_mis.domain.decision_post_banking_models import (
    DecisionPostBankingExecutionResult,
    DecisionPostBankingReview,
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


class DecisionPostBankingPersistenceError(RuntimeError):
    """Raised when a same-hash review artifact is not an exact validated match."""


class DecisionPostBankingOrchestrator:
    """Persist Decision's route review, including durable missing-data requests."""

    def __init__(
        self,
        *,
        reviewer: DecisionPostBankingReviewer,
        artifacts: ArtifactRepository,
        evidence_validator: EvidenceValidator | None = None,
        artifact_factory: ArtifactFactory | None = None,
    ) -> None:
        self._reviewer = reviewer
        self._artifacts = artifacts
        self._validator = evidence_validator or EvidenceValidator()
        self._artifact_factory = artifact_factory or ArtifactFactory()

    async def run(self, context: ExecutionContext) -> DecisionPostBankingExecutionResult:
        """Validate and persist the review even when it requests a workflow pause."""
        result = await self._reviewer.execute(context)
        events = tuple(item.model_dump(mode="json") for item in result.runtime_events)
        if result.status is ComponentStatus.FAILED_SAFE:
            return self._failed(
                tuple(item.message for item in result.runtime_events),
                result.warnings,
                events,
            )
        errors = self._contract_errors(result)
        if errors:
            return self._failed(errors, result.warnings, events)
        review = result.review
        draft = result.artifacts[0]
        if review is None:  # pragma: no cover - guarded by contract validation
            return self._failed(
                ("Decision post-Banking review returned no typed output.",),
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
                review=review,
            )
        try:
            envelope = await self._persist_or_reuse(draft, context, report)
        except DecisionPostBankingPersistenceError as exc:
            return self._failed(
                (str(exc),),
                result.warnings,
                events,
                reports=(report,),
                review=review,
            )
        persisted = DecisionPostBankingReview.model_validate(envelope.payload)
        workflow_status = (
            WorkflowStatus.WAITING_FOR_INPUT
            if result.status is ComponentStatus.WAITING_FOR_INPUT
            else WorkflowStatus.COMPLETED
        )
        return DecisionPostBankingExecutionResult(
            status=workflow_status,
            component_status=result.status,
            current_node=WorkflowNode.DECISION_POST_BANKING_REVIEW.value,
            review=persisted,
            generated_artifacts=(envelope,),
            validation_reports=(report,),
            missing_data_requests=persisted.missing_data_requests,
            warnings=result.warnings,
            runtime_events=events,
        )

    @staticmethod
    def _contract_errors(result: object) -> tuple[str, ...]:
        review = getattr(result, "review", None)
        artifacts = getattr(result, "artifacts", ())
        if review is None:
            return ("Decision post-Banking review must return a typed review.",)
        if len(artifacts) != 1 or (
            artifacts[0].artifact_type
            is not ArtifactType.DECISION_POST_BANKING_REVIEW
        ):
            return ("Decision post-Banking must return exactly one review draft.",)
        if artifacts[0].payload != review.model_dump(mode="json"):
            return ("Decision post-Banking review and artifact draft disagree.",)
        if tuple(getattr(result, "missing_data_requests", ())) != tuple(
            review.missing_data_requests
        ):
            return (
                "Decision post-Banking result and durable missing requests disagree.",
            )
        if getattr(result, "approval_signals", ()) or getattr(
            result, "action_commands", ()
        ):
            return (
                "Decision post-Banking review cannot emit approvals or action commands.",
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
        current = next(
            (
                item
                for item in existing
                if item.artifact_type is draft.artifact_type
                and item.input_hash == input_hash
            ),
            None,
        )
        if current is not None:
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
                raise DecisionPostBankingPersistenceError(
                    "Existing Decision post-Banking artifact does not match its "
                    "exact validated business inputs."
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
        review: DecisionPostBankingReview | None = None,
    ) -> DecisionPostBankingExecutionResult:
        return DecisionPostBankingExecutionResult(
            status=WorkflowStatus.FAILED_SAFE,
            component_status=ComponentStatus.FAILED_SAFE,
            current_node=WorkflowNode.DECISION_POST_BANKING_REVIEW.value,
            review=review,
            validation_reports=reports,
            validation_errors=errors,
            warnings=warnings,
            runtime_events=events,
        )
