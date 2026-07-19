"""Workflow ownership tests for Final Risk validation and persistence."""

import asyncio
from datetime import UTC, datetime
from typing import cast

from opc_mis.business.agents.decision.analysis_component import DecisionAnalysisAgent
from opc_mis.business.agents.decision.analysis_context import (
    DecisionAnalysisContextLoader,
)
from opc_mis.business.agents.decision.card_component import DecisionCardAssembler
from opc_mis.business.agents.decision.card_context import DecisionCardContextLoader
from opc_mis.business.agents.risk.final_component import FinalRiskCheck
from opc_mis.business.agents.risk.final_context_loader import FinalRiskContextLoader
from opc_mis.domain.case_workflow_models import CaseWorkflowRun
from opc_mis.domain.components import ExecutionContext
from opc_mis.domain.decision_models import (
    DecisionAnalysisExecutionResult,
    DecisionCardExecutionResult,
)
from opc_mis.domain.enums import (
    ArtifactType,
    ComponentStatus,
    EvaluationScope,
    MajorExceptionStatus,
    RiskAssessmentStatus,
    RiskLevel,
    RiskSeverity,
    ValidationStatus,
    WorkflowStatus,
)
from opc_mis.domain.final_risk_models import (
    FinalRiskAssessment,
    FinalRiskComponentResult,
    FinalRiskExecutionResult,
    final_risk_assessment_id,
)
from opc_mis.domain.internal_decision_package_models import InternalDecisionPackage
from opc_mis.domain.workflow import WorkflowNode
from opc_mis.infrastructure.openai.decision_fallback import (
    DeterministicDecisionAnalysisComposer,
)
from opc_mis.infrastructure.persistence.memory_approval_request_repository import (
    InMemoryApprovalRequestRepository,
)
from opc_mis.infrastructure.persistence.sqlite_database import SQLiteDatabase
from opc_mis.infrastructure.persistence.sqlite_runtime_event_repository import (
    SQLiteRuntimeEventRepository,
)
from opc_mis.infrastructure.persistence.sqlite_workflow_repository import (
    SQLiteCaseWorkflowRepository,
)
from opc_mis.ports.artifact_repository import ArtifactRepository
from opc_mis.workflow.case_workflow_orchestrator import (
    AutomaticWorkflowServices,
    CaseWorkflowOrchestrator,
)
from opc_mis.workflow.decision_analysis_orchestrator import (
    DecisionAnalysisOrchestrator,
)
from opc_mis.workflow.final_risk_orchestrator import FinalRiskOrchestrator
from tests.unit.test_final_risk_check import (
    _execution_context,
    _package_artifact,
    _risk,
)


class _FixedFinalRiskCheck(FinalRiskCheck):
    """Test double that returns an intentionally forged component result."""

    def __init__(self, result: FinalRiskComponentResult) -> None:
        self._result = result

    async def execute(self, context: ExecutionContext) -> FinalRiskComponentResult:
        del context
        return self._result


class _FinalRiskServices:
    """Minimal service facade used to exercise the durable Final Risk node."""

    snapshot_hash = "SNAPSHOT-FINAL-RISK-TEST"
    decision_analysis_configuration_hash = "DACFG-FINAL-RISK-TEST-000001"

    def __init__(
        self,
        *,
        dataset_id: str,
        final_risk: FinalRiskOrchestrator,
        artifacts: ArtifactRepository,
    ) -> None:
        self.dataset_id = dataset_id
        self._final_risk = final_risk
        self._decision = DecisionAnalysisOrchestrator(
            analysis_agent=DecisionAnalysisAgent(
                context_loader=DecisionAnalysisContextLoader(artifacts=artifacts),
                composer=DeterministicDecisionAnalysisComposer(),
            ),
            card_assembler=DecisionCardAssembler(
                context_loader=DecisionCardContextLoader(artifacts=artifacts)
            ),
            artifacts=artifacts,
        )

    async def final_risk_check(
        self,
        *,
        evaluation_case_id: str,
        workflow_run_id: str,
        internal_decision_package_artifact_id: str,
    ) -> FinalRiskExecutionResult:
        return await self._final_risk.run(
            ExecutionContext(
                evaluation_case_id=evaluation_case_id,
                dataset_id=self.dataset_id,
                workflow_run_id=workflow_run_id,
                input_artifact_ids=(internal_decision_package_artifact_id,),
                requested_scope=(EvaluationScope.RISK,),
                current_node=WorkflowNode.FINAL_RISK_CHECK.value,
            )
        )

    async def decision_analysis(
        self,
        *,
        evaluation_case_id: str,
        workflow_run_id: str,
        final_risk_artifact_id: str,
    ) -> DecisionAnalysisExecutionResult:
        result = await self._decision.run_analysis(
            ExecutionContext(
                evaluation_case_id=evaluation_case_id,
                dataset_id=self.dataset_id,
                workflow_run_id=workflow_run_id,
                input_artifact_ids=(final_risk_artifact_id,),
                requested_scope=(EvaluationScope.RISK,),
                component_input={
                    "composer_configuration_hash": (
                        self.decision_analysis_configuration_hash
                    )
                },
                current_node=WorkflowNode.DECISION_CARD_COMPOSITION.value,
            )
        )
        assert result.status is WorkflowStatus.COMPLETED, result.runtime_events
        return result

    async def decision_card(
        self,
        *,
        evaluation_case_id: str,
        workflow_run_id: str,
        analysis_artifact_id: str,
    ) -> DecisionCardExecutionResult:
        return await self._decision.run_card(
            ExecutionContext(
                evaluation_case_id=evaluation_case_id,
                dataset_id=self.dataset_id,
                workflow_run_id=workflow_run_id,
                input_artifact_ids=(analysis_artifact_id,),
                requested_scope=(EvaluationScope.RISK,),
                current_node=WorkflowNode.DECISION_CARD_COMPOSITION.value,
            )
        )


