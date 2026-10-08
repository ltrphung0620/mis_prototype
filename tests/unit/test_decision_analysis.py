"""Decision analysis tests for exact lineage, AI guardrails, and stable output."""

import asyncio
from datetime import UTC, datetime

import pytest

from opc_mis.business.agents.decision.analysis_component import DecisionAnalysisAgent
from opc_mis.business.agents.decision.analysis_context import (
    DecisionAnalysisContextError,
    DecisionAnalysisContextLoader,
)
from opc_mis.business.agents.decision.card_component import DecisionCardAssembler
from opc_mis.business.agents.decision.card_context import DecisionCardContextLoader
from opc_mis.business.agents.risk.final_component import FinalRiskCheck
from opc_mis.business.agents.risk.final_context_loader import FinalRiskContextLoader
from opc_mis.domain.artifacts import ArtifactEnvelope
from opc_mis.domain.components import ExecutionContext
from opc_mis.domain.decision_analysis import (
    DecisionAnalysisBoundaryError,
    _margin_negotiation_strategies,
    _metric_candidates,
    _risk_candidates,
    assemble_decision_card,
    build_decision_scenario_packet,
    guard_ai_decision_composition,
)
from opc_mis.domain.decision_models import (
    MARGIN_BENCHMARK_INPUTS_CONDITION_CODE,
    MARGIN_STRATEGY_INPUTS_CONDITION_CODE,
    AIDecisionComposition,
    AIDecisionProposalDraft,
    AIDecisionReasonDraft,
    AIDecisionRecommendedActionDraft,
    DecisionAnalysisSource,
    DecisionCalculationCode,
    DecisionConditionStatus,
    DecisionConfidence,
    DecisionLimitationSnapshot,
    DecisionMetricRole,
    DecisionMetricSnapshot,
    DecisionNegotiationStrategyType,
    DecisionRecommendation,
    NegotiationConditionDraft,
    decision_conditions_support_negotiation,
    decision_packet_input_hash,
)
from opc_mis.domain.enums import (
    ArtifactStatus,
    ArtifactType,
    ComponentStatus,
    EvaluationScope,
    FinanceMetric,
    RiskAssessmentStatus,
    RiskLevel,
    RiskSeverity,
    ValidationStatus,
)
from opc_mis.domain.final_risk_models import FinalRiskAssessment
from opc_mis.domain.internal_decision_package_models import InternalDecisionPackage
from opc_mis.infrastructure.persistence.memory_artifact_repository import (
    InMemoryArtifactRepository,
)
from opc_mis.workflow.final_risk_orchestrator import FinalRiskOrchestrator
from tests.unit.test_final_risk_check import (
    _execution_context,
    _package_artifact,
    _risk,
)


async def _inputs(
    *,
    risk=None,
) -> tuple[
    InMemoryArtifactRepository,
    ArtifactEnvelope,
    InternalDecisionPackage,
    ArtifactEnvelope,
    FinalRiskAssessment,
]:
    if risk is None:
        risk = _risk(
            assessment_status=RiskAssessmentStatus.COMPLETE,
            risk_level=RiskLevel.LOW,
            severity=RiskSeverity.LOW,
        )
    repository, package_artifact = await _package_artifact(risk=risk)
    orchestrator = FinalRiskOrchestrator(
        final_risk=FinalRiskCheck(
            context_loader=FinalRiskContextLoader(artifacts=repository)
        ),
        artifacts=repository,
    )
    result = await orchestrator.run(_execution_context(package_artifact.artifact_id))
    final_artifact = result.generated_artifacts[0]
    return (
        repository,
        package_artifact,
        InternalDecisionPackage.model_validate(package_artifact.payload),
        final_artifact,
        FinalRiskAssessment.model_validate(final_artifact.payload),
    )


