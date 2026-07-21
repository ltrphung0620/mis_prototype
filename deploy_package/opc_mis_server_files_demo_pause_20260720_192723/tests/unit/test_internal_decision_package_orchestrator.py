"""Focused orchestration tests for the read-only Internal Decision Package."""

import asyncio
from datetime import UTC, datetime

import pytest

from opc_mis.business.agents.decision.internal_package_component import (
    InternalDecisionPackageAssembler,
)
from opc_mis.business.agents.decision.internal_package_context import (
    InternalDecisionPackageContextLoader,
)
from opc_mis.domain.approvals import ApprovalCheckpointSet
from opc_mis.domain.artifacts import ArtifactEnvelope
from opc_mis.domain.components import ExecutionContext
from opc_mis.domain.decision_post_banking_models import DecisionPostBankingReview
from opc_mis.domain.decision_route_models import DecisionRoutePlan
from opc_mis.domain.enums import (
    ApprovalDecision,
    ApprovalRequestStatus,
    ArtifactStatus,
    ArtifactType,
    CashflowScope,
    ComponentStatus,
    DecisionCapability,
    DecisionPostBankingOutcome,
    DecisionRouteMode,
    DecisionRouteOutcome,
    EvaluationScope,
    FinanceAssessmentStatus,
    FinanceNarrativeSource,
    OperationsAssessmentStatus,
    ProtectedAction,
    RiskAssessmentStatus,
    RiskLevel,
    ValidationStatus,
    WorkflowStatus,
)
from opc_mis.domain.finance_models import (
    FinanceAssessment,
    FinanceFacts,
    FinanceNarrative,
)
from opc_mis.domain.internal_decision_package_models import (
    InternalDecisionAssemblyPath,
    InternalDecisionGovernanceReference,
    internal_decision_governance_identity,
    internal_decision_package_id,
    internal_decision_snapshot_hash,
)
from opc_mis.domain.operations_models import OperationsAssessment, OperationsFacts
from opc_mis.domain.planner_models import EvaluationCase
from opc_mis.domain.risk_models import InitialRiskAssessment
from opc_mis.domain.validation_reports import ValidationReport
from opc_mis.infrastructure.persistence.memory_approval_request_repository import (
    InMemoryApprovalRequestRepository,
)
from opc_mis.infrastructure.persistence.memory_artifact_repository import (
    InMemoryArtifactRepository,
)
from opc_mis.workflow.internal_decision_package_orchestrator import (
    InternalDecisionPackageOrchestrator,
)

CASE_ID = "CASE-INTERNAL-PACKAGE"
DATASET_ID = "DATASET-INTERNAL-PACKAGE"
CONTRACT_ID = "CON-INTERNAL-PACKAGE"


