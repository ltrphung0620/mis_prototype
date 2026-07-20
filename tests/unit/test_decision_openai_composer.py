"""Boundary, fallback, and identity tests for OpenAI Decision composition."""

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from opc_mis.domain.decision_analysis import (
    _margin_negotiation_strategies,
    guard_ai_decision_composition,
)
from opc_mis.domain.decision_models import (
    MARGIN_NEGOTIATION_CONDITION_CODE,
    MARGIN_NEGOTIATION_CONDITION_DESCRIPTION,
    MARGIN_NEGOTIATION_CONDITION_EXPECTED_RISK_EFFECT,
    MARGIN_NEGOTIATION_CONDITION_TITLE,
    MARGIN_NEGOTIATION_CONDITION_VERIFICATION_EVIDENCE_TYPES,
    AIDecisionAttentionPointDraft,
    AIDecisionComposition,
    AIDecisionProposalDraft,
    AIDecisionReasonDraft,
    DecisionAnalysisSource,
    DecisionCalculation,
    DecisionCalculationOperand,
    DecisionConditionCandidate,
    DecisionConditionCategory,
    DecisionConditionStatus,
    DecisionConditionTarget,
    DecisionConfidence,
    DecisionEnforcementPoint,
    DecisionMetricRole,
    DecisionMetricSnapshot,
    DecisionNegotiationStrategyCandidate,
    DecisionOptionSnapshot,
    DecisionReasonCandidate,
    DecisionRecommendation,
    DecisionReferenceEvidence,
    DecisionReferenceKind,
    DecisionScenarioPacket,
    DecisionTargetOperator,
    ExactDecisionArtifactRef,
    NegotiationConditionDraft,
    decision_negotiation_strategy_founder_instruction,
    decision_packet_input_hash,
    decision_scenario_packet_id,
)
from opc_mis.domain.enums import (
    ArtifactType,
    FinalRiskAssessmentStatus,
    FinanceMetric,
    MajorExceptionStatus,
    RiskLevel,
)
from opc_mis.domain.lineage import deterministic_id
from opc_mis.infrastructure.openai.decision_composer import (
    OpenAIDecisionAnalysisComposer,
    ResilientDecisionAnalysisComposer,
)
from opc_mis.infrastructure.openai.decision_fallback import (
    DeterministicDecisionAnalysisComposer,
)
from opc_mis.infrastructure.openai.decision_guard import validate_decision_proposal


def _reason_candidate() -> DecisionReasonCandidate:
    values = {
        "code": "BANKING_RESULT_NON_BINDING",
        "title": "Kết quả ngân hàng chưa ràng buộc",
        "detail": "Precheck hiện tại chưa phải cam kết chính thức từ ngân hàng.",
        "source_reference_ids": ("BANK-REF",),
        "evidence_ids": ("EVD-BANK",),
    }
    return DecisionReasonCandidate(
        candidate_id=deterministic_id(
            "DRC",
            values["code"],
            values["title"],
            values["detail"],
            values["source_reference_ids"],
            values["evidence_ids"],
        ),
        **values,
    )


def _condition_candidate() -> DecisionConditionCandidate:
    target = DecisionConditionTarget(
        metric="SUPPORTED_AMOUNT",
        operator=DecisionTargetOperator.GREATER_THAN_OR_EQUAL,
        current_value=420_000_000,
        target_value=420_000_000,
        unit="VND",
        currency="VND",
        source_reference_ids=("BANK-REF",),
        evidence_ids=("EVD-BANK",),
    )
    values = {
        "code": "BINDING_PERFORMANCE_BOND_REQUIRED",
        "category": DecisionConditionCategory.BANKING,
        "title": "Xác nhận bảo lãnh mang tính ràng buộc",
        "description": "Cần phản hồi chính thức cho nghĩa vụ bảo lãnh của hợp đồng.",
        "status": DecisionConditionStatus.OPEN,
        "enforcement_point": DecisionEnforcementPoint.BEFORE_CONTRACT_SIGNING,
        "target": target,
        "verification_evidence_types": ("BINDING_BANK_RESPONSE",),
        "expected_risk_effect": "Kiểm soát khả năng không đáp ứng nghĩa vụ bảo lãnh.",
        "source_reference_ids": ("BANK-REF",),
        "evidence_ids": ("EVD-BANK",),
    }
    return DecisionConditionCandidate(
        candidate_id=deterministic_id(
            "DCC",
            values["code"],
            values["category"],
            values["title"],
            values["description"],
            values["status"],
            values["enforcement_point"],
            target.model_dump(mode="json"),
            values["verification_evidence_types"],
            values["expected_risk_effect"],
            values["source_reference_ids"],
            values["evidence_ids"],
        ),
        **values,
    )