def _composition(packet, recommendation=None):
    chosen = recommendation or (
        DecisionRecommendation.NEGOTIATE_CONDITIONS_TO_ACCEPT
        if DecisionRecommendation.NEGOTIATE_CONDITIONS_TO_ACCEPT
        in packet.allowed_recommendations
        else (
            DecisionRecommendation.ACCEPT
            if DecisionRecommendation.ACCEPT in packet.allowed_recommendations
            else DecisionRecommendation.NOT_EVALUABLE
        )
    )
    reasons = tuple(
        AIDecisionReasonDraft.model_validate(
            item.model_dump(exclude={"candidate_id"})
        )
        for item in packet.reason_candidates[:2]
    )
    conditions = (
        tuple(
            NegotiationConditionDraft.model_validate(
                item.model_dump(exclude={"candidate_id"})
            )
            for item in packet.condition_candidates
        )
        if chosen is DecisionRecommendation.NEGOTIATE_CONDITIONS_TO_ACCEPT
        else ()
    )
    strategy_ids = ()
    if chosen is DecisionRecommendation.NEGOTIATE_CONDITIONS_TO_ACCEPT:
        strategy_by_condition: dict[str, str] = {}
        for strategy in packet.negotiation_strategy_candidates:
            strategy_by_condition.setdefault(
                strategy.condition_code, strategy.strategy_id
            )
        strategy_ids = tuple(strategy_by_condition.values())
    return AIDecisionComposition(
        proposal=AIDecisionProposalDraft(
            recommendation=chosen,
            executive_summary="Evidence supports the selected guarded disposition.",
            reasons=reasons,
            recommended_actions=(
                tuple(
                    AIDecisionRecommendedActionDraft(
                        reason_code=item.code,
                        action="Founder should address this reason before deciding.",
                        source_reference_ids=item.source_reference_ids,
                        evidence_ids=item.evidence_ids,
                    )
                    for item in reasons
                )
                if chosen is not DecisionRecommendation.NOT_EVALUABLE
                else ()
            ),
            conditions=conditions,
            selected_negotiation_strategy_ids=strategy_ids,
            confidence=(
                DecisionConfidence.NOT_EVALUABLE
                if chosen is DecisionRecommendation.NOT_EVALUABLE
                else DecisionConfidence.MEDIUM
            ),
        ),
        source=DecisionAnalysisSource.OPENAI,
        model="test-model",
        prompt_version="decision-test-v1",
        input_hash=decision_packet_input_hash(packet),
    )


def _finance_metric(
    metric: FinanceMetric,
    value: int | float,
    unit: str,
    *,
    role: DecisionMetricRole = DecisionMetricRole.CASE_FACT,
) -> DecisionMetricSnapshot:
    return DecisionMetricSnapshot(
        fact_id=f"FACT-{metric.value}",
        metric=metric.value,
        value=value,
        unit=unit,
        calculation="TEST_FIXTURE",
        quality="VERIFIED",
        evidence_ids=(f"EVD-{metric.value}",),
        role=role,
        contract_attributable=role is DecisionMetricRole.CASE_FACT,
    )


def test_risk_limitation_reason_names_cashflow_pressure_months() -> None:
    limitation = DecisionLimitationSnapshot(
        limitation_id="LIM-CLOSING-CASH",
        code="EVIDENCE_LIMITATION",
        detail=(
            "No exact closing_cash fact exists; projected_closing_cash is not "
            "silently aliased."
        ),
        evidence_ids=("EVD-CASHFLOW",),
    )
    finance_metrics = (
        _finance_metric(
            FinanceMetric.WORST_RESERVE_GAP,
            500_000_000,
            "VND",
            role=DecisionMetricRole.OPC_GLOBAL_CONTEXT,
        ),
        DecisionMetricSnapshot(
            fact_id="FACT-WORST-MONTH",
            metric=FinanceMetric.WORST_RESERVE_GAP_MONTH.value,
            value="2026-09",
            unit="TEXT",
            calculation="TEST_FIXTURE",
            quality="VERIFIED",
            evidence_ids=("EVD-CASHFLOW",),
            role=DecisionMetricRole.OPC_GLOBAL_CONTEXT,
            contract_attributable=False,
        ),
        _finance_metric(
            FinanceMetric.NEGATIVE_NET_CASHFLOW_MONTH_COUNT,
            2,
            "COUNT",
            role=DecisionMetricRole.OPC_GLOBAL_CONTEXT,
        ),
    )

    reasons, conditions = _risk_candidates(
        (),
        (),
        (limitation,),
        has_banking_options=False,
        finance_metrics=finance_metrics,
    )

    assert "2026-09" in reasons[0].detail
    assert "500,000,000 VND" in reasons[0].detail
    assert "2 tháng có net cash âm" in reasons[0].detail
    assert conditions[0].description == reasons[0].detail


