"""Unit tests for deterministic, side-effect-free Decision Initial Route."""

import asyncio
from datetime import UTC, datetime
from pathlib import Path

from opc_mis.business.agents.decision.component import DecisionInitialRoutePlanner
from opc_mis.business.agents.decision.context_loader import DecisionRouteContextLoader
from opc_mis.domain.approvals import ApprovalCheckpointSet
from opc_mis.domain.artifacts import ArtifactEnvelope
from opc_mis.domain.components import ExecutionContext
from opc_mis.domain.enums import (
    ArtifactStatus,
    ArtifactType,
    CashflowScope,
    ComponentStatus,
    DecisionRouteOutcome,
    EvaluationScope,
    FinanceObservationCode,
    RiskAssessmentStatus,
    RiskLevel,
    SourceType,
    ValidationStatus,
)
from opc_mis.domain.evidence import EvidenceRef
from opc_mis.domain.finance_models import FinanceFacts, FinanceObservation
from opc_mis.domain.operations_models import OperationsFacts
from opc_mis.domain.planner_models import EvaluationCase
from opc_mis.domain.risk_models import InitialRiskAssessment
from opc_mis.infrastructure.persistence.memory_artifact_repository import (
    InMemoryArtifactRepository,
)

CASE_ID = "CASE-DECISION-TEST"
DATASET_ID = "DECISION-TEST"
CONTRACT_ID = "CON-TEST"


def evidence() -> EvidenceRef:
    return EvidenceRef(
        evidence_id="EVD-PERFORMANCE-BOND",
        source_type=SourceType.TEAM_PACK,
        sheet="04_CONTRACTS",
        row_number=2,
        record_id=CONTRACT_ID,
        field="payment_terms",
        display_value="Performance bond required",
    )


def envelope(
    artifact_type: ArtifactType,
    payload: dict[str, object],
    *,
    evidence_refs: tuple[EvidenceRef, ...] = (),
) -> ArtifactEnvelope:
    return ArtifactEnvelope(
        artifact_id=f"ART-{artifact_type.value}",
        artifact_type=artifact_type,
        evaluation_case_id=CASE_ID,
        producer="TEST",
        version=1,
        status=ArtifactStatus.CREATED,
        payload=payload,
        evidence_refs=evidence_refs,
        input_artifact_ids=("UPSTREAM",),
        input_hash=f"HASH-{artifact_type.value}",
        validation_status=ValidationStatus.VALID,
        validation_notes=(),
        created_at=datetime.now(UTC),
    )