@pytest.mark.parametrize(
    ("path", "expected_tail"),
    (
        (InternalDecisionAssemblyPath.DIRECT_ROUTE, ()),
        (
            InternalDecisionAssemblyPath.BANKING_NO_VIABLE_OPTION,
            (
                ArtifactType.BANKING_DISCOVERY_REQUEST,
                ArtifactType.BANKING_OPTION_MATRIX,
                ArtifactType.BANKING_DISCOVERY_RESULT,
                ArtifactType.BANKING_PRECHECK_READINESS,
                ArtifactType.DECISION_POST_BANKING_REVIEW,
            ),
        ),
        (
            InternalDecisionAssemblyPath.BANKING_NO_PRECHECK_PATH,
            (
                ArtifactType.BANKING_DISCOVERY_REQUEST,
                ArtifactType.BANKING_OPTION_MATRIX,
                ArtifactType.BANKING_DISCOVERY_RESULT,
                ArtifactType.BANKING_PRECHECK_READINESS,
                ArtifactType.DECISION_POST_BANKING_REVIEW,
            ),
        ),
        (
            InternalDecisionAssemblyPath.BANKING_PRECHECK_DECLINED,
            (
                ArtifactType.BANKING_DISCOVERY_REQUEST,
                ArtifactType.BANKING_OPTION_MATRIX,
                ArtifactType.BANKING_DISCOVERY_RESULT,
                ArtifactType.BANKING_PRECHECK_READINESS,
                ArtifactType.DECISION_POST_BANKING_REVIEW,
                ArtifactType.BANKING_PRECHECK_SUBMISSION_PROPOSAL,
            ),
        ),
        (
            InternalDecisionAssemblyPath.BANKING_NON_ACTIONABLE,
            (
                ArtifactType.BANKING_DISCOVERY_REQUEST,
                ArtifactType.BANKING_OPTION_MATRIX,
                ArtifactType.BANKING_DISCOVERY_RESULT,
                ArtifactType.BANKING_PRECHECK_READINESS,
                ArtifactType.DECISION_POST_BANKING_REVIEW,
                ArtifactType.BANKING_PRECHECK_SUBMISSION_PROPOSAL,
                ArtifactType.BANKING_PRECHECK_RESULT_SET,
                ArtifactType.DECISION_POST_PRECHECK_REVIEW,
            ),
        ),
        (
            InternalDecisionAssemblyPath.CONDITIONAL_DOCUMENT_READY,
            (
                ArtifactType.BANKING_DISCOVERY_REQUEST,
                ArtifactType.BANKING_OPTION_MATRIX,
                ArtifactType.BANKING_DISCOVERY_RESULT,
                ArtifactType.BANKING_PRECHECK_READINESS,
                ArtifactType.DECISION_POST_BANKING_REVIEW,
                ArtifactType.BANKING_PRECHECK_SUBMISSION_PROPOSAL,
                ArtifactType.BANKING_PRECHECK_RESULT_SET,
                ArtifactType.DECISION_POST_PRECHECK_REVIEW,
                ArtifactType.DOCUMENT_PREPARATION_REQUEST,
                ArtifactType.DOCUMENT_RELEASE_PACKAGE,
            ),
        ),
    ),
)
def test_each_assembly_path_has_exact_required_artifact_types(
    path: InternalDecisionAssemblyPath,
    expected_tail: tuple[ArtifactType, ...],
) -> None:
    common = (
        ArtifactType.EVALUATION_CASE,
        ArtifactType.FINANCE_FACTS,
        ArtifactType.FINANCE_ASSESSMENT,
        ArtifactType.OPERATIONS_FACTS,
        ArtifactType.OPERATIONS_ASSESSMENT,
        ArtifactType.INITIAL_RISK_ASSESSMENT,
        ArtifactType.APPROVAL_CHECKPOINTS,
        ArtifactType.DECISION_ROUTE_PLAN,
    )

    assert InternalDecisionPackageContextLoader._required_types(path) == (
        *common,
        *expected_tail,
    )


def test_governance_identity_excludes_runtime_ids_and_event_time() -> None:
    """Equivalent business decisions must not acquire runtime-dependent IDs."""
    common = {
        "status": ApprovalRequestStatus.REJECTED,
        "action": ProtectedAction.SUBMIT_BANKING_PRECHECK,
        "subject_artifact_id": "ART-PROPOSAL",
        "subject_artifact_version": 1,
        "subject_input_hash": "PROPOSAL-HASH",
        "checkpoint_ids": ("CHK-API-002",),
        "policy_artifact_id": "ART-POLICY",
        "policy_artifact_version": 1,
        "policy_input_hash": "POLICY-HASH",
        "policy_coverage_ids": ("COV-API-002",),
        "decision": ApprovalDecision.REJECT,
        "decided_by": "FOUNDER",
        "decision_reason": "HUMAN_REVIEW_COMPLETED",
    }
    first = InternalDecisionGovernanceReference(
        approval_request_id="APR-RUNTIME-A",
        workflow_run_id="RUN-RUNTIME-A",
        decided_at=datetime(2026, 7, 19, 1, tzinfo=UTC),
        **common,
    )
    second = InternalDecisionGovernanceReference(
        approval_request_id="APR-RUNTIME-B",
        workflow_run_id="RUN-RUNTIME-B",
        decided_at=datetime(2026, 7, 19, 2, tzinfo=UTC),
        **common,
    )

    assert internal_decision_governance_identity(first) == (
        internal_decision_governance_identity(second)
    )
    assert internal_decision_package_id(
        assembly_path=InternalDecisionAssemblyPath.BANKING_PRECHECK_DECLINED,
        source_artifacts=(),
        governance_references=(first,),
    ) == internal_decision_package_id(
        assembly_path=InternalDecisionAssemblyPath.BANKING_PRECHECK_DECLINED,
        source_artifacts=(),
        governance_references=(second,),
    )