def test_margin_strategies_use_conservative_deterministic_vnd_rounding() -> None:
    revenue = _finance_metric(
        FinanceMetric.ORDER_REVENUE_TOTAL, 3_100_000_000, "VND"
    )
    cost = _finance_metric(
        FinanceMetric.ORDER_ESTIMATED_COST_TOTAL, 2_356_000_000, "VND"
    )
    target = _finance_metric(
        FinanceMetric.OPC_TARGET_GROSS_MARGIN,
        0.28,
        "RATIO",
        role=DecisionMetricRole.POLICY_TARGET,
    )

    strategies, calculations = _margin_negotiation_strategies(
        revenue=revenue,
        cost=cost,
        target_margin=target,
    )
    repeated = _margin_negotiation_strategies(
        revenue=revenue,
        cost=cost,
        target_margin=target,
    )

    assert (strategies, calculations) == repeated
    assert len(strategies) == 2
    assert len(calculations) == 2
    by_type = {item.strategy_type: item for item in strategies}
    price = by_type[DecisionNegotiationStrategyType.INCREASE_CUSTOMER_PRICE]
    assert price.required_adjustment_value == 172_222_223
    assert price.resulting_revenue == 3_272_222_223
    assert price.resulting_cost == 2_356_000_000
    assert "172,222,223 VND" in price.founder_instruction
    assert "3,272,222,223 VND" in price.founder_instruction
    cost_strategy = by_type[
        DecisionNegotiationStrategyType.REDUCE_EVIDENCED_COST_AT_FIXED_REVENUE
    ]
    assert cost_strategy.required_adjustment_value == 124_000_000
    assert cost_strategy.resulting_revenue == 3_100_000_000
    assert cost_strategy.resulting_cost == 2_232_000_000
    assert "124,000,000 VND" in cost_strategy.founder_instruction
    assert "2,232,000,000 VND" in cost_strategy.founder_instruction
    assert {item.code for item in calculations} == {
        DecisionCalculationCode.MINIMUM_REVENUE_INCREASE_FOR_TARGET_MARGIN,
        DecisionCalculationCode.MINIMUM_COST_REDUCTION_FOR_TARGET_MARGIN,
    }
    assert all(
        item.condition_code == "MEET_OPC_GROSS_MARGIN_TARGET"
        for item in strategies
    )
    assert all(item.evidence_ids for item in strategies)