def scenario_packet() -> DecisionScenarioPacket:
    reason = _reason_candidate()
    condition = _condition_candidate()
    current_margin = DecisionMetricSnapshot(
        fact_id="FACT-MARGIN-READY",
        metric=FinanceMetric.ORDER_GROSS_MARGIN.value,
        value=0.30,
        unit="RATIO",
        calculation="SAFE_RATIO",
        quality="VERIFIED",
        evidence_ids=("EVD-MARGIN-READY",),
        role=DecisionMetricRole.CASE_FACT,
        contract_attributable=True,
    )
    target_margin = DecisionMetricSnapshot(
        fact_id="FACT-TARGET-READY",
        metric=FinanceMetric.OPC_TARGET_GROSS_MARGIN.value,
        value=0.28,
        unit="RATIO",
        calculation="SOURCE",
        quality="VERIFIED",
        evidence_ids=("EVD-TARGET-READY",),
        role=DecisionMetricRole.POLICY_TARGET,
        contract_attributable=False,
    )
    values = {
        "evaluation_case_id": "CASE-X",
        "dataset_id": "DATASET-X",
        "contract_id": "CON-X",
        "internal_decision_package_id": "IDP-X",
        "final_risk_assessment_id": "FRA-X",
        "internal_decision_package_artifact": ExactDecisionArtifactRef(
            artifact_id="ART-IDP-X",
            artifact_type=ArtifactType.INTERNAL_DECISION_PACKAGE,
            version=1,
            input_hash="IDP-HASH-X",
        ),
        "final_risk_artifact": ExactDecisionArtifactRef(
            artifact_id="ART-FRA-X",
            artifact_type=ArtifactType.FINAL_RISK_ASSESSMENT,
            version=1,
            input_hash="FRA-HASH-X",
        ),
        "assembly_path": "CONDITIONAL_DOCUMENT_READY",
        "finance_metrics": (current_margin, target_margin),
        "final_risk_status": FinalRiskAssessmentStatus.LIMITED_BY_EVIDENCE,
        "banking_options": (
            DecisionOptionSnapshot(
                option_id="BOPT-X",
                bank_product_id="BANKPROD-X",
                provider="Ngân hàng mẫu",
                product_name="Bảo lãnh thực hiện hợp đồng",
                requested_amount=420_000_000,
                supported_amount=420_000_000,
                precheck_outcome="CONDITIONAL_PRECHECK",
                precheck_authority="SIMULATED_NON_BINDING",
                non_binding=True,
                evidence_ids=("EVD-BANK",),
            ),
        ),
        "residual_risk_level": RiskLevel.HIGH,
        "major_exception_status": MajorExceptionStatus.NOT_EVALUABLE,
        "reason_candidates": (reason,),
        "condition_candidates": (condition,),
        "allowed_recommendations": (
            DecisionRecommendation.NEGOTIATE_CONDITIONS_TO_ACCEPT,
            DecisionRecommendation.NOT_EVALUABLE,
        ),
        "allowed_numeric_display_values": ("420,000,000 VND",),
        "reference_evidence": (
            DecisionReferenceEvidence(
                reference_id="BANK-REF",
                kind=DecisionReferenceKind.BANKING_RESULT,
                evidence_ids=("EVD-BANK",),
            ),
            DecisionReferenceEvidence(
                reference_id="CONTROL-REF",
                kind=DecisionReferenceKind.REQUIRED_CONTROL,
                evidence_ids=("EVD-CONTROL",),
            ),
            DecisionReferenceEvidence(
                reference_id=current_margin.fact_id,
                kind=DecisionReferenceKind.FINANCE_FACT,
                evidence_ids=current_margin.evidence_ids,
            ),
            DecisionReferenceEvidence(
                reference_id=target_margin.fact_id,
                kind=DecisionReferenceKind.FINANCE_FACT,
                evidence_ids=target_margin.evidence_ids,
            ),
        ),
        "known_evidence_ids": (
            "EVD-BANK",
            "EVD-CONTROL",
            "EVD-MARGIN-READY",
            "EVD-TARGET-READY",
        ),
        "excluded_opc_global_finance_fact_count": 1,
        "excluded_opc_global_operations_fact_count": 0,
    }
    draft = DecisionScenarioPacket.model_construct(packet_id="PENDING", **values)
    return DecisionScenarioPacket(
        packet_id=decision_scenario_packet_id(draft),
        **values,
    )


def valid_proposal() -> AIDecisionProposalDraft:
    reason = AIDecisionReasonDraft.model_validate(
        _reason_candidate().model_dump(mode="json", exclude={"candidate_id"})
    )
    condition = NegotiationConditionDraft.model_validate(
        _condition_candidate().model_dump(mode="json", exclude={"candidate_id"})
    )
    return AIDecisionProposalDraft(
        recommendation=DecisionRecommendation.NEGOTIATE_CONDITIONS_TO_ACCEPT,
        executive_summary=(
            "Nên tiếp tục đàm phán và yêu cầu xác nhận bảo lãnh 420,000,000 VND "
            "trước khi chấp nhận hợp đồng."
        ),
        reasons=(reason,),
        conditions=(condition,),
        selected_option_ids=("BOPT-X",),
        confidence=DecisionConfidence.MEDIUM,
        human_attention_points=(
            AIDecisionAttentionPointDraft(
                code="REVIEW_BANK_TERMS",
                text="Founder cần xem điều kiện tài chính trước khi cam kết.",
                source_reference_ids=("CONTROL-REF",),
                evidence_ids=("EVD-CONTROL",),
            ),
        ),
    )