def _envelope(
    artifact_type: ArtifactType,
    payload: dict[str, object],
    *,
    input_artifact_ids: tuple[str, ...] = (),
    validation_status: ValidationStatus = ValidationStatus.VALID,
) -> ArtifactEnvelope:
    return ArtifactEnvelope(
        artifact_id=f"ART-{artifact_type.value}",
        artifact_type=artifact_type,
        evaluation_case_id=CASE_ID,
        producer="TEST",
        version=1,
        status=ArtifactStatus.CREATED,
        payload=payload,
        evidence_refs=(),
        input_artifact_ids=input_artifact_ids,
        input_hash=f"HASH-{artifact_type.value}",
        validation_status=validation_status,
        validation_notes=(),
        created_at=datetime(2026, 7, 19, tzinfo=UTC),
    )


def _direct_artifacts() -> tuple[ArtifactEnvelope, ...]:
    case = EvaluationCase(
        evaluation_case_id=CASE_ID,
        dataset_id=DATASET_ID,
        contract_id=CONTRACT_ID,
        customer_id="CUS-INTERNAL-PACKAGE",
        related_order_ids=(),
        related_invoice_ids=(),
        related_service_ids=(),
        related_credit_case_ids=(),
        evaluation_scope=(
            EvaluationScope.FINANCE,
            EvaluationScope.OPERATIONS,
            EvaluationScope.RISK,
        ),
        cashflow_scope=CashflowScope.OPC_GLOBAL,
        warnings=(),
        evidence_refs=(),
    )
    finance_facts = FinanceFacts(
        evaluation_case_id=CASE_ID,
        dataset_id=DATASET_ID,
        contract_id=CONTRACT_ID,
        facts=(),
        observations=(),
        limitations=(),
    )
    finance_assessment = FinanceAssessment(
        evaluation_case_id=CASE_ID,
        dataset_id=DATASET_ID,
        contract_id=CONTRACT_ID,
        assessment_status=FinanceAssessmentStatus.COMPLETE,
        facts_input_hash=internal_decision_snapshot_hash(finance_facts),
        fact_ids=(),
        observations=(),
        limitations=(),
        narrative=FinanceNarrative(
            headline="No case-specific Finance facts were required for this fixture.",
            statements=(),
        ),
        narrative_source=FinanceNarrativeSource.DETERMINISTIC_FALLBACK,
        composer_model="DETERMINISTIC_TEST",
        prompt_version="test-v1",
    )
    operations_facts = OperationsFacts(
        evaluation_case_id=CASE_ID,
        dataset_id=DATASET_ID,
        contract_id=CONTRACT_ID,
        as_of_date=None,
        facts=(),
        order_schedules=(),
        source_notes=(),
        observations=(),
        limitations=(),
    )
    operations_assessment = OperationsAssessment(
        evaluation_case_id=CASE_ID,
        dataset_id=DATASET_ID,
        contract_id=CONTRACT_ID,
        assessment_status=OperationsAssessmentStatus.COMPLETE,
        facts_input_hash=internal_decision_snapshot_hash(operations_facts),
        fact_ids=(),
        observations=(),
        limitations=(),
        summary=(),
    )
    risk = InitialRiskAssessment(
        evaluation_case_id=CASE_ID,
        dataset_id=DATASET_ID,
        contract_id=CONTRACT_ID,
        assessment_status=RiskAssessmentStatus.COMPLETE,
        overall_risk_level=RiskLevel.NO_CASE_SIGNAL,
        triggered_rule_ids=(),
        findings=(),
        source_alerts=(),
        global_context_signals=(),
        human_confirmation_points=(),
        limitations=(),
        finance_facts_artifact_id="ART-FINANCE_FACTS",
        operations_facts_artifact_id="ART-OPERATIONS_FACTS",
    )
    checkpoints = ApprovalCheckpointSet(
        evaluation_case_id=CASE_ID,
        dataset_id=DATASET_ID,
        contract_id=CONTRACT_ID,
        checkpoints=(),
    )
    route_sources = (
        "ART-EVALUATION_CASE",
        "ART-FINANCE_FACTS",
        "ART-OPERATIONS_FACTS",
        "ART-INITIAL_RISK_ASSESSMENT",
        "ART-APPROVAL_CHECKPOINTS",
    )
    route = DecisionRoutePlan(
        route_plan_id="DRP-DIRECT-INTERNAL-PACKAGE",
        evaluation_case_id=CASE_ID,
        dataset_id=DATASET_ID,
        contract_id=CONTRACT_ID,
        execution_mode=DecisionRouteMode.INITIAL_ROUTE,
        route_outcome=DecisionRouteOutcome.DIRECT_INTERNAL_DECISION,
        required_capabilities=(DecisionCapability.INTERNAL_DECISION_PACKAGE,),
        source_artifact_ids=route_sources,
    )
    return (
        _envelope(ArtifactType.EVALUATION_CASE, case.model_dump(mode="json")),
        _envelope(ArtifactType.FINANCE_FACTS, finance_facts.model_dump(mode="json")),
        _envelope(
            ArtifactType.FINANCE_ASSESSMENT,
            finance_assessment.model_dump(mode="json"),
            input_artifact_ids=("ART-FINANCE_FACTS",),
        ),
        _envelope(
            ArtifactType.OPERATIONS_FACTS,
            operations_facts.model_dump(mode="json"),
        ),
        _envelope(
            ArtifactType.OPERATIONS_ASSESSMENT,
            operations_assessment.model_dump(mode="json"),
            input_artifact_ids=("ART-OPERATIONS_FACTS",),
        ),
        _envelope(
            ArtifactType.INITIAL_RISK_ASSESSMENT,
            risk.model_dump(mode="json"),
            input_artifact_ids=(
                "ART-FINANCE_FACTS",
                "ART-OPERATIONS_FACTS",
            ),
        ),
        _envelope(
            ArtifactType.APPROVAL_CHECKPOINTS,
            checkpoints.model_dump(mode="json"),
        ),
        _envelope(
            ArtifactType.DECISION_ROUTE_PLAN,
            route.model_dump(mode="json"),
            input_artifact_ids=route_sources,
        ),
    )