def test_final_risk_orchestrator_persists_once_and_reuses_exact_output() -> None:
    async def scenario() -> None:
        repository, package = await _package_artifact()
        orchestrator = FinalRiskOrchestrator(
            final_risk=FinalRiskCheck(
                context_loader=FinalRiskContextLoader(artifacts=repository)
            ),
            artifacts=repository,
        )
        context = _execution_context(package.artifact_id)

        first = await orchestrator.run(context)
        second = await orchestrator.run(context)

        assert first.status is WorkflowStatus.COMPLETED
        assert second.status is WorkflowStatus.COMPLETED
        assert first.assessment == second.assessment
        assert first.generated_artifacts == second.generated_artifacts
        envelope = first.generated_artifacts[0]
        assert envelope.artifact_type is ArtifactType.FINAL_RISK_ASSESSMENT
        assert envelope.version == 1
        assert envelope.input_artifact_ids == (package.artifact_id,)
        assert envelope.validation_status in {
            ValidationStatus.VALID,
            ValidationStatus.VALID_WITH_WARNINGS,
        }
        persisted = tuple(
            item
            for item in await repository.list_by_case(package.evaluation_case_id)
            if item.artifact_type is ArtifactType.FINAL_RISK_ASSESSMENT
        )
        assert persisted == (envelope,)

    asyncio.run(scenario())


def test_final_risk_orchestrator_fails_closed_without_exact_single_input() -> None:
    async def scenario() -> None:
        repository, package = await _package_artifact()
        orchestrator = FinalRiskOrchestrator(
            final_risk=FinalRiskCheck(
                context_loader=FinalRiskContextLoader(artifacts=repository)
            ),
            artifacts=repository,
        )
        context = _execution_context(package.artifact_id).model_copy(
            update={"input_artifact_ids": (package.artifact_id, package.artifact_id)}
        )

        result = await orchestrator.run(context)

        assert result.status is WorkflowStatus.FAILED_SAFE
        assert result.generated_artifacts == ()
        assert result.assessment is None
        assert result.validation_errors
        assert not any(
            item.artifact_type is ArtifactType.FINAL_RISK_ASSESSMENT
            for item in await repository.list_by_case(package.evaluation_case_id)
        )

    asyncio.run(scenario())