def _margin_strategy_packet() -> DecisionScenarioPacket:
    def metric(
        fact_id: str,
        metric_name: str,
        value: int | float,
        unit: str,
        evidence_id: str,
        *,
        role: DecisionMetricRole = DecisionMetricRole.CASE_FACT,
    ) -> DecisionMetricSnapshot:
        return DecisionMetricSnapshot(
            fact_id=fact_id,
            metric=metric_name,
            value=value,
            unit=unit,
            calculation="TEST_FIXTURE",
            quality="VERIFIED",
            evidence_ids=(evidence_id,),
            role=role,
            contract_attributable=role is DecisionMetricRole.CASE_FACT,
        )

    revenue = metric("FACT-REV", "ORDER_REVENUE_TOTAL", 3_100_000_000, "VND", "EVD-REV")
    cost = metric(
        "FACT-COST",
        "ORDER_ESTIMATED_COST_TOTAL",
        2_356_000_000,
        "VND",
        "EVD-COST",
    )
    current_margin = metric(
        "FACT-MARGIN",
        FinanceMetric.ORDER_GROSS_MARGIN.value,
        0.24,
        "RATIO",
        "EVD-MARGIN",
    )
    target_metric = metric(
        "FACT-TARGET",
        "OPC_TARGET_GROSS_MARGIN",
        0.28,
        "RATIO",
        "EVD-TARGET",
        role=DecisionMetricRole.POLICY_TARGET,
    )
    strategies, calculations = _margin_negotiation_strategies(
        revenue=revenue,
        cost=cost,
        target_margin=target_metric,
    )
    target = DecisionConditionTarget(
        metric="ORDER_GROSS_MARGIN",
        operator=DecisionTargetOperator.GREATER_THAN_OR_EQUAL,
        current_value=0.24,
        target_value=0.28,
        unit="RATIO",
        source_reference_ids=("FACT-MARGIN", "FACT-TARGET"),
        evidence_ids=("EVD-MARGIN", "EVD-TARGET"),
    )
    condition_values = {
        "code": MARGIN_NEGOTIATION_CONDITION_CODE,
        "category": DecisionConditionCategory.COMMERCIAL,
        "title": MARGIN_NEGOTIATION_CONDITION_TITLE,
        "description": MARGIN_NEGOTIATION_CONDITION_DESCRIPTION,
        "status": DecisionConditionStatus.OPEN,
        "enforcement_point": DecisionEnforcementPoint.BEFORE_ACCEPTANCE,
        "target": target,
        "verification_evidence_types": (
            MARGIN_NEGOTIATION_CONDITION_VERIFICATION_EVIDENCE_TYPES
        ),
        "expected_risk_effect": (
            MARGIN_NEGOTIATION_CONDITION_EXPECTED_RISK_EFFECT
        ),
        "source_reference_ids": ("FACT-MARGIN", "FACT-TARGET"),
        "evidence_ids": ("EVD-MARGIN", "EVD-TARGET"),
    }
    condition = DecisionConditionCandidate(
        candidate_id=deterministic_id(
            "DCC",
            condition_values["code"],
            condition_values["category"],
            condition_values["title"],
            condition_values["description"],
            condition_values["status"],
            condition_values["enforcement_point"],
            target.model_dump(mode="json"),
            condition_values["verification_evidence_types"],
            condition_values["expected_risk_effect"],
            condition_values["source_reference_ids"],
            condition_values["evidence_ids"],
        ),
        **condition_values,
    )
    base = scenario_packet()
    values = {
        field_name: getattr(base, field_name)
        for field_name in DecisionScenarioPacket.model_fields
        if field_name != "packet_id"
    }
    values.update(
        {
            "finance_metrics": (revenue, cost, current_margin, target_metric),
            "calculations": calculations,
            "condition_candidates": (condition,),
            "negotiation_strategy_candidates": strategies,
            "reference_evidence": (
                DecisionReferenceEvidence(
                    reference_id="BANK-REF",
                    kind=DecisionReferenceKind.BANKING_RESULT,
                    evidence_ids=("EVD-BANK",),
                ),
                DecisionReferenceEvidence(
                    reference_id="FACT-REV",
                    kind=DecisionReferenceKind.FINANCE_FACT,
                    evidence_ids=("EVD-REV",),
                ),
                DecisionReferenceEvidence(
                    reference_id="FACT-COST",
                    kind=DecisionReferenceKind.FINANCE_FACT,
                    evidence_ids=("EVD-COST",),
                ),
                DecisionReferenceEvidence(
                    reference_id="FACT-MARGIN",
                    kind=DecisionReferenceKind.FINANCE_FACT,
                    evidence_ids=("EVD-MARGIN",),
                ),
                DecisionReferenceEvidence(
                    reference_id="FACT-TARGET",
                    kind=DecisionReferenceKind.FINANCE_FACT,
                    evidence_ids=("EVD-TARGET",),
                ),
            ),
            "known_evidence_ids": (
                "EVD-BANK",
                "EVD-REV",
                "EVD-COST",
                "EVD-MARGIN",
                "EVD-TARGET",
            ),
            "allowed_numeric_display_values": (
                "24%",
                "28%",
                "172,222,223 VND",
                "124,000,000 VND",
            ),
        }
    )
    draft = DecisionScenarioPacket.model_construct(packet_id="PENDING", **values)
    return DecisionScenarioPacket(
        packet_id=decision_scenario_packet_id(draft),
        **values,
    )


def _margin_strategy_proposal(packet: DecisionScenarioPacket) -> AIDecisionProposalDraft:
    condition = NegotiationConditionDraft.model_validate(
        packet.condition_candidates[0].model_dump(
            mode="json", exclude={"candidate_id"}
        )
    )
    return AIDecisionProposalDraft(
        recommendation=DecisionRecommendation.NEGOTIATE_CONDITIONS_TO_ACCEPT,
        executive_summary=(
            "Ưu tiên phương án thương mại đã được tính trước và chạy lại Finance "
            "sau khi có bằng chứng mới."
        ),
        reasons=(
            AIDecisionReasonDraft.model_validate(
                packet.reason_candidates[0].model_dump(
                    mode="json", exclude={"candidate_id"}
                )
            ),
        ),
        conditions=(condition,),
        selected_negotiation_strategy_ids=(
            packet.negotiation_strategy_candidates[0].strategy_id,
        ),
        confidence=DecisionConfidence.MEDIUM,
    )