def test_margin_strategies_are_generic_and_round_to_exact_minimum() -> None:
    revenue = _finance_metric(FinanceMetric.ORDER_REVENUE_TOTAL, 1_000, "VND")
    cost = _finance_metric(
        FinanceMetric.ORDER_ESTIMATED_COST_TOTAL, 755, "VND"
    )
    target = _finance_metric(
        FinanceMetric.OPC_TARGET_GROSS_MARGIN,
        0.30,
        "RATIO",
        role=DecisionMetricRole.POLICY_TARGET,
    )
    generic, _ = _margin_negotiation_strategies(
        revenue=revenue,
        cost=cost,
        target_margin=target,
    )
    con004_like, _ = _margin_negotiation_strategies(
        revenue=_finance_metric(
            FinanceMetric.ORDER_REVENUE_TOTAL, 3_100_000_000, "VND"
        ),
        cost=_finance_metric(
            FinanceMetric.ORDER_ESTIMATED_COST_TOTAL, 2_356_000_000, "VND"
        ),
        target_margin=_finance_metric(
            FinanceMetric.OPC_TARGET_GROSS_MARGIN,
            0.28,
            "RATIO",
            role=DecisionMetricRole.POLICY_TARGET,
        ),
    )

    by_type = {item.strategy_type: item for item in generic}
    price = by_type[DecisionNegotiationStrategyType.INCREASE_CUSTOMER_PRICE]
    cost_reduction = by_type[
        DecisionNegotiationStrategyType.REDUCE_EVIDENCED_COST_AT_FIXED_REVENUE
    ]
    assert price.required_adjustment_value == 79
    assert price.resulting_revenue == 1_079
    assert (price.resulting_revenue - price.resulting_cost) / price.resulting_revenue >= 0.30
    assert cost_reduction.required_adjustment_value == 55
    assert cost_reduction.resulting_cost == 700
    assert (
        cost_reduction.resulting_revenue - cost_reduction.resulting_cost
    ) / cost_reduction.resulting_revenue >= 0.30
    assert {item.strategy_id for item in generic}.isdisjoint(
        item.strategy_id for item in con004_like
    )


def test_margin_strategy_candidates_are_absent_when_target_is_met_or_inputs_missing() -> None:
    current = _finance_metric(FinanceMetric.ORDER_GROSS_MARGIN, 0.30, "RATIO")
    target = _finance_metric(
        FinanceMetric.OPC_TARGET_GROSS_MARGIN,
        0.28,
        "RATIO",
        role=DecisionMetricRole.POLICY_TARGET,
    )
    revenue = _finance_metric(
        FinanceMetric.ORDER_REVENUE_TOTAL, 3_100_000_000, "VND"
    )
    cost = _finance_metric(
        FinanceMetric.ORDER_ESTIMATED_COST_TOTAL, 2_356_000_000, "VND"
    )

    _, _, strategies, calculations = _metric_candidates(
        (current, target, revenue, cost)
    )

    assert strategies == ()
    assert calculations == ()
    assert _margin_negotiation_strategies(
        revenue=revenue,
        cost=None,
        target_margin=target,
    ) == ((), ())


def test_below_target_margin_without_operands_is_explicitly_not_evaluable() -> None:
    current = _finance_metric(FinanceMetric.ORDER_GROSS_MARGIN, 0.24, "RATIO")
    target = _finance_metric(
        FinanceMetric.OPC_TARGET_GROSS_MARGIN,
        0.28,
        "RATIO",
        role=DecisionMetricRole.POLICY_TARGET,
    )

    _, conditions, strategies, calculations = _metric_candidates(
        (current, target)
    )

    assert len(conditions) == 1
    condition = conditions[0]
    assert condition.code == MARGIN_STRATEGY_INPUTS_CONDITION_CODE
    assert condition.status is DecisionConditionStatus.NOT_EVALUABLE
    assert "cannot support a bounded strategy" in condition.description
    assert "precomputed" not in condition.description
    assert not decision_conditions_support_negotiation(conditions)
    assert strategies == ()
    assert calculations == ()


@pytest.mark.parametrize("missing_metric", ("CURRENT", "TARGET"))
def test_missing_margin_benchmark_blocks_accept_and_negotiation(
    missing_metric: str,
) -> None:
    current = _finance_metric(FinanceMetric.ORDER_GROSS_MARGIN, 0.24, "RATIO")
    target = _finance_metric(
        FinanceMetric.OPC_TARGET_GROSS_MARGIN,
        0.28,
        "RATIO",
        role=DecisionMetricRole.POLICY_TARGET,
    )
    metrics = (target,) if missing_metric == "CURRENT" else (current,)

    _, conditions, strategies, calculations = _metric_candidates(metrics)

    assert len(conditions) == 1
    condition = conditions[0]
    assert condition.code == MARGIN_BENCHMARK_INPUTS_CONDITION_CODE
    assert condition.status is DecisionConditionStatus.NOT_EVALUABLE
    assert condition.target is None
    assert not decision_conditions_support_negotiation(conditions)
    assert strategies == ()
    assert calculations == ()


