"""Workflow-owned validation and persistence for Decision Initial Route."""

from opc_mis.business.agents.decision.component import DecisionInitialRoutePlanner
from opc_mis.domain.artifacts import ArtifactDraft, ArtifactEnvelope
from opc_mis.domain.components import ExecutionContext
from opc_mis.domain.decision_route_models import (
    DecisionRouteExecutionResult,
    DecisionRoutePlan,
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


class DecisionRoutePersistenceError(RuntimeError):
    """Raised when a same-hash route artifact is not an exact validated match."""


class DecisionRouteOrchestrator:
    """Validate and persist a route draft without executing downstream capabilities."""

    def __init__(
        self,
        *,
        planner: DecisionInitialRoutePlanner,
        artifacts: ArtifactRepository,
        validator: EvidenceValidator | None = None,
        artifact_factory: ArtifactFactory | None = None,
    ) -> None:
        self._planner = planner
        self._artifacts = artifacts
        self._validator = validator or EvidenceValidator()
        self._artifact_factory = artifact_factory or ArtifactFactory()

    async def run(self, context: ExecutionContext) -> DecisionRouteExecutionResult:
        result = await self._planner.execute(context)
        if result.status is ComponentStatus.FAILED_SAFE:
            return DecisionRouteExecutionResult(
                status=WorkflowStatus.FAILED_SAFE,
                component_status=result.status,
                current_node=WorkflowNode.DECISION_ROUTE_PLANNING.value,
                validation_errors=tuple(
                    event.message for event in result.runtime_events
                ),
                runtime_events=tuple(
                    event.model_dump(mode="json") for event in result.runtime_events
                ),
            )
        if result.status is ComponentStatus.WAITING_FOR_INPUT:
            return DecisionRouteExecutionResult(
                status=WorkflowStatus.WAITING_FOR_INPUT,
                component_status=result.status,
                current_node=WorkflowNode.DECISION_ROUTE_PLANNING.value,
                missing_data_requests=result.missing_data_requests,
                runtime_events=tuple(
                    event.model_dump(mode="json") for event in result.runtime_events
                ),
            )
        draft = self._one_route_draft(result.artifacts)
        report = await self._validator.validate(draft)
        if report.status is ValidationStatus.BLOCKED:
            return DecisionRouteExecutionResult(
                status=WorkflowStatus.FAILED_SAFE,
                component_status=ComponentStatus.FAILED_SAFE,
                current_node=WorkflowNode.DECISION_ROUTE_PLANNING.value,
                route_plan=result.route_plan,
                validation_reports=(report,),
                validation_errors=report.blocking_errors,
                warnings=result.warnings,
            )
        try:
            envelope = await self._persist_or_reuse(draft, context, report)
        except DecisionRoutePersistenceError as exc:
            return DecisionRouteExecutionResult(
                status=WorkflowStatus.FAILED_SAFE,
                component_status=ComponentStatus.FAILED_SAFE,
                current_node=WorkflowNode.DECISION_ROUTE_PLANNING.value,
                route_plan=result.route_plan,
                validation_reports=(report,),
                validation_errors=(str(exc),),
                warnings=result.warnings,
                runtime_events=tuple(
                    event.model_dump(mode="json") for event in result.runtime_events
                ),
            )
        persisted = DecisionRoutePlan.model_validate(envelope.payload)
        return DecisionRouteExecutionResult(
            status=WorkflowStatus.COMPLETED,
            component_status=result.status,
            current_node=WorkflowNode.DECISION_ROUTE_PLANNED.value,
            route_plan=persisted,
            generated_artifacts=(envelope,),
            validation_reports=(report,),
            warnings=result.warnings,
            runtime_events=tuple(
                event.model_dump(mode="json") for event in result.runtime_events
            ),
        )

    @staticmethod
    def _one_route_draft(drafts: tuple[ArtifactDraft, ...]) -> ArtifactDraft:
        matches = tuple(
            item
            for item in drafts
            if item.artifact_type is ArtifactType.DECISION_ROUTE_PLAN
        )
        if len(matches) != 1:
            raise RuntimeError(
                "Decision Initial Route must return exactly one DECISION_ROUTE_PLAN draft."
            )
        return matches[0]

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
                raise DecisionRoutePersistenceError(
                    "Existing Decision route artifact does not match its exact "
                    "validated business inputs."
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