def _rehash_calculation(values: dict[str, object]) -> DecisionCalculation:
    raw_operands = values["operands"]
    assert isinstance(raw_operands, tuple)
    operands = tuple(
        DecisionCalculationOperand.model_validate(item) for item in raw_operands
    )
    values["operands"] = operands
    values["calculation_id"] = deterministic_id(
        "DCALC",
        values["code"],
        values["formula"],
        tuple(item.model_dump(mode="json") for item in operands),
        values["result_value"],
        values["result_unit"],
    )
    return DecisionCalculation.model_validate(values)


def _rehash_strategy(
    values: dict[str, object],
) -> DecisionNegotiationStrategyCandidate:
    values["strategy_id"] = deterministic_id(
        "DNSTRAT",
        values["condition_code"],
        values["strategy_type"],
        values["title"],
        values["founder_instruction"],
        values["assumptions"],
        values["baseline_revenue"],
        values["baseline_cost"],
        values["target_margin"],
        values["required_adjustment_value"],
        values["resulting_revenue"],
        values["resulting_cost"],
        values["currency"],
        values["calculation_id"],
        values["verification_evidence_types"],
        values["source_reference_ids"],
        values["evidence_ids"],
    )
    return DecisionNegotiationStrategyCandidate.model_validate(values)


def _rehash_condition(values: dict[str, object]) -> DecisionConditionCandidate:
    target_value = values["target"]
    target = (
        None
        if target_value is None
        else DecisionConditionTarget.model_validate(target_value)
    )
    values["target"] = target
    values["candidate_id"] = deterministic_id(
        "DCC",
        values["code"],
        values["category"],
        values["title"],
        values["description"],
        values["status"],
        values["enforcement_point"],
        None if target is None else target.model_dump(mode="json"),
        values["verification_evidence_types"],
        values["expected_risk_effect"],
        values["source_reference_ids"],
        values["evidence_ids"],
    )
    return DecisionConditionCandidate.model_validate(values)


def _packet_values(packet: DecisionScenarioPacket) -> dict[str, object]:
    return packet.model_dump(mode="python")


def _rehashed_packet_values(
    packet: DecisionScenarioPacket,
    **updates: object,
) -> dict[str, object]:
    draft = packet.model_copy(update={"packet_id": "PENDING", **updates})
    values = draft.model_dump(mode="python")
    values["packet_id"] = decision_scenario_packet_id(draft)
    return values


def _composer(
    client: object,
    *,
    prompt_version: str = "decision-analysis-v1",
) -> OpenAIDecisionAnalysisComposer:
    return OpenAIDecisionAnalysisComposer(
        client=client,  # type: ignore[arg-type]
        model="MODEL-X",
        prompt_path=Path("config/prompts/decision_analysis.md"),
        prompt_version=prompt_version,
    )


def test_openai_adapter_uses_strict_schema_and_exact_packet() -> None:
    proposal = valid_proposal()

    class FakeResponses:
        async def parse(self, **kwargs: object) -> object:
            assert kwargs["text_format"] is AIDecisionProposalDraft
            assert kwargs["store"] is False
            request_input = kwargs["input"]
            model_payload = json.loads(request_input[1]["content"])  # type: ignore[index]
            assert model_payload["packet_id"] == scenario_packet().packet_id
            assert model_payload["condition_candidates"][0]["target"]["target_value"] == 420_000_000
            return SimpleNamespace(output_parsed=proposal)

    result = asyncio.run(
        _composer(SimpleNamespace(responses=FakeResponses())).compose(scenario_packet())
    )

    assert result.source is DecisionAnalysisSource.OPENAI
    assert result.proposal == proposal
    assert result.model == "MODEL-X"
    assert result.prompt_version == "decision-analysis-v1"


def test_openai_adapter_receives_precomputed_margin_strategy_values() -> None:
    packet = _margin_strategy_packet()
    proposal = _margin_strategy_proposal(packet)

    class FakeResponses:
        async def parse(self, **kwargs: object) -> object:
            request_input = kwargs["input"]
            model_payload = json.loads(request_input[1]["content"])  # type: ignore[index]
            strategies = model_payload["negotiation_strategy_candidates"]
            assert strategies[0]["required_adjustment_value"] == 172_222_223
            assert strategies[1]["required_adjustment_value"] == 124_000_000
            return SimpleNamespace(output_parsed=proposal)

    result = asyncio.run(
        _composer(SimpleNamespace(responses=FakeResponses())).compose(packet)
    )

    assert result.proposal.selected_negotiation_strategy_ids == (
        packet.negotiation_strategy_candidates[0].strategy_id,
    )


def test_openai_adapter_hydrates_candidates_and_mandatory_conditions() -> None:
    packet = scenario_packet()
    proposal = valid_proposal()
    abbreviated = proposal.model_copy(
        update={
            "reasons": (
                proposal.reasons[0].model_copy(
                    update={"title": "Model-authored text is not authoritative"}
                ),
            ),
            "conditions": (),
        }
    )

    class FakeResponses:
        async def parse(self, **kwargs: object) -> object:
            del kwargs
            return SimpleNamespace(output_parsed=abbreviated)

    result = asyncio.run(
        _composer(SimpleNamespace(responses=FakeResponses())).compose(packet)
    )

    assert result.proposal.reasons[0].title == packet.reason_candidates[0].title
    assert tuple(item.code for item in result.proposal.conditions) == tuple(
        item.code for item in packet.condition_candidates
    )
    validate_decision_proposal(result.proposal, packet)


