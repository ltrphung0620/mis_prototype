"""Workflow-owned validation and persistence for the Finance assessment node."""

from opc_mis.business.agents.finance.component import FinanceAgent
from opc_mis.domain.artifacts import ArtifactDraft, ArtifactEnvelope
from opc_mis.domain.components import ExecutionContext
from opc_mis.domain.enums import (
    ArtifactType,
    ComponentStatus,
    ValidationStatus,
    WorkflowStatus,
)
from opc_mis.domain.finance_models import FinanceAssessment, FinanceExecutionResult, FinanceFacts
from opc_mis.domain.validation_reports import ValidationReport
from opc_mis.domain.workflow import WorkflowNode
from opc_mis.governance.evidence_validator import EvidenceValidator
from opc_mis.ports.artifact_repository import ArtifactRepository
from opc_mis.workflow.artifact_factory import ArtifactFactory, artifact_input_hash


class FinanceAssessmentOrchestrator:
    """Persist validated Finance artifacts without making downstream node decisions."""

    def __init__(
        self,
        *,
        finance: FinanceAgent,
        artifacts: ArtifactRepository,
        validator: EvidenceValidator | None = None,
        artifact_factory: ArtifactFactory | None = None,
    ) -> None:
        self._finance = finance
        self._artifacts = artifacts
        self._validator = validator or EvidenceValidator()
        self._artifact_factory = artifact_factory or ArtifactFactory()

    async def run(self, context: ExecutionContext) -> FinanceExecutionResult:
        result = await self._finance.execute(context)
        if result.status is ComponentStatus.FAILED_SAFE:
            return FinanceExecutionResult(
                status=WorkflowStatus.FAILED_SAFE,
                component_status=result.status,
                current_node=WorkflowNode.FINANCE_ASSESSMENT.value,
                validation_errors=tuple(event.message for event in result.runtime_events),
                warnings=result.warnings,
                runtime_events=tuple(
                    event.model_dump(mode="json") for event in result.runtime_events
                ),
            )
        if result.status is ComponentStatus.WAITING_FOR_INPUT:
            return FinanceExecutionResult(
                status=WorkflowStatus.WAITING_FOR_INPUT,
                component_status=result.status,
                current_node=WorkflowNode.FINANCE_ASSESSMENT.value,
                missing_data_requests=result.missing_data_requests,
                warnings=result.warnings,
                runtime_events=tuple(
                    event.model_dump(mode="json") for event in result.runtime_events
                ),
            )

        reports: list[ValidationReport] = []
        envelopes: list[ArtifactEnvelope] = []
        execution_context = context
        for draft in result.artifacts:
            if draft.artifact_type is ArtifactType.FINANCE_ASSESSMENT:
                facts_artifact = next(
                    item for item in envelopes if item.artifact_type is ArtifactType.FINANCE_FACTS
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
                return FinanceExecutionResult(
                    status=WorkflowStatus.FAILED_SAFE,
                    component_status=ComponentStatus.FAILED_SAFE,
                    current_node=WorkflowNode.FINANCE_ASSESSMENT.value,
                    finance_facts=result.finance_facts,
                    finance_assessment=result.finance_assessment,
                    validation_reports=tuple(reports),
                    validation_errors=report.blocking_errors,
                    warnings=result.warnings,
                )
            envelopes.append(await self._persist_or_reuse(draft, execution_context, report))
        persisted_facts = FinanceFacts.model_validate(
            next(
                item.payload
                for item in envelopes
                if item.artifact_type is ArtifactType.FINANCE_FACTS
            )
        )
        persisted_assessment = FinanceAssessment.model_validate(
            next(
                item.payload
                for item in envelopes
                if item.artifact_type is ArtifactType.FINANCE_ASSESSMENT
            )
        )
        return FinanceExecutionResult(
            status=WorkflowStatus.COMPLETED,
            component_status=result.status,
            current_node=WorkflowNode.INITIAL_ASSESSMENT.value,
            finance_facts=persisted_facts,
            finance_assessment=persisted_assessment,
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