def test_missing_both_margin_benchmarks_uses_exact_fallback_lineage() -> None:
    _, conditions, strategies, calculations = _metric_candidates(
        (),
        fallback_reference_id="IDP-REF",
        fallback_evidence_ids=("EVD-IDP",),
    )

    assert len(conditions) == 1
    condition = conditions[0]
    assert condition.code == MARGIN_BENCHMARK_INPUTS_CONDITION_CODE
    assert condition.source_reference_ids == ("IDP-REF",)
    assert condition.evidence_ids == ("EVD-IDP",)
    assert not decision_conditions_support_negotiation(conditions)
    assert strategies == ()
    assert calculations == ()


@pytest.mark.parametrize(
    "invalid_case",
    ("TARGET_RANGE", "TARGET_UNIT", "TARGET_ROLE", "CURRENT_ROLE"),
)
def test_invalid_margin_benchmark_routes_to_evidence_repair(
    invalid_case: str,
) -> None:
    current_role = (
        DecisionMetricRole.POLICY_TARGET
        if invalid_case == "CURRENT_ROLE"
        else DecisionMetricRole.CASE_FACT
    )
    target_role = (
        DecisionMetricRole.CASE_FACT
        if invalid_case == "TARGET_ROLE"
        else DecisionMetricRole.POLICY_TARGET
    )
    current = _finance_metric(
        FinanceMetric.ORDER_GROSS_MARGIN,
        0.24,
        "RATIO",
        role=current_role,
    )
    target = _finance_metric(
        FinanceMetric.OPC_TARGET_GROSS_MARGIN,
        1.2 if invalid_case == "TARGET_RANGE" else 0.28,
        "VND" if invalid_case == "TARGET_UNIT" else "RATIO",
        role=target_role,
    )

    _, conditions, strategies, calculations = _metric_candidates(
        (current, target)
    )

    assert len(conditions) == 1
    assert conditions[0].code == MARGIN_BENCHMARK_INPUTS_CONDITION_CODE
    assert conditions[0].status is DecisionConditionStatus.NOT_EVALUABLE
    assert not decision_conditions_support_negotiation(conditions)
    assert strategies == ()
    assert calculations == ()


def test_packet_is_stable_and_opens_only_deterministically_eligible_outcomes() -> None:
    async def scenario() -> None:
        _, package_artifact, package, final_artifact, final_risk = await _inputs()

        first = build_decision_scenario_packet(
            package_artifact=package_artifact,
            package=package,
            final_risk_artifact=final_artifact,
            final_risk=final_risk,
        )
        second = build_decision_scenario_packet(
            package_artifact=package_artifact,
            package=package,
            final_risk_artifact=final_artifact,
            final_risk=final_risk,
        )

        assert first == second
        assert DecisionRecommendation.NOT_EVALUABLE in first.allowed_recommendations
        assert DecisionRecommendation.DO_NOT_ACCEPT not in first.allowed_recommendations
        assert all(
            item.contract_attributable
            for item in first.finance_metrics
            if item.role.value == "CASE_FACT"
        )
        assert first.known_evidence_ids
        assert first.reason_candidates

    asyncio.run(scenario())