def test_openai_adapter_restores_margin_condition_selected_by_strategy() -> None:
    packet = _margin_strategy_packet()
    proposal = _margin_strategy_proposal(packet).model_copy(update={"conditions": ()})

    class FakeResponses:
        async def parse(self, **kwargs: object) -> object:
            del kwargs
            return SimpleNamespace(output_parsed=proposal)

    result = asyncio.run(
        _composer(SimpleNamespace(responses=FakeResponses())).compose(packet)
    )

    assert tuple(item.code for item in result.proposal.conditions) == (
        MARGIN_NEGOTIATION_CONDITION_CODE,
    )
    assert result.proposal.selected_negotiation_strategy_ids == (
        packet.negotiation_strategy_candidates[0].strategy_id,
    )
    validate_decision_proposal(result.proposal, packet)


def test_guard_rejects_an_invented_condition_target() -> None:
    proposal = valid_proposal()
    condition = proposal.conditions[0]
    assert condition.target is not None
    invented = proposal.model_copy(
        update={
            "conditions": (
                condition.model_copy(
                    update={
                        "target": condition.target.model_copy(
                            update={"target_value": 450_000_000}
                        )
                    }
                ),
            )
        }
    )

    with pytest.raises(ValueError, match="outside supplied candidates"):
        validate_decision_proposal(invented, scenario_packet())


def test_guard_accepts_one_exact_precomputed_margin_strategy() -> None:
    packet = _margin_strategy_packet()
    proposal = _margin_strategy_proposal(packet)

    validate_decision_proposal(proposal, packet)

    selected = packet.negotiation_strategy_candidates[0]
    assert selected.required_adjustment_value == 172_222_223
    assert proposal.selected_negotiation_strategy_ids == (selected.strategy_id,)


def test_packet_rejects_self_hashed_nonminimum_margin_strategy() -> None:
    packet = _margin_strategy_packet()
    strategy = packet.negotiation_strategy_candidates[0]
    calculation = next(
        item
        for item in packet.calculations
        if item.calculation_id == strategy.calculation_id
    )
    calculation_values = calculation.model_dump(mode="python")
    calculation_values["result_value"] = 200_000_000
    altered_calculation = _rehash_calculation(calculation_values)
    strategy_values = strategy.model_dump(mode="python")
    strategy_values.update(
        {
            "required_adjustment_value": 200_000_000,
            "resulting_revenue": 3_300_000_000,
            "calculation_id": altered_calculation.calculation_id,
        }
    )
    strategy_values["founder_instruction"] = (
        decision_negotiation_strategy_founder_instruction(
            strategy_type=strategy.strategy_type,
            baseline_revenue=strategy.baseline_revenue,
            baseline_cost=strategy.baseline_cost,
            required_adjustment_value=200_000_000,
            resulting_revenue=3_300_000_000,
            resulting_cost=strategy.resulting_cost,
        )
    )
    altered_strategy = _rehash_strategy(strategy_values)
    packet_values = _packet_values(packet)
    packet_values["calculations"] = tuple(
        altered_calculation if item == calculation else item
        for item in packet.calculations
    )
    packet_values["negotiation_strategy_candidates"] = tuple(
        altered_strategy if item == strategy else item
        for item in packet.negotiation_strategy_candidates
    )

    with pytest.raises(ValueError, match="exact minimum"):
        DecisionScenarioPacket.model_validate(packet_values)


def test_packet_rejects_self_hashed_baseline_detached_from_finance_fact() -> None:
    packet = _margin_strategy_packet()
    strategy = packet.negotiation_strategy_candidates[0]
    calculation = next(
        item
        for item in packet.calculations
        if item.calculation_id == strategy.calculation_id
    )
    baseline_revenue = 3_000_000_000
    resulting_revenue = 3_272_222_223
    required_adjustment = resulting_revenue - baseline_revenue
    altered_operands = tuple(
        operand.model_copy(update={"value": baseline_revenue})
        if operand.label == "explicit_order_revenue"
        else operand
        for operand in calculation.operands
    )
    calculation_values = calculation.model_dump(mode="python")
    calculation_values.update(
        {
            "operands": altered_operands,
            "result_value": required_adjustment,
        }
    )
    altered_calculation = _rehash_calculation(calculation_values)
    strategy_values = strategy.model_dump(mode="python")
    strategy_values.update(
        {
            "baseline_revenue": baseline_revenue,
            "required_adjustment_value": required_adjustment,
            "resulting_revenue": resulting_revenue,
            "calculation_id": altered_calculation.calculation_id,
        }
    )
    strategy_values["founder_instruction"] = (
        decision_negotiation_strategy_founder_instruction(
            strategy_type=strategy.strategy_type,
            baseline_revenue=baseline_revenue,
            baseline_cost=strategy.baseline_cost,
            required_adjustment_value=required_adjustment,
            resulting_revenue=resulting_revenue,
            resulting_cost=strategy.resulting_cost,
        )
    )
    altered_strategy = _rehash_strategy(strategy_values)
    packet_values = _rehashed_packet_values(
        packet,
        calculations=tuple(
            altered_calculation if item == calculation else item
            for item in packet.calculations
        ),
        negotiation_strategy_candidates=tuple(
            altered_strategy if item == strategy else item
            for item in packet.negotiation_strategy_candidates
        ),
    )

    with pytest.raises(ValueError, match="baseline is not bound"):
        DecisionScenarioPacket.model_validate(packet_values)