def _context(artifacts: tuple[ArtifactEnvelope, ...]) -> ExecutionContext:
    return ExecutionContext(
        evaluation_case_id=CASE_ID,
        dataset_id=DATASET_ID,
        workflow_run_id="RUN-INTERNAL-PACKAGE",
        input_artifact_ids=tuple(item.artifact_id for item in artifacts),
        requested_scope=(
            EvaluationScope.FINANCE,
            EvaluationScope.OPERATIONS,
            EvaluationScope.RISK,
        ),
        component_input={"assembly_path": "DIRECT_ROUTE"},
        current_node="INTERNAL_DECISION_PACKAGE_ASSEMBLY",
    )


def _system() -> tuple[
    InMemoryArtifactRepository,
    InternalDecisionPackageAssembler,
    InternalDecisionPackageOrchestrator,
]:
    repository = InMemoryArtifactRepository()
    assembler = InternalDecisionPackageAssembler(
        context_loader=InternalDecisionPackageContextLoader(
            artifacts=repository,
            approvals=InMemoryApprovalRequestRepository(),
        )
    )
    return (
        repository,
        assembler,
        InternalDecisionPackageOrchestrator(
            assembler=assembler,
            artifacts=repository,
        ),
    )


async def _save_all(
    repository: InMemoryArtifactRepository,
    artifacts: tuple[ArtifactEnvelope, ...],
) -> None:
    for artifact in artifacts:
        await repository.save(artifact)


def test_direct_package_has_exact_lineage_stable_id_and_idempotent_persistence() -> None:
    async def run() -> None:
        repository, assembler, orchestrator = _system()
        sources = _direct_artifacts()
        await _save_all(repository, sources)
        context = _context(sources)

        component_result = await assembler.execute(context)
        assert component_result.status is ComponentStatus.COMPLETED
        assert component_result.approval_signals == ()
        assert component_result.action_commands == ()

        first = await orchestrator.run(context)
        second = await orchestrator.run(context)

        assert first.status is WorkflowStatus.COMPLETED
        assert second.status is WorkflowStatus.COMPLETED
        assert first.package is not None
        assert second.package is not None
        assert first.package.package_id == second.package.package_id
        assert first.package.source_artifact_ids == context.input_artifact_ids
        assert first.generated_artifacts == second.generated_artifacts
        assert first.generated_artifacts[0].version == 1
        assert first.validation_reports[0].status is ValidationStatus.VALID
        persisted = await repository.list_by_case(CASE_ID)
        packages = tuple(
            item
            for item in persisted
            if item.artifact_type is ArtifactType.INTERNAL_DECISION_PACKAGE
        )
        assert packages == first.generated_artifacts
        assert len(packages) == 1

        package = first.package
        assert package.recommendation_performed is False
        assert package.selection_performed is False
        assert package.approval_requested is False
        assert package.external_action_performed is False
        assert package.document_release_package is None
        assert package.governance_references == ()

    asyncio.run(run())


