"""Application service orchestrating Dataset-ready Planner intake."""

from opc_mis.business.skills.planner.component import PlannerSkill
from opc_mis.domain.artifacts import ArtifactDraft, ArtifactEnvelope
from opc_mis.domain.components import ExecutionContext
from opc_mis.domain.enums import ComponentStatus, ValidationStatus, WorkflowStatus
from opc_mis.domain.planner_models import PlannerExecutionResult, PlannerResult
from opc_mis.domain.validation_reports import ValidationReport
from opc_mis.domain.workflow import WorkflowNode, WorkflowRunState
from opc_mis.governance.evidence_validator import EvidenceValidator
from opc_mis.ports.artifact_repository import ArtifactRepository
from opc_mis.ports.workflow_repository import WorkflowStateRepository
from opc_mis.workflow.artifact_factory import ArtifactFactory, artifact_input_hash


class PlannerIntakeOrchestrator:
    """Validate and persist Planner outputs while owning pause/next-node state."""

    def __init__(
        self,
        *,
        planner: PlannerSkill,
        artifact_repository: ArtifactRepository,
        workflow_repository: WorkflowStateRepository,
        evidence_validator: EvidenceValidator | None = None,
        artifact_factory: ArtifactFactory | None = None,
    ) -> None:
        self._planner = planner
        self._artifact_repository = artifact_repository
        self._workflow_repository = workflow_repository
        self._evidence_validator = evidence_validator or EvidenceValidator()
        self._artifact_factory = artifact_factory or ArtifactFactory()

    async def run_planner(self, context: ExecutionContext) -> PlannerExecutionResult:
        """Run Planner, validate drafts, persist envelopes, and select workflow state."""
        component_result = await self._planner.execute(context)
        if component_result.status is ComponentStatus.FAILED_SAFE:
            errors = tuple(event.message for event in component_result.runtime_events)
            await self._persist_state(
                context=context,
                planner_result=component_result.planner_result,
                status=WorkflowStatus.FAILED_SAFE,
                current_node=context.current_node,
                blocked_reason="; ".join(errors) or "Planner failed safe.",
            )
            return PlannerExecutionResult(
                status=WorkflowStatus.FAILED_SAFE,
                component_status=component_result.status,
                current_node=context.current_node,
                planner_result=component_result.planner_result,
                generated_artifacts=(),
                validation_errors=errors,
            )

        reports: list[ValidationReport] = []
        envelopes: list[ArtifactEnvelope] = []
        for draft in component_result.artifacts:
            report = await self._evidence_validator.validate(draft)
            reports.append(report)
            if report.status is ValidationStatus.BLOCKED:
                await self._persist_state(
                    context=context,
                    planner_result=component_result.planner_result,
                    status=WorkflowStatus.FAILED_SAFE,
                    current_node=context.current_node,
                    blocked_reason="; ".join(report.blocking_errors),
                )
                return PlannerExecutionResult(
                    status=WorkflowStatus.FAILED_SAFE,
                    component_status=ComponentStatus.FAILED_SAFE,
                    current_node=context.current_node,
                    planner_result=component_result.planner_result,
                    generated_artifacts=(),
                    validation_reports=tuple(reports),
                    validation_errors=report.blocking_errors,
                )
            envelope = await self._persist_or_reuse(draft, context, report)
            envelopes.append(envelope)

        waiting = component_result.status is ComponentStatus.WAITING_FOR_INPUT
        workflow_status = WorkflowStatus.WAITING_FOR_INPUT if waiting else WorkflowStatus.COMPLETED
        current_node = (
            WorkflowNode.PLANNER_INTAKE.value if waiting else WorkflowNode.INITIAL_ASSESSMENT.value
        )
        await self._persist_state(
            context=context,
            planner_result=component_result.planner_result,
            status=workflow_status,
            current_node=current_node,
            pending_request_ids=tuple(
                request.request_id for request in component_result.missing_data_requests
            ),
            blocked_reason=(
                "Planner requires blocking base data before initial assessment."
                if waiting
                else None
            ),
        )
        return PlannerExecutionResult(
            status=workflow_status,
            component_status=component_result.status,
            current_node=current_node,
            planner_result=component_result.planner_result,
            generated_artifacts=tuple(envelopes),
            validation_reports=tuple(reports),
        )

    async def _persist_state(
        self,
        *,
        context: ExecutionContext,
        planner_result: PlannerResult | None,
        status: WorkflowStatus,
        current_node: str,
        pending_request_ids: tuple[str, ...] = (),
        blocked_reason: str | None = None,
    ) -> None:
        evaluation_case = planner_result.evaluation_case if planner_result else None
        evaluation_case_id = evaluation_case.evaluation_case_id if evaluation_case else None
        missing = planner_result.missing_data_requests if planner_result else ()
        if evaluation_case_id is None and missing:
            evaluation_case_id = missing[0].evaluation_case_id
        blocked = status in {
            WorkflowStatus.WAITING_FOR_INPUT,
            WorkflowStatus.FAILED_SAFE,
        }
        await self._workflow_repository.save(
            WorkflowRunState(
                workflow_run_id=context.workflow_run_id,
                dataset_id=context.dataset_id,
                evaluation_case_id=evaluation_case_id,
                status=status,
                current_node=current_node,
                blocked_node=context.current_node if blocked else None,
                blocked_reason=blocked_reason,
                pending_request_ids=pending_request_ids,
            )
        )

    async def _persist_or_reuse(
        self,
        draft: ArtifactDraft,
        context: ExecutionContext,
        report: ValidationReport,
    ) -> ArtifactEnvelope:
        existing = await self._artifact_repository.list_by_case(draft.evaluation_case_id)
        input_hash = artifact_input_hash(draft, context)
        current = next(
            (
                artifact
                for artifact in existing
                if artifact.artifact_type is draft.artifact_type
                and artifact.input_hash == input_hash
            ),
            None,
        )
        if current is not None:
            return current
        version = 1 + max(
            (
                artifact.version
                for artifact in existing
                if artifact.artifact_type is draft.artifact_type
            ),
            default=0,
        )
        envelope = self._artifact_factory.create(
            draft=draft,
            context=context,
            validation_report=report,
            version=version,
        )
        await self._artifact_repository.save(envelope)
        return envelope