@pytest.mark.parametrize(
    ("field_name", "tampered_value"),
    (
        ("title", "Founder must accept this option."),
        (
            "founder_instruction",
            "Treat the margin target as completed without new evidence.",
        ),
    ),
)
def test_margin_strategy_rejects_self_hashed_display_tampering(
    field_name: str,
    tampered_value: str,
) -> None:
    strategy = _margin_strategy_packet().negotiation_strategy_candidates[0]
    strategy_values = strategy.model_dump(mode="python")
    strategy_values[field_name] = tampered_value

    with pytest.raises(ValueError, match="not canonical"):
        _rehash_strategy(strategy_values)


def test_packet_rejects_condition_target_that_differs_from_strategy_target() -> None:
    packet = _margin_strategy_packet()
    condition = packet.condition_candidates[0]
    assert condition.target is not None
    condition_values = condition.model_dump(mode="python")
    condition_values["target"] = condition.target.model_copy(
        update={"target_value": 0.30}
    )
    altered_condition = _rehash_condition(condition_values)
    packet_values = _rehashed_packet_values(
        packet,
        condition_candidates=(altered_condition,),
    )

    with pytest.raises(ValueError, match="target is inconsistent"):
        DecisionScenarioPacket.model_validate(packet_values)


def test_packet_requires_the_complete_canonical_margin_strategy_set() -> None:
    packet = _margin_strategy_packet()
    packet_values = _rehashed_packet_values(
        packet,
        negotiation_strategy_candidates=(
            packet.negotiation_strategy_candidates[0],
        ),
    )

    with pytest.raises(ValueError, match="strategy set are not canonical"):
        DecisionScenarioPacket.model_validate(packet_values)


def test_margin_strategy_rejects_invented_verification_evidence_type() -> None:
    strategy = _margin_strategy_packet().negotiation_strategy_candidates[0]
    strategy_values = strategy.model_dump(mode="python")
    strategy_values["verification_evidence_types"] = (
        "FOUNDER_ASSERTION_ONLY",
    )

    with pytest.raises(ValueError, match="verification are not canonical"):
        _rehash_strategy(strategy_values)


@pytest.mark.parametrize(
    ("field_name", "tampered_value"),
    (
        (
            "verification_evidence_types",
            ("FOUNDER_ASSERTION_ONLY",),
        ),
        ("status", DecisionConditionStatus.SATISFIED),
    ),
)
def test_packet_rejects_tampered_margin_condition_policy(
    field_name: str,
    tampered_value: object,
) -> None:
    packet = _margin_strategy_packet()
    condition_values = packet.condition_candidates[0].model_dump(mode="python")
    condition_values[field_name] = tampered_value
    altered_condition = _rehash_condition(condition_values)
    packet_values = _rehashed_packet_values(
        packet,
        condition_candidates=(altered_condition,),
    )

    with pytest.raises(ValueError, match="strategy set are not canonical"):
        DecisionScenarioPacket.model_validate(packet_values)


def test_packet_rejects_false_margin_formula_even_when_rehashed() -> None:
    packet = _margin_strategy_packet()
    strategy = packet.negotiation_strategy_candidates[0]
    calculation = next(
        item
        for item in packet.calculations
        if item.calculation_id == strategy.calculation_id
    )
    calculation_values = calculation.model_dump(mode="python")
    calculation_values["formula"] = "baseline_revenue + 999"
    altered_calculation = _rehash_calculation(calculation_values)
    assert altered_calculation.calculation_id != calculation.calculation_id
    strategy_values = strategy.model_dump(mode="python")
    strategy_values["calculation_id"] = altered_calculation.calculation_id
    altered_strategy = _rehash_strategy(strategy_values)
    packet_values = _packet_values(packet)
    packet_values["calculations"] = tuple(
        altered_calculation if item == calculation else item
        for item in packet.calculations
    )
    packet_values["negotiation_strategy_candidates"] = tuple(
        altered_strategy if item == strategy else item
        for item in packet.negotiation_strategy_candidates
    )

    with pytest.raises(ValueError, match="exact calculation"):
        DecisionScenarioPacket.model_validate(packet_values)


@pytest.mark.parametrize(
    "tamper, expected_error",
    (
        ("REFERENCE", "unknown source"),
        ("EVIDENCE", "unrelated to its source"),
    ),
)
def test_packet_rejects_calculation_operand_lineage_tampering(
    tamper: str,
    expected_error: str,
) -> None:
    packet = _margin_strategy_packet()
    calculation = packet.calculations[0]
    operand = calculation.operands[0]
    bad_operand = operand.model_copy(
        update=(
            {"source_reference_id": "FACT-DOES-NOT-EXIST"}
            if tamper == "REFERENCE"
            else {"evidence_ids": ("EVD-TARGET",)}
        )
    )
    operands = (bad_operand, *calculation.operands[1:])
    calculation_values = calculation.model_dump(mode="python")
    calculation_values["operands"] = operands
    calculation_values["evidence_ids"] = tuple(
        dict.fromkeys(
            evidence_id
            for item in operands
            for evidence_id in item.evidence_ids
        )
    )
    altered_calculation = _rehash_calculation(calculation_values)
    packet_values = _packet_values(packet)
    packet_values["calculations"] = (
        altered_calculation,
        *packet.calculations[1:],
    )

    with pytest.raises(ValueError, match=expected_error):
        DecisionScenarioPacket.model_validate(packet_values)