def test_missing_required_input_waits_with_mdr_and_persists_no_package() -> None:
    async def run() -> None:
        repository, _, orchestrator = _system()
        sources = _direct_artifacts()[:1]
        await _save_all(repository, sources)

        result = await orchestrator.run(_context(sources))

        assert result.status is WorkflowStatus.WAITING_FOR_INPUT
        assert result.component_status is ComponentStatus.WAITING_FOR_INPUT
        assert result.package is None
        assert result.generated_artifacts == ()
        assert result.validation_reports == ()
        assert result.missing_data_requests
        assert {
            item.requirement_code for item in result.missing_data_requests
        } == {
            "FINANCE_FACTS_REQUIRED",
            "FINANCE_ASSESSMENT_REQUIRED",
            "OPERATIONS_FACTS_REQUIRED",
            "OPERATIONS_ASSESSMENT_REQUIRED",
            "INITIAL_RISK_ASSESSMENT_REQUIRED",
            "APPROVAL_CHECKPOINTS_REQUIRED",
            "DECISION_ROUTE_PLAN_REQUIRED",
        }
        persisted = await repository.list_by_case(CASE_ID)
        assert not any(
            item.artifact_type is ArtifactType.INTERNAL_DECISION_PACKAGE
            for item in persisted
        )

    asyncio.run(run())


def test_wrong_path_fails_safe_before_emitting_irrelevant_missing_requests() -> None:
    async def run() -> None:
        repository, _, orchestrator = _system()
        sources = _direct_artifacts()
        await _save_all(repository, sources)
        context = _context(sources).model_copy(
            update={
                "component_input": {
                    "assembly_path": "CONDITIONAL_DOCUMENT_READY"
                }
            }
        )

        result = await orchestrator.run(context)

        assert result.status is WorkflowStatus.FAILED_SAFE
        assert result.package is None
        assert result.missing_data_requests == ()
        assert "contradicts" in " ".join(result.validation_errors)

    asyncio.run(run())


def test_wrong_non_direct_path_fails_before_downstream_missing_requests() -> None:
    async def run() -> None:
        repository, _, orchestrator = _system()
        sources = list(_direct_artifacts())
        route_index = next(
            index
            for index, item in enumerate(sources)
            if item.artifact_type is ArtifactType.DECISION_ROUTE_PLAN
        )
        route = DecisionRoutePlan.model_validate(sources[route_index].payload)
        banking_route = route.model_copy(
            update={
                "route_outcome": DecisionRouteOutcome.BANKING_DISCOVERY_REQUIRED,
                "required_capabilities": (
                    DecisionCapability.BANKING_INTERNAL_DISCOVERY,
                ),
            }
        )
        sources[route_index] = sources[route_index].model_copy(
            update={"payload": banking_route.model_dump(mode="json")}
        )
        post_banking = DecisionPostBankingReview(
            review_id="DPB-NO-VIABLE",
            evaluation_case_id=CASE_ID,
            dataset_id=DATASET_ID,
            contract_id=CONTRACT_ID,
            matrix_id="BOM-NO-VIABLE",
            banking_request_id="BDR-NO-VIABLE",
            readiness_id="BPR-NO-VIABLE",
            outcome=DecisionPostBankingOutcome.NO_VIABLE_OPTION,
            candidate_option_ids=(),
            source_artifact_ids=(
                "ART-BANKING_OPTION_MATRIX",
                "ART-BANKING_PRECHECK_READINESS",
            ),
            evidence_ids=("EVD-NO-VIABLE",),
        )
        sources.append(
            _envelope(
                ArtifactType.DECISION_POST_BANKING_REVIEW,
                post_banking.model_dump(mode="json"),
            )
        )
        source_tuple = tuple(sources)
        await _save_all(repository, source_tuple)
        context = _context(source_tuple).model_copy(
            update={
                "component_input": {
                    "assembly_path": "CONDITIONAL_DOCUMENT_READY"
                }
            }
        )

        result = await orchestrator.run(context)

        assert result.status is WorkflowStatus.FAILED_SAFE
        assert result.package is None
        assert result.missing_data_requests == ()
        assert "post-Banking review" in " ".join(result.validation_errors)

    asyncio.run(run())