def upstream_artifacts(
    observation_code: FinanceObservationCode | None,
) -> tuple[ArtifactEnvelope, ...]:
    case = EvaluationCase(
        evaluation_case_id=CASE_ID,
        dataset_id=DATASET_ID,
        contract_id=CONTRACT_ID,
        customer_id="CUS-TEST",
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
    observation = (
        FinanceObservation(
            observation_id="FOB-TEST",
            code=observation_code,
            title="Typed observation",
            detail="Performance bond wording must not control the route by itself.",
            evidence_ids=(evidence().evidence_id,),
        ),
    ) if observation_code is not None else ()
    finance = FinanceFacts(
        evaluation_case_id=CASE_ID,
        dataset_id=DATASET_ID,
        contract_id=CONTRACT_ID,
        facts=(),
        observations=observation,
        limitations=(),
    )
    operations = OperationsFacts(
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
    return (
        envelope(ArtifactType.EVALUATION_CASE, case.model_dump(mode="json")),
        envelope(
            ArtifactType.FINANCE_FACTS,
            finance.model_dump(mode="json"),
            evidence_refs=(evidence(),),
        ),
        envelope(ArtifactType.OPERATIONS_FACTS, operations.model_dump(mode="json")),
        envelope(
            ArtifactType.INITIAL_RISK_ASSESSMENT,
            risk.model_dump(mode="json"),
        ),
        envelope(
            ArtifactType.APPROVAL_CHECKPOINTS,
            checkpoints.model_dump(mode="json"),
        ),
    )


async def execute_route(
    observation_code: FinanceObservationCode | None,
) -> tuple[DecisionInitialRoutePlanner, ExecutionContext, object]:
    repository = InMemoryArtifactRepository()
    artifacts = upstream_artifacts(observation_code)
    for artifact in artifacts:
        await repository.save(artifact)
    component = DecisionInitialRoutePlanner(
        context_loader=DecisionRouteContextLoader(artifacts=repository)
    )
    context = ExecutionContext(
        evaluation_case_id=CASE_ID,
        dataset_id=DATASET_ID,
        workflow_run_id="RUN-DECISION-TEST",
        input_artifact_ids=tuple(item.artifact_id for item in artifacts),
        requested_scope=(
            EvaluationScope.FINANCE,
            EvaluationScope.OPERATIONS,
            EvaluationScope.RISK,
        ),
        component_input={"execution_mode": "INITIAL_ROUTE"},
        current_node="DECISION_ROUTE_PLANNING",
    )
    return component, context, await component.execute(context)


def test_performance_bond_signal_routes_to_banking_without_action() -> None:
    _, _, result = asyncio.run(
        execute_route(FinanceObservationCode.PERFORMANCE_BOND_REQUIREMENT_OBSERVED)
    )

    assert result.status is ComponentStatus.COMPLETED
    assert result.route_plan is not None
    assert (
        result.route_plan.route_outcome
        is DecisionRouteOutcome.BANKING_DISCOVERY_REQUIRED
    )
    assert result.route_plan.banking_need_types == ("PERFORMANCE_BOND",)
    assert result.route_plan.routing_reasons[0].evidence_ids == (
        "EVD-PERFORMANCE-BOND",
    )
    assert result.action_commands == ()
    assert result.approval_signals == ()


def test_text_does_not_route_without_the_exact_typed_signal() -> None:
    _, _, result = asyncio.run(
        execute_route(FinanceObservationCode.MARGIN_BELOW_OPC_TARGET_OBSERVED)
    )

    assert result.route_plan is not None
    assert (
        result.route_plan.route_outcome
        is DecisionRouteOutcome.DIRECT_INTERNAL_DECISION
    )
    assert result.route_plan.routing_reasons == ()


def test_missing_authoritative_artifacts_waits_for_input() -> None:
    async def run() -> object:
        repository = InMemoryArtifactRepository()
        case = upstream_artifacts(None)[0]
        await repository.save(case)
        component = DecisionInitialRoutePlanner(
            context_loader=DecisionRouteContextLoader(artifacts=repository)
        )
        context = ExecutionContext(
            evaluation_case_id=CASE_ID,
            dataset_id=DATASET_ID,
            workflow_run_id="RUN-MISSING",
            input_artifact_ids=(case.artifact_id,),
            requested_scope=(EvaluationScope.RISK,),
            component_input={"execution_mode": "INITIAL_ROUTE"},
            current_node="DECISION_ROUTE_PLANNING",
        )
        return await component.execute(context)

    result = asyncio.run(run())

    assert result.status is ComponentStatus.WAITING_FOR_INPUT
    assert {item.field for item in result.missing_data_requests} == {
        "FINANCE_FACTS",
        "OPERATIONS_FACTS",
        "INITIAL_RISK_ASSESSMENT",
        "APPROVAL_CHECKPOINTS",
    }
    assert result.artifacts == ()


def test_risk_assessment_must_reference_exact_finance_and_operations_artifacts() -> None:
    async def run(lineage_field: str, stale_artifact_id: str) -> object:
        repository = InMemoryArtifactRepository()
        artifacts = list(upstream_artifacts(None))
        risk_index = next(
            index
            for index, artifact in enumerate(artifacts)
            if artifact.artifact_type is ArtifactType.INITIAL_RISK_ASSESSMENT
        )
        risk_artifact = artifacts[risk_index]
        risk = InitialRiskAssessment.model_validate(risk_artifact.payload)
        artifacts[risk_index] = risk_artifact.model_copy(
            update={
                "payload": risk.model_copy(
                    update={lineage_field: stale_artifact_id}
                ).model_dump(mode="json")
            }
        )
        for artifact in artifacts:
            await repository.save(artifact)
        component = DecisionInitialRoutePlanner(
            context_loader=DecisionRouteContextLoader(artifacts=repository)
        )
        context = ExecutionContext(
            evaluation_case_id=CASE_ID,
            dataset_id=DATASET_ID,
            workflow_run_id="RUN-STALE-RISK-LINEAGE",
            input_artifact_ids=tuple(item.artifact_id for item in artifacts),
            requested_scope=(EvaluationScope.RISK,),
            component_input={"execution_mode": "INITIAL_ROUTE"},
            current_node="DECISION_ROUTE_PLANNING",
        )
        return await component.execute(context)

    for field, stale_id, expected_label in (
        ("finance_facts_artifact_id", "ART-STALE-FINANCE", "FinanceFacts"),
        ("operations_facts_artifact_id", "ART-STALE-OPERATIONS", "OperationsFacts"),
    ):
        result = asyncio.run(run(field, stale_id))
        assert result.status is ComponentStatus.FAILED_SAFE
        assert result.artifacts == ()
        assert expected_label in result.runtime_events[0].message


def test_decision_business_layer_has_no_adapter_or_ui_dependency() -> None:
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in Path("src/opc_mis/business/agents/decision").glob("*.py")
    )

    for forbidden in (
        "opc_mis.infrastructure",
        "import pandas",
        "import openpyxl",
        "import fastapi",
        "import openai",
    ):
        assert forbidden not in source