def test_guard_keeps_margin_amounts_out_of_model_authored_prose() -> None:
    packet = _margin_strategy_packet()
    selected = packet.negotiation_strategy_candidates[0]
    proposal = _margin_strategy_proposal(packet).model_copy(
        update={
            "executive_summary": (
                "Đề xuất tăng giá tối thiểu 172222223 vnd cho phạm vi order đã "
                "liên kết và chạy lại Finance."
            )
        }
    )

    with pytest.raises(ValueError, match="numeric prose"):
        validate_decision_proposal(proposal, packet)
    assert selected.required_adjustment_value == 172_222_223


def test_guard_rejects_a_model_authored_margin_completion_claim() -> None:
    packet = _margin_strategy_packet()
    proposal = _margin_strategy_proposal(packet).model_copy(
        update={"executive_summary": "The target is achieved."}
    )

    with pytest.raises(ValueError, match="already met"):
        validate_decision_proposal(proposal, packet)


def test_canonical_margin_summary_replaces_model_wording_and_replays() -> None:
    packet = _margin_strategy_packet()
    model_summary = (
        "Prefer the supplied commercial strategy and rerun Finance after fresh evidence."
    )
    proposal = _margin_strategy_proposal(packet).model_copy(
        update={"executive_summary": model_summary}
    )
    validate_decision_proposal(proposal, packet)
    composition = AIDecisionComposition(
        proposal=proposal,
        source=DecisionAnalysisSource.OPENAI,
        model="test-model",
        prompt_version="decision-analysis-v2",
        input_hash=decision_packet_input_hash(packet),
    )

    analysis = guard_ai_decision_composition(
        packet=packet,
        composition=composition,
    )

    assert model_summary not in analysis.executive_summary
    assert "24%" in analysis.executive_summary
    assert "28%" in analysis.executive_summary
    assert "172,222,223 VND" in analysis.executive_summary
    assert "Điều kiện vẫn OPEN" in analysis.executive_summary
    replay_proposal = AIDecisionProposalDraft(
        recommendation=analysis.recommendation,
        executive_summary=analysis.executive_summary,
        reasons=tuple(
            AIDecisionReasonDraft.model_validate(
                item.model_dump(mode="json", exclude={"reason_id"})
            )
            for item in analysis.reasons
        ),
        conditions=tuple(
            NegotiationConditionDraft.model_validate(
                item.model_dump(mode="json", exclude={"condition_id"})
            )
            for item in analysis.conditions
        ),
        selected_negotiation_strategy_ids=(
            analysis.selected_negotiation_strategy_ids
        ),
        selected_option_ids=analysis.selected_option_ids,
        confidence=analysis.confidence,
        human_attention_points=tuple(
            AIDecisionAttentionPointDraft.model_validate(
                item.model_dump(mode="json", exclude={"attention_point_id"})
            )
            for item in analysis.human_attention_points
        ),
    )
    replay = guard_ai_decision_composition(
        packet=packet,
        composition=composition.model_copy(update={"proposal": replay_proposal}),
    )
    assert replay == analysis


@pytest.mark.parametrize(
    "unsafe_summary, expected_error",
    (
        ("Biên lợi nhuận đã đạt 28%.", "numeric prose|already met"),
        (
            "This is not final; gross margin now meets 28%.",
            "numeric prose|already met",
        ),
        (
            "Cannot approve yet, but gross margin now meets 28%.",
            "numeric prose|already met",
        ),
        (
            "Đề xuất giảm chi phí 124000000 vnd.",
            "numeric prose",
        ),
        ("Đề xuất tăng giá thêm một tỷ đồng.", "numeric prose"),
        ("Đề xuất tăng giá hàng trăm triệu đồng.", "numeric prose"),
        ("Propose an increase of eleven million VND.", "numeric prose"),
    ),
)
def test_guard_rejects_margin_completion_and_unselected_or_word_numbers(
    unsafe_summary: str,
    expected_error: str,
) -> None:
    packet = _margin_strategy_packet()
    proposal = _margin_strategy_proposal(packet).model_copy(
        update={"executive_summary": unsafe_summary}
    )

    with pytest.raises(ValueError, match=expected_error):
        validate_decision_proposal(proposal, packet)


@pytest.mark.parametrize("selection", ((), ("DNSTRAT-UNKNOWN",)))
def test_guard_rejects_missing_or_unknown_margin_strategy(
    selection: tuple[str, ...],
) -> None:
    packet = _margin_strategy_packet()
    proposal = _margin_strategy_proposal(packet).model_copy(
        update={"selected_negotiation_strategy_ids": selection}
    )

    with pytest.raises(ValueError, match="strategy"):
        validate_decision_proposal(proposal, packet)


def test_guard_rejects_selecting_both_alternative_margin_strategies() -> None:
    packet = _margin_strategy_packet()
    proposal = _margin_strategy_proposal(packet).model_copy(
        update={
            "selected_negotiation_strategy_ids": tuple(
                item.strategy_id
                for item in packet.negotiation_strategy_candidates
            )
        }
    )

    with pytest.raises(ValueError, match="exactly one"):
        validate_decision_proposal(proposal, packet)