def test_blocked_validation_never_exposes_an_apparently_ready_package() -> None:
    class BlockingValidator:
        async def validate(self, draft: object) -> ValidationReport:
            del draft
            return ValidationReport(
                status=ValidationStatus.BLOCKED,
                blocking_errors=("TEST_VALIDATION_BLOCK",),
            )

    async def run() -> None:
        repository, assembler, _ = _system()
        sources = _direct_artifacts()
        await _save_all(repository, sources)
        orchestrator = InternalDecisionPackageOrchestrator(
            assembler=assembler,
            artifacts=repository,
            evidence_validator=BlockingValidator(),
        )

        result = await orchestrator.run(_context(sources))

        assert result.status is WorkflowStatus.FAILED_SAFE
        assert result.package is None
        assert result.generated_artifacts == ()
        assert result.validation_errors == ("TEST_VALIDATION_BLOCK",)

    asyncio.run(run())


@pytest.mark.parametrize(
    "defect",
    (
        "UNVALIDATED",
        "WRONG_RISK_LINEAGE",
        "STALE_FINANCE_ASSESSMENT",
        "STALE_FINANCE_ENVELOPE_LINEAGE",
    ),
)
def test_malformed_or_unvalidated_input_fails_safe_without_persistence(
    defect: str,
) -> None:
    async def run() -> None:
        repository, _, orchestrator = _system()
        sources = list(_direct_artifacts())
        finance_index = next(
            index
            for index, item in enumerate(sources)
            if item.artifact_type is ArtifactType.FINANCE_FACTS
        )
        risk_index = next(
            index
            for index, item in enumerate(sources)
            if item.artifact_type is ArtifactType.INITIAL_RISK_ASSESSMENT
        )
        finance_assessment_index = next(
            index
            for index, item in enumerate(sources)
            if item.artifact_type is ArtifactType.FINANCE_ASSESSMENT
        )
        if defect == "UNVALIDATED":
            sources[finance_index] = sources[finance_index].model_copy(
                update={"validation_status": ValidationStatus.BLOCKED}
            )
        elif defect == "WRONG_RISK_LINEAGE":
            risk = InitialRiskAssessment.model_validate(sources[risk_index].payload)
            sources[risk_index] = sources[risk_index].model_copy(
                update={
                    "payload": risk.model_copy(
                        update={"finance_facts_artifact_id": "ART-STALE-FINANCE"}
                    ).model_dump(mode="json")
                }
            )
        elif defect == "STALE_FINANCE_ASSESSMENT":
            assessment = FinanceAssessment.model_validate(
                sources[finance_assessment_index].payload
            )
            sources[finance_assessment_index] = sources[
                finance_assessment_index
            ].model_copy(
                update={
                    "payload": assessment.model_copy(
                        update={"facts_input_hash": "STALE-FACTS-HASH"}
                    ).model_dump(mode="json")
                }
            )
        else:
            sources[finance_assessment_index] = sources[
                finance_assessment_index
            ].model_copy(
                update={"input_artifact_ids": ("ART-STALE-FINANCE-FACTS",)}
            )
        source_tuple = tuple(sources)
        await _save_all(repository, source_tuple)

        result = await orchestrator.run(_context(source_tuple))

        assert result.status is WorkflowStatus.FAILED_SAFE
        assert result.component_status is ComponentStatus.FAILED_SAFE
        assert result.package is None
        assert result.generated_artifacts == ()
        assert result.validation_errors
        persisted = await repository.list_by_case(CASE_ID)
        assert not any(
            item.artifact_type is ArtifactType.INTERNAL_DECISION_PACKAGE
            for item in persisted
        )

    asyncio.run(run())