def test_final_risk_orchestrator_rejects_risk_downgrade_from_exact_package() -> None:
    """A self-consistent payload cannot rewrite the package's Initial Risk snapshot."""

    async def scenario() -> None:
        initial_risk = _risk(
            assessment_status=RiskAssessmentStatus.COMPLETE,
            risk_level=RiskLevel.HIGH,
            severity=RiskSeverity.HIGH,
        )
        repository, package = await _package_artifact(risk=initial_risk)
        context = _execution_context(package.artifact_id)
        legitimate = await FinalRiskCheck(
            context_loader=FinalRiskContextLoader(artifacts=repository)
        ).execute(context)
        assert legitimate.assessment is not None
        assert legitimate.assessment.residual_risk_level is RiskLevel.HIGH

        source = legitimate.assessment
        forged_payload = source.model_dump(mode="python")
        forged_payload.update(
            {
                "initial_risk_level": RiskLevel.NO_CASE_SIGNAL,
                "residual_risk_level": RiskLevel.NO_CASE_SIGNAL,
                "residual_findings": (),
                "major_exception_status": MajorExceptionStatus.NOT_DETECTED,
                "major_exception_signal": None,
            }
        )
        forged_payload["assessment_id"] = final_risk_assessment_id(
            internal_decision_package_artifact_id=(
                source.internal_decision_package_artifact_id
            ),
            internal_decision_package_artifact_version=(
                source.internal_decision_package_artifact_version
            ),
            internal_decision_package_input_hash=(
                source.internal_decision_package_input_hash
            ),
            internal_decision_package_id=source.internal_decision_package_id,
            assessment_status=source.assessment_status,
            residual_risk_level=RiskLevel.NO_CASE_SIGNAL,
            residual_findings=(),
            unresolved_approval_gates=source.unresolved_approval_gates,
            required_controls=source.required_controls,
            major_exception_status=MajorExceptionStatus.NOT_DETECTED,
            major_exception_signal=None,
            limitations=source.limitations,
            evidence_ids=source.evidence_ids,
        )
        forged = FinalRiskAssessment.model_validate(forged_payload)
        forged_draft = legitimate.artifacts[0].model_copy(
            update={"payload": forged.model_dump(mode="json")}
        )
        forged_result = FinalRiskComponentResult(
            status=ComponentStatus.COMPLETED,
            assessment=forged,
            artifacts=(forged_draft,),
        )
        orchestrator = FinalRiskOrchestrator(
            final_risk=_FixedFinalRiskCheck(forged_result),
            artifacts=repository,
        )

        result = await orchestrator.run(context)

        assert result.status is WorkflowStatus.FAILED_SAFE
        assert result.generated_artifacts == ()
        assert not any(
            item.artifact_type is ArtifactType.FINAL_RISK_ASSESSMENT
            for item in await repository.list_by_case(package.evaluation_case_id)
        )

    asyncio.run(scenario())


def test_final_risk_node_recovery_does_not_duplicate_completion_event() -> None:
    async def scenario() -> None:
        artifacts, package_artifact = await _package_artifact(
            risk=_risk(
                assessment_status=RiskAssessmentStatus.COMPLETE,
                risk_level=RiskLevel.HIGH,
                severity=RiskSeverity.HIGH,
            )
        )
        package = InternalDecisionPackage.model_validate(package_artifact.payload)
        database = SQLiteDatabase(":memory:")
        await database.initialize()
        try:
            workflows = SQLiteCaseWorkflowRepository(database)
            events = SQLiteRuntimeEventRepository(database)
            final_risk = FinalRiskOrchestrator(
                final_risk=FinalRiskCheck(
                    context_loader=FinalRiskContextLoader(artifacts=artifacts)
                ),
                artifacts=artifacts,
            )
            services = _FinalRiskServices(
                dataset_id=package.dataset_id,
                final_risk=final_risk,
                artifacts=artifacts,
            )
            workflow = CaseWorkflowOrchestrator(
                services=cast(AutomaticWorkflowServices, services),
                workflows=workflows,
                artifacts=artifacts,
                approvals=InMemoryApprovalRequestRepository(),
                events=events,
            )
            now = datetime.now(UTC)
            run = CaseWorkflowRun(
                workflow_run_id="CWF-FINAL-RISK-RECOVERY",
                dataset_id=package.dataset_id,
                dataset_snapshot_hash=services.snapshot_hash,
                evaluation_case_id=package.evaluation_case_id,
                contract_id=package.contract_id,
                status=WorkflowStatus.RUNNING,
                current_stage=WorkflowNode.INTERNAL_DECISION_PACKAGE_READY.value,
                requested_scope=(EvaluationScope.RISK,),
                created_at=now,
                updated_at=now,
            )
            await workflows.save_run(run)

            await workflow._run_final_risk_check(
                run=run,
                package_artifact=package_artifact,
            )
            recovered = await workflows.get_run(run.workflow_run_id)
            assert recovered is not None
            assert recovered.status is WorkflowStatus.COMPLETED, recovered.failure_reason
            await workflow._run_final_risk_check(
                run=recovered,
                package_artifact=package_artifact,
            )

            stored_events = await events.list_after(run.workflow_run_id, 0)
            completion_events = tuple(
                item
                for item in stored_events
                if item.event_type == "FINAL_RISK_CHECK_COMPLETED"
            )
            assert len(completion_events) == 1
            node = await workflows.get_node(
                run.workflow_run_id,
                WorkflowNode.FINAL_RISK_CHECK.value,
            )
            assert node is not None and node.attempt == 1
            completed = await workflows.get_run(run.workflow_run_id)
            assert completed is not None
            assert completed.status is WorkflowStatus.COMPLETED, completed.failure_reason
            assert completed.current_stage == WorkflowNode.DECISION_CARD_READY.value
            assert await workflow._approvals.list_by_case(package.evaluation_case_id) == ()
            case_artifacts = await artifacts.list_by_case(package.evaluation_case_id)
            assert sum(
                item.artifact_type is ArtifactType.AI_DECISION_ANALYSIS
                for item in case_artifacts
            ) == 1
            assert sum(
                item.artifact_type is ArtifactType.DECISION_CARD
                for item in case_artifacts
            ) == 1
            assert not any(
                item.artifact_type
                is ArtifactType.EXTERNAL_DOCUMENT_SUBMISSION_PROPOSAL
                for item in case_artifacts
            )
        finally:
            await database.close()

    asyncio.run(scenario())