def test_missing_margin_benchmarks_override_high_risk_negotiation_path() -> None:
    async def scenario() -> None:
        initial = _risk(
            assessment_status=RiskAssessmentStatus.LIMITED_BY_EVIDENCE,
            risk_level=RiskLevel.HIGH,
            severity=RiskSeverity.HIGH,
        )
        _, package_artifact, package, final_artifact, final_risk = await _inputs(
            risk=initial
        )

        packet = build_decision_scenario_packet(
            package_artifact=package_artifact,
            package=package,
            final_risk_artifact=final_artifact,
            final_risk=final_risk,
        )

        assert packet.allowed_recommendations == (
            DecisionRecommendation.NOT_EVALUABLE,
        )
        assert DecisionRecommendation.ACCEPT not in packet.allowed_recommendations
        assert DecisionRecommendation.DO_NOT_ACCEPT not in packet.allowed_recommendations
        assert any(
            item.code == MARGIN_BENCHMARK_INPUTS_CONDITION_CODE
            for item in packet.condition_candidates
        )

    asyncio.run(scenario())


def test_guard_accepts_only_exact_candidates_and_produces_stable_analysis() -> None:
    async def scenario() -> None:
        initial = _risk(
            assessment_status=RiskAssessmentStatus.COMPLETE,
            risk_level=RiskLevel.HIGH,
            severity=RiskSeverity.HIGH,
        )
        _, package_artifact, package, final_artifact, final_risk = await _inputs(
            risk=initial
        )
        packet = build_decision_scenario_packet(
            package_artifact=package_artifact,
            package=package,
            final_risk_artifact=final_artifact,
            final_risk=final_risk,
        )
        composition = _composition(packet)

        first = guard_ai_decision_composition(
            packet=packet, composition=composition
        )
        second = guard_ai_decision_composition(
            packet=packet, composition=composition
        )

        assert first == second
        assert first.recommendation is DecisionRecommendation.NOT_EVALUABLE
        assert first.deterministic_guard_passed is True
        assert first.calculations_performed_by_model is False
        assert first.approval_requested is False
        assert first.external_action_performed is False

        invented_reason = composition.proposal.reasons[0].model_copy(
            update={"detail": "Invented unsupported detail."}
        )
        forged = composition.model_copy(
            update={
                "proposal": composition.proposal.model_copy(
                    update={
                        "reasons": (
                            invented_reason,
                            *composition.proposal.reasons[1:],
                        )
                    }
                )
            }
        )
        with pytest.raises(
            DecisionAnalysisBoundaryError,
            match="reason was not selected exactly",
        ):
            guard_ai_decision_composition(packet=packet, composition=forged)

        unsafe_claim = composition.model_copy(
            update={
                "proposal": composition.proposal.model_copy(
                    update={
                        "executive_summary": (
                            "Founder already approved this recommendation."
                        )
                    }
                )
            }
        )
        with pytest.raises(
            DecisionAnalysisBoundaryError,
            match="claims an approval",
        ):
            guard_ai_decision_composition(
                packet=packet,
                composition=unsafe_claim,
            )

    asyncio.run(scenario())


def test_context_and_packet_reject_cross_version_or_forged_final_risk() -> None:
    async def scenario() -> None:
        repository, package_artifact, package, final_artifact, final_risk = (
            await _inputs()
        )
        loader = DecisionAnalysisContextLoader(artifacts=repository)
        context = ExecutionContext(
            evaluation_case_id=package.evaluation_case_id,
            dataset_id=package.dataset_id,
            workflow_run_id="RUN-DECISION-TEST",
            input_artifact_ids=(final_artifact.artifact_id,),
            requested_scope=(EvaluationScope.RISK,),
            component_input={"composer_configuration_hash": "CFG-DECISION-TEST"},
            current_node="AI_DECISION_ANALYSIS",
        )
        loaded = await loader.load(context)
        assert loaded.final_risk == final_risk
        assert loaded.package == package

        wrong_version = final_risk.model_copy(
            update={
                "internal_decision_package_artifact_version": (
                    package_artifact.version + 1
                )
            }
        )
        with pytest.raises(DecisionAnalysisBoundaryError, match="exact"):
            build_decision_scenario_packet(
                package_artifact=package_artifact,
                package=package,
                final_risk_artifact=final_artifact,
                final_risk=wrong_version,
            )

        repository = InMemoryArtifactRepository()
        await repository.save(
            final_artifact.model_copy(
                update={"input_artifact_ids": ("ART-WRONG-PACKAGE",)}
            )
        )
        with pytest.raises(DecisionAnalysisContextError, match="unknown artifact"):
            await DecisionAnalysisContextLoader(artifacts=repository).load(context)

    asyncio.run(scenario())


