"""Workflow-owned validation and persistence for the Operations node."""

from opc_mis.business.skills.operations.component import OperationsSkill
from opc_mis.domain.artifacts import ArtifactDraft, ArtifactEnvelope
from opc_mis.domain.components import ExecutionContext
from opc_mis.domain.enums import ArtifactType, ComponentStatus, ValidationStatus, WorkflowStatus
from opc_mis.domain.operations_models import (
    OperationsAssessment,
    OperationsExecutionResult,
    OperationsFacts,
)
from opc_mis.domain.validation_reports import ValidationReport
from opc_mis.domain.workflow import WorkflowNode
from opc_mis.governance.evidence_validator import EvidenceValidator
from opc_mis.ports.artifact_repository import ArtifactRepository
from opc_mis.workflow.artifact_factory import ArtifactFactory, artifact_input_hash


class OperationsAssessmentOrchestrator:
    """Persist validated Operations artifacts without making Risk decisions."""

    def __init__(
        self,
        *,
        operations: OperationsSkill,
        artifacts: ArtifactRepository,
        validator: EvidenceValidator | None = None,
        artifact_factory: ArtifactFactory | None = None,
    ) -> None:
        self._operations = operations
        self._artifacts = artifacts
        self._validator = validator or EvidenceValidator()
        self._artifact_factory = artifact_factory or ArtifactFactory()

    async def run(self, context: ExecutionContext) -> OperationsExecutionResult:
        result = await self._operations.execute(context)
        if result.status is ComponentStatus.FAILED_SAFE:
            return OperationsExecutionResult(
                status=WorkflowStatus.FAILED_SAFE,
                component_status=result.status,
                current_node=WorkflowNode.OPERATIONS_ASSESSMENT.value,
                validation_errors=tuple(event.message for event in result.runtime_events),
                warnings=result.warnings,
                runtime_events=tuple(
                    event.model_dump(mode="json") for event in result.runtime_events
                ),
            )
        if result.status is ComponentStatus.WAITING_FOR_INPUT:
            return OperationsExecutionResult(
                status=WorkflowStatus.WAITING_FOR_INPUT,
                component_status=result.status,
                current_node=WorkflowNode.OPERATIONS_ASSESSMENT.value,
                missing_data_requests=result.missing_data_requests,
                warnings=result.warnings,
            )

        reports: list[ValidationReport] = []
        envelopes: list[ArtifactEnvelope] = []
        execution_context = context
        for draft in result.artifacts:
            if draft.artifact_type is ArtifactType.OPERATIONS_ASSESSMENT:
                facts_artifact = next(
                    item
                    for item in envelopes
                    if item.artifact_type is ArtifactType.OPERATIONS_FACTS
                )
                execution_context = context.model_copy(
                    update={
                        "input_artifact_ids": (
                            *context.input_artifact_ids,
                            facts_artifact.artifact_id,
                        )
                    }
                )
            report = await self._validator.validate(draft)
            reports.append(report)
            if report.status is ValidationStatus.BLOCKED:
                return OperationsExecutionResult(
                    status=WorkflowStatus.FAILED_SAFE,
                    component_status=ComponentStatus.FAILED_SAFE,
                    current_node=WorkflowNode.OPERATIONS_ASSESSMENT.value,
                    operations_facts=result.operations_facts,
                    operations_assessment=result.operations_assessment,
                    validation_reports=tuple(reports),
                    validation_errors=report.blocking_errors,
                    warnings=result.warnings,
                )
            envelopes.append(await self._persist_or_reuse(draft, execution_context, report))
        persisted_facts = OperationsFacts.model_validate(
            next(
                item.payload
                for item in envelopes
                if item.artifact_type is ArtifactType.OPERATIONS_FACTS
            )
        )
        persisted_assessment = OperationsAssessment.model_validate(
            next(
                item.payload
                for item in envelopes
                if item.artifact_type is ArtifactType.OPERATIONS_ASSESSMENT
            )
        )
        return OperationsExecutionResult(
            status=WorkflowStatus.COMPLETED,
            component_status=result.status,
            current_node=WorkflowNode.INITIAL_ASSESSMENT.value,
            operations_facts=persisted_facts,
            operations_assessment=persisted_assessment,
            generated_artifacts=tuple(envelopes),
            validation_reports=tuple(reports),
            warnings=result.warnings,
            runtime_events=tuple(event.model_dump(mode="json") for event in result.runtime_events),
        )

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
                if item.artifact_type is draft.artifact_type and item.input_hash == input_hash
            ),
            None,
        )
        if current is not None:
            return current
        version = 1 + max(
            (item.version for item in existing if item.artifact_type is draft.artifact_type),
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