def test_summary_ignores_blocked_or_stale_final_risk_artifacts() -> None:
    async def scenario() -> None:
        artifacts, package_artifact = await _package_artifact(
            risk=_risk(
                assessment_status=RiskAssessmentStatus.COMPLETE,
                risk_level=RiskLevel.HIGH,
                severity=RiskSeverity.HIGH,
            )
        )
        package = InternalDecisionPackage.model_validate(package_artifact.payload)
        database = SQLiteDatabase(":memory:")
        await database.initialize()
        try:
            workflows = SQLiteCaseWorkflowRepository(database)
            events = SQLiteRuntimeEventRepository(database)
            final_risk = FinalRiskOrchestrator(
                final_risk=FinalRiskCheck(
                    context_loader=FinalRiskContextLoader(artifacts=artifacts)
                ),
                artifacts=artifacts,
            )
            services = _FinalRiskServices(
                dataset_id=package.dataset_id,
                final_risk=final_risk,
                artifacts=artifacts,
            )
            workflow = CaseWorkflowOrchestrator(
                services=cast(AutomaticWorkflowServices, services),
                workflows=workflows,
                artifacts=artifacts,
                approvals=InMemoryApprovalRequestRepository(),
                events=events,
            )
            now = datetime.now(UTC)
            run = CaseWorkflowRun(
                workflow_run_id="CWF-FINAL-RISK-SUMMARY",
                dataset_id=package.dataset_id,
                dataset_snapshot_hash=services.snapshot_hash,
                evaluation_case_id=package.evaluation_case_id,
                contract_id=package.contract_id,
                status=WorkflowStatus.RUNNING,
                current_stage=WorkflowNode.INTERNAL_DECISION_PACKAGE_READY.value,
                requested_scope=(EvaluationScope.RISK,),
                created_at=now,
                updated_at=now,
            )
            await workflows.save_run(run)
            await workflow._run_final_risk_check(
                run=run,
                package_artifact=package_artifact,
            )
            valid_summary = await workflow.summary(run.workflow_run_id)
            assert valid_summary.final_risk_assessment_id is not None

            final_artifact = max(
                (
                    item
                    for item in await artifacts.list_by_case(
                        package.evaluation_case_id
                    )
                    if item.artifact_type is ArtifactType.FINAL_RISK_ASSESSMENT
                ),
                key=lambda item: item.version,
            )
            await artifacts.save(
                final_artifact.model_copy(
                    update={
                        "artifact_id": "ART-FINAL-RISK-BLOCKED-NEWER",
                        "version": final_artifact.version + 1,
                        "input_hash": "BLOCKED-FINAL-RISK-HASH",
                        "validation_status": ValidationStatus.BLOCKED,
                    }
                )
            )
            blocked_summary = await workflow.summary(run.workflow_run_id)
            assert (
                blocked_summary.final_risk_assessment_id
                == valid_summary.final_risk_assessment_id
            )

            await artifacts.save(
                package_artifact.model_copy(
                    update={
                        "artifact_id": "ART-INTERNAL-PACKAGE-NEWER",
                        "version": package_artifact.version + 1,
                        "input_hash": "NEWER-INTERNAL-PACKAGE-HASH",
                    }
                )
            )
            stale_summary = await workflow.summary(run.workflow_run_id)
            assert stale_summary.final_risk_assessment_id is None
            assert stale_summary.final_risk_status is None
            assert stale_summary.final_required_control_codes == ()
        finally:
            await database.close()

    asyncio.run(scenario())