def test_guard_rejects_numeric_prose_not_supplied_by_calculator() -> None:
    proposal = valid_proposal().model_copy(
        update={"executive_summary": "Nên yêu cầu bảo lãnh 450 triệu VND."}
    )

    with pytest.raises(ValueError, match="numeric prose"):
        validate_decision_proposal(proposal, scenario_packet())


def test_guard_rejects_accept_while_mandatory_condition_is_open() -> None:
    proposal = valid_proposal().model_copy(
        update={
            "recommendation": DecisionRecommendation.ACCEPT,
            "conditions": (),
        }
    )

    packet = scenario_packet()
    unsafe_packet = packet.model_copy(
        update={
            "allowed_recommendations": (
                *packet.allowed_recommendations,
                DecisionRecommendation.ACCEPT,
            )
        }
    )

    with pytest.raises(ValueError, match="mandatory condition"):
        validate_decision_proposal(proposal, unsafe_packet)


def test_guard_rejects_attention_evidence_outside_its_reference() -> None:
    proposal = valid_proposal()
    invalid_point = proposal.human_attention_points[0].model_copy(
        update={"evidence_ids": ("EVD-UNKNOWN",)}
    )
    proposal = proposal.model_copy(update={"human_attention_points": (invalid_point,)})

    with pytest.raises(ValueError, match="not authorized"):
        validate_decision_proposal(proposal, scenario_packet())


def test_guard_rejects_attention_point_derived_from_a_finance_fact() -> None:
    packet = _margin_strategy_packet()
    point = AIDecisionAttentionPointDraft(
        code="FOUNDER_MARGIN_REVIEW",
        text="Founder should review this Finance fact.",
        source_reference_ids=("FACT-MARGIN",),
        evidence_ids=("EVD-MARGIN",),
    )
    proposal = _margin_strategy_proposal(packet).model_copy(
        update={"human_attention_points": (point,)}
    )

    with pytest.raises(ValueError, match="required controls"):
        validate_decision_proposal(proposal, packet)


def test_guard_rejects_completed_approval_or_external_action_claim() -> None:
    proposal = valid_proposal().model_copy(
        update={"executive_summary": "Hồ sơ đã được phê duyệt và có thể tiếp tục."}
    )

    with pytest.raises(ValueError, match="claims an approval"):
        validate_decision_proposal(proposal, scenario_packet())


def test_guard_allows_a_pending_human_approval_attention_point() -> None:
    proposal = valid_proposal()
    point = proposal.human_attention_points[0].model_copy(
        update={"text": "Cam kết này cần được Founder phê duyệt trước khi thực hiện."}
    )

    validate_decision_proposal(
        proposal.model_copy(update={"human_attention_points": (point,)}),
        scenario_packet(),
    )


def test_deterministic_fallback_uses_unambiguous_negotiation_policy() -> None:
    result = asyncio.run(
        DeterministicDecisionAnalysisComposer().compose(scenario_packet())
    )

    assert result.source is DecisionAnalysisSource.DETERMINISTIC_FALLBACK
    assert result.proposal.recommendation is (
        DecisionRecommendation.NEGOTIATE_CONDITIONS_TO_ACCEPT
    )
    assert tuple(item.code for item in result.proposal.conditions) == (
        _condition_candidate().code,
    )
    assert result.proposal.selected_option_ids == ()
    assert result.proposal.reasons[0].code == _reason_candidate().code
    assert result.fallback_reason == "OPENAI_NOT_CONFIGURED"
    validate_decision_proposal(result.proposal, scenario_packet())


class InvalidPrimaryComposer:
    async def compose(self, payload: DecisionScenarioPacket) -> object:
        del payload
        raise ValueError("invalid structured or guarded proposal")


class UnexpectedFailureComposer:
    async def compose(self, payload: DecisionScenarioPacket) -> object:
        del payload
        raise RuntimeError("programming defect")


def test_expected_openai_or_guard_failure_uses_safe_fallback() -> None:
    composer = ResilientDecisionAnalysisComposer(
        InvalidPrimaryComposer(),  # type: ignore[arg-type]
        DeterministicDecisionAnalysisComposer(),
    )

    result = asyncio.run(composer.compose(scenario_packet()))

    assert result.proposal.recommendation is (
        DecisionRecommendation.NEGOTIATE_CONDITIONS_TO_ACCEPT
    )
    assert result.fallback_reason == "DECISION_PROPOSAL_INVALID"


def test_deterministic_fallback_does_not_choose_between_ambiguous_strategies() -> None:
    result = asyncio.run(
        DeterministicDecisionAnalysisComposer().compose(_margin_strategy_packet())
    )

    assert result.proposal.recommendation is DecisionRecommendation.NOT_EVALUABLE
    assert result.proposal.selected_negotiation_strategy_ids == ()


def test_unexpected_programming_failure_is_not_swallowed() -> None:
    composer = ResilientDecisionAnalysisComposer(
        UnexpectedFailureComposer(),  # type: ignore[arg-type]
        DeterministicDecisionAnalysisComposer(),
    )

    with pytest.raises(RuntimeError, match="programming defect"):
        asyncio.run(composer.compose(scenario_packet()))


def test_composer_cache_key_is_stable_and_prompt_version_sensitive() -> None:
    client = SimpleNamespace(responses=SimpleNamespace())
    first = _composer(client)
    same = _composer(client)
    changed = _composer(client, prompt_version="decision-analysis-v2")

    assert first.cache_key(scenario_packet()) == same.cache_key(scenario_packet())
    assert first.cache_key(scenario_packet()) != changed.cache_key(scenario_packet())