class _ExactComposer:
    def __init__(self) -> None:
        self.packet = None

    async def compose(self, payload):
        self.packet = payload
        return _composition(payload)


def test_component_emits_analysis_only_and_card_binds_exact_analysis() -> None:
    async def scenario() -> None:
        repository, package_artifact, package, final_artifact, _ = await _inputs()
        composer = _ExactComposer()
        component = DecisionAnalysisAgent(
            context_loader=DecisionAnalysisContextLoader(artifacts=repository),
            composer=composer,
        )
        context = ExecutionContext(
            evaluation_case_id=package.evaluation_case_id,
            dataset_id=package.dataset_id,
            workflow_run_id="RUN-DECISION-COMPONENT",
            input_artifact_ids=(final_artifact.artifact_id,),
            requested_scope=(EvaluationScope.RISK,),
            component_input={"composer_configuration_hash": "CFG-DECISION-TEST"},
            current_node="AI_DECISION_ANALYSIS",
        )

        result = await component.execute(context)

        assert result.status in {
            ComponentStatus.COMPLETED,
            ComponentStatus.COMPLETED_WITH_WARNINGS,
        }
        assert result.analysis is not None
        assert result.scenario_packet is not None
        assert len(result.artifacts) == 1
        assert result.artifacts[0].artifact_type is ArtifactType.AI_DECISION_ANALYSIS
        assert result.approval_signals == ()
        assert result.action_commands == ()

        analysis_artifact = ArtifactEnvelope(
            artifact_id="ART-AI-DECISION-TEST",
            artifact_type=ArtifactType.AI_DECISION_ANALYSIS,
            evaluation_case_id=package.evaluation_case_id,
            producer=component.component_id,
            version=1,
            status=ArtifactStatus.CREATED,
            payload=result.analysis.model_dump(mode="json"),
            evidence_refs=result.artifacts[0].evidence_refs,
            input_artifact_ids=(final_artifact.artifact_id,),
            input_hash="HASH-AI-DECISION-TEST",
            validation_status=ValidationStatus.VALID,
            validation_notes=(),
            created_at=datetime.now(UTC),
        )
        card = assemble_decision_card(
            packet=result.scenario_packet,
            analysis_artifact=analysis_artifact,
            analysis=result.analysis,
        )
        assert card.recommendation is result.analysis.recommendation
        assert card.ai_analysis_artifact.artifact_id == analysis_artifact.artifact_id
        assert card.founder_decision_recorded is False
        assert card.approval_requested is False
        assert card.external_action_performed is False
        assert card.internal_decision_package_artifact.artifact_id == (
            package_artifact.artifact_id
        )

        await repository.save(analysis_artifact)
        card_result = await DecisionCardAssembler(
            context_loader=DecisionCardContextLoader(artifacts=repository)
        ).execute(
            context.model_copy(
                update={
                    "input_artifact_ids": (analysis_artifact.artifact_id,),
                    "current_node": "DECISION_CARD_ASSEMBLY",
                }
            )
        )
        assert card_result.status in {
            ComponentStatus.COMPLETED,
            ComponentStatus.COMPLETED_WITH_WARNINGS,
        }
        assert card_result.decision_card == card
        assert len(card_result.artifacts) == 1
        assert card_result.artifacts[0].artifact_type is ArtifactType.DECISION_CARD
        assert card_result.approval_signals == ()
        assert card_result.action_commands == ()

    asyncio.run(scenario())
