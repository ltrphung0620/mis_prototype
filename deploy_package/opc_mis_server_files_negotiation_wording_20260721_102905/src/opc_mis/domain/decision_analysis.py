"""Pure construction and guard logic for AI-assisted Decision analysis.

All calculations and candidate conditions are created deterministically before
OpenAI is invoked.  OpenAI selects a recommendation and a subset of supplied
candidates; this module rejects invented IDs, targets, evidence, option
combinations, and unsafe eligibility claims.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal
from typing import Any

from opc_mis.domain.artifacts import ArtifactEnvelope
from opc_mis.domain.decision_models import (
    MARGIN_BENCHMARK_INPUTS_CONDITION_CODE,
    MARGIN_BENCHMARK_INPUTS_CONDITION_DESCRIPTION,
    MARGIN_BENCHMARK_INPUTS_CONDITION_EXPECTED_RISK_EFFECT,
    MARGIN_BENCHMARK_INPUTS_CONDITION_TITLE,
    MARGIN_BENCHMARK_INPUTS_CONDITION_VERIFICATION_EVIDENCE_TYPES,
    MARGIN_NEGOTIATION_CONDITION_CODE,
    MARGIN_NEGOTIATION_CONDITION_DESCRIPTION,
    MARGIN_NEGOTIATION_CONDITION_EXPECTED_RISK_EFFECT,
    MARGIN_NEGOTIATION_CONDITION_TITLE,
    MARGIN_NEGOTIATION_CONDITION_VERIFICATION_EVIDENCE_TYPES,
    MARGIN_STRATEGY_INPUTS_CONDITION_CODE,
    MARGIN_STRATEGY_INPUTS_CONDITION_DESCRIPTION,
    MARGIN_STRATEGY_INPUTS_CONDITION_EXPECTED_RISK_EFFECT,
    MARGIN_STRATEGY_INPUTS_CONDITION_TITLE,
    MARGIN_STRATEGY_INPUTS_CONDITION_VERIFICATION_EVIDENCE_TYPES,
    AIDecisionAnalysis,
    AIDecisionComposition,
    AIDecisionProposalDraft,
    DecisionCalculation,
    DecisionCalculationCode,
    DecisionCalculationOperand,
    DecisionCard,
    DecisionConditionCandidate,
    DecisionConditionCategory,
    DecisionConditionStatus,
    DecisionConditionTarget,
    DecisionConfidence,
    DecisionControlSnapshot,
    DecisionDocumentReleaseSnapshot,
    DecisionEnforcementPoint,
    DecisionHumanAttentionPoint,
    DecisionLimitationSnapshot,
    DecisionMetricRole,
    DecisionMetricSnapshot,
    DecisionNegotiationStrategyCandidate,
    DecisionNegotiationStrategyType,
    DecisionOptionSnapshot,
    DecisionReason,
    DecisionReasonCandidate,
    DecisionRecommendation,
    DecisionReferenceEvidence,
    DecisionReferenceKind,
    DecisionRiskFindingSnapshot,
    DecisionScenarioPacket,
    DecisionTargetOperator,
    ExactDecisionArtifactRef,
    NegotiationCondition,
    ai_decision_analysis_id,
    decision_card_id,
    decision_conditions_support_negotiation,
    decision_current_margin_metric_is_evaluable,
    decision_negotiation_strategy_founder_instruction,
    decision_negotiation_strategy_title,
    decision_negotiation_strategy_verification_evidence_types,
    decision_packet_input_hash,
    decision_scenario_packet_id,
    decision_target_margin_metric_is_evaluable,
)
from opc_mis.domain.enums import (
    ArtifactType,
    BankingPrecheckResultAuthority,
    CurrencyCode,
    FinalRiskAssessmentStatus,
    FinalRiskControlCode,
    FinanceDataScope,
    FinanceMetric,
    MajorExceptionStatus,
    OperationsDataScope,
)
from opc_mis.domain.final_risk_models import FinalRiskAssessment
from opc_mis.domain.final_risk_policy import build_final_risk_assessment
from opc_mis.domain.internal_decision_package_models import InternalDecisionPackage
from opc_mis.domain.lineage import deterministic_id


class DecisionAnalysisBoundaryError(ValueError):
    """Raised when Decision input or model output crosses a safety boundary."""


_DECISION_OPC_GLOBAL_CONTEXT_METRICS = {
    FinanceMetric.WORST_RESERVE_GAP,
    FinanceMetric.WORST_RESERVE_GAP_MONTH,
    FinanceMetric.NEGATIVE_NET_CASHFLOW_MONTH_COUNT,
}

_NUMERIC_TOKEN = re.compile(r"(?<![\w])[-+]?\d+(?:[.,]\d+)*(?:\s*%)?")
_GROUNDED_NUMBER_WITH_LABEL = re.compile(
    r"(?<![\w])(?P<number>[-+]?\d+(?:[.,]\d+)*)(?:\s+|[-/]\s*)"
    r"(?P<label>[^\W\d_]+)",
    re.UNICODE,
)
_GROUNDED_NUMERIC_LABEL_ALIASES = {
    "province": ("province", "provinces", "tỉnh"),
    "provinces": ("province", "provinces", "tỉnh"),
    "tỉnh": ("province", "provinces", "tỉnh"),
}
_UNMASKED_NUMERIC_UNIT = re.compile(
    r"(?<!\w)(?:vnd|triệu|tỷ|million|billion|percent|percentage|"
    r"phần\s+trăm|%)(?!\w)",
    re.IGNORECASE,
)
_FORBIDDEN_COMPLETION_CLAIMS = (
    "đã phê duyệt",
    "đã được phê duyệt",
    "founder approved",
    "has approved",
    "already approved",
    "đã cho phép",
    "đã được cho phép",
    "has been authorized",
    "đã gửi",
    "đã nộp",
    "has been submitted",
    "bank accepted",
    "bank approved",
    "ngân hàng đã đồng ý",
    "ngân hàng đã chấp thuận",
    "rủi ro đã được loại bỏ",
    "rủi ro đã giảm",
    "risk has been eliminated",
    "risk has been reduced",
)
_OPEN_CONDITION_COMPLETION_CLAIMS = (
    "biên lợi nhuận đã đạt",
    "biên lợi nhuận hiện đã đạt",
    "gross margin has reached",
    "gross margin now meets",
    "target margin has been met",
    "target is achieved",
    "target is met",
    "target achieved",
    "mục tiêu đã đạt",
    "đã đạt mục tiêu",
    "điều kiện đã đạt",
    "điều kiện đã được đáp ứng",
    "condition has been satisfied",
    "condition is satisfied",
)


def _exact_artifact_ref(artifact: ArtifactEnvelope) -> ExactDecisionArtifactRef:
    return ExactDecisionArtifactRef(
        artifact_id=artifact.artifact_id,
        artifact_type=artifact.artifact_type,
        version=artifact.version,
        input_hash=artifact.input_hash,
    )


def _known_evidence(
    package: InternalDecisionPackage,
    final_risk: FinalRiskAssessment,
) -> tuple[str, ...]:
    return tuple(dict.fromkeys((*package.evidence_ids, *final_risk.evidence_ids)))


def _usable_evidence(
    evidence_ids: tuple[str, ...],
    known_evidence_ids: tuple[str, ...],
) -> tuple[str, ...]:
    known = set(known_evidence_ids)
    return tuple(dict.fromkeys(item for item in evidence_ids if item in known))


def _metric_evidence(
    *,
    evidence_id: str,
    source_evidence_ids: tuple[str, ...],
    known_evidence_ids: tuple[str, ...],
) -> tuple[str, ...]:
    return _usable_evidence(
        (evidence_id, *source_evidence_ids),
        known_evidence_ids,
    )


def _source_artifact_ref(
    package: InternalDecisionPackage,
    artifact_id: str,
) -> ExactDecisionArtifactRef:
    matches = tuple(
        item for item in package.source_artifacts if item.artifact_id == artifact_id
    )
    if len(matches) != 1:
        raise DecisionAnalysisBoundaryError(
            f"Internal Decision Package lacks one exact source: {artifact_id}."
        )
    source = matches[0]
    return ExactDecisionArtifactRef(
        artifact_id=source.artifact_id,
        artifact_type=source.artifact_type,
        version=source.version,
        input_hash=source.input_hash,
    )


def _add_reference(
    references: dict[str, DecisionReferenceEvidence],
    *,
    reference_id: str,
    kind: DecisionReferenceKind,
    evidence_ids: tuple[str, ...],
) -> None:
    if not evidence_ids:
        return
    value = DecisionReferenceEvidence(
        reference_id=reference_id,
        kind=kind,
        evidence_ids=evidence_ids,
    )
    existing = references.setdefault(reference_id, value)
    if existing != value:
        raise DecisionAnalysisBoundaryError(
            f"Decision reference {reference_id} has conflicting lineage."
        )


def _reason_candidate(
    *,
    code: str,
    title: str,
    detail: str,
    source_reference_ids: tuple[str, ...],
    evidence_ids: tuple[str, ...],
) -> DecisionReasonCandidate:
    candidate_id = deterministic_id(
        "DRC", code, title, detail, source_reference_ids, evidence_ids
    )
    return DecisionReasonCandidate(
        candidate_id=candidate_id,
        code=code,
        title=title,
        detail=detail,
        source_reference_ids=source_reference_ids,
        evidence_ids=evidence_ids,
    )


def _condition_candidate(
    *,
    code: str,
    category: DecisionConditionCategory,
    title: str,
    description: str,
    status: DecisionConditionStatus,
    enforcement_point: DecisionEnforcementPoint,
    target: DecisionConditionTarget | None,
    verification_evidence_types: tuple[str, ...],
    expected_risk_effect: str,
    source_reference_ids: tuple[str, ...],
    evidence_ids: tuple[str, ...],
) -> DecisionConditionCandidate:
    candidate_id = deterministic_id(
        "DCC",
        code,
        category,
        title,
        description,
        status,
        enforcement_point,
        target.model_dump(mode="json") if target else None,
        verification_evidence_types,
        expected_risk_effect,
        source_reference_ids,
        evidence_ids,
    )
    return DecisionConditionCandidate(
        candidate_id=candidate_id,
        code=code,
        category=category,
        title=title,
        description=description,
        status=status,
        enforcement_point=enforcement_point,
        target=target,
        verification_evidence_types=verification_evidence_types,
        expected_risk_effect=expected_risk_effect,
        source_reference_ids=source_reference_ids,
        evidence_ids=evidence_ids,
    )


def _negotiation_strategy_candidate(
    *,
    condition_code: str,
    strategy_type: DecisionNegotiationStrategyType,
    title: str,
    founder_instruction: str,
    assumptions: tuple[str, ...],
    baseline_revenue: int,
    baseline_cost: int,
    target_margin: float,
    required_adjustment_value: int,
    resulting_revenue: int,
    resulting_cost: int,
    calculation_id: str,
    verification_evidence_types: tuple[str, ...],
    source_reference_ids: tuple[str, ...],
    evidence_ids: tuple[str, ...],
) -> DecisionNegotiationStrategyCandidate:
    values: dict[str, Any] = {
        "condition_code": condition_code,
        "strategy_type": strategy_type,
        "title": title,
        "founder_instruction": founder_instruction,
        "assumptions": assumptions,
        "baseline_revenue": baseline_revenue,
        "baseline_cost": baseline_cost,
        "target_margin": target_margin,
        "required_adjustment_value": required_adjustment_value,
        "resulting_revenue": resulting_revenue,
        "resulting_cost": resulting_cost,
        "currency": CurrencyCode.VND,
        "calculation_id": calculation_id,
        "verification_evidence_types": verification_evidence_types,
        "source_reference_ids": source_reference_ids,
        "evidence_ids": evidence_ids,
    }
    return DecisionNegotiationStrategyCandidate(
        strategy_id=deterministic_id(
            "DNSTRAT",
            condition_code,
            strategy_type,
            title,
            founder_instruction,
            assumptions,
            baseline_revenue,
            baseline_cost,
            target_margin,
            required_adjustment_value,
            resulting_revenue,
            resulting_cost,
            CurrencyCode.VND,
            calculation_id,
            verification_evidence_types,
            source_reference_ids,
            evidence_ids,
        ),
        **values,
    )


def _business_display(value: int | float, unit: str) -> str:
    number = Decimal(str(value))
    if unit == "VND":
        return f"{int(number):,} VND"
    if unit == "RATIO":
        percentage = number * Decimal("100")
        text = format(percentage.normalize(), "f")
        return f"{text}%"
    text = format(number.normalize(), "f")
    return f"{text} {unit.lower()}"


def _allowed_numeric_displays(
    *,
    metrics: tuple[DecisionMetricSnapshot, ...],
    options: tuple[DecisionOptionSnapshot, ...],
    calculations: tuple[DecisionCalculation, ...],
    negotiation_strategies: tuple[DecisionNegotiationStrategyCandidate, ...],
) -> tuple[str, ...]:
    displays: list[str] = []
    for metric in metrics:
        if isinstance(metric.value, bool) or not isinstance(metric.value, (int, float)):
            continue
        displays.append(_business_display(metric.value, metric.unit))
    for option in options:
        for value in (option.requested_amount, option.supported_amount):
            if value is not None:
                displays.append(_business_display(value, option.currency.value))
        for value in (
            option.annual_rate_or_fee,
            option.processing_fee_rate,
            option.collateral_ratio,
        ):
            if value is not None:
                displays.append(_business_display(value, "RATIO"))
        if option.minimum_amount is not None:
            displays.append(_business_display(option.minimum_amount, "VND"))
    for calculation in calculations:
        displays.append(
            _business_display(calculation.result_value, calculation.result_unit)
        )
    for strategy in negotiation_strategies:
        for value in (
            strategy.baseline_revenue,
            strategy.baseline_cost,
            strategy.required_adjustment_value,
            strategy.resulting_revenue,
            strategy.resulting_cost,
        ):
            displays.append(_business_display(value, strategy.currency.value))
        displays.append(_business_display(strategy.target_margin, "RATIO"))
    return tuple(dict.fromkeys(displays))


def _build_finance_metrics(
    package: InternalDecisionPackage,
    known_evidence_ids: tuple[str, ...],
    references: dict[str, DecisionReferenceEvidence],
) -> tuple[tuple[DecisionMetricSnapshot, ...], int]:
    metrics: list[DecisionMetricSnapshot] = []
    excluded_global = 0
    for fact in package.finance_facts.facts:
        role: DecisionMetricRole | None = None
        attributable = False
        if fact.scope is FinanceDataScope.CASE_SPECIFIC:
            role = DecisionMetricRole.CASE_FACT
            attributable = True
        elif fact.metric is FinanceMetric.OPC_TARGET_GROSS_MARGIN:
            role = DecisionMetricRole.POLICY_TARGET
        elif fact.scope is FinanceDataScope.OPC_GLOBAL:
            if fact.metric in _DECISION_OPC_GLOBAL_CONTEXT_METRICS:
                role = DecisionMetricRole.OPC_GLOBAL_CONTEXT
            else:
                excluded_global += 1
        if role is None:
            continue
        evidence_ids = _metric_evidence(
            evidence_id=fact.evidence_id,
            source_evidence_ids=fact.source_evidence_ids,
            known_evidence_ids=known_evidence_ids,
        )
        if not evidence_ids:
            continue
        metric = DecisionMetricSnapshot(
            fact_id=fact.fact_id,
            metric=fact.metric.value,
            value=fact.value,
            unit=fact.unit.value,
            calculation=fact.calculation.value,
            quality=fact.quality.value,
            evidence_ids=evidence_ids,
            role=role,
            contract_attributable=attributable,
        )
        metrics.append(metric)
        _add_reference(
            references,
            reference_id=fact.fact_id,
            kind=DecisionReferenceKind.FINANCE_FACT,
            evidence_ids=evidence_ids,
        )
    return tuple(metrics), excluded_global


def _build_operations_metrics(
    package: InternalDecisionPackage,
    known_evidence_ids: tuple[str, ...],
    references: dict[str, DecisionReferenceEvidence],
) -> tuple[tuple[DecisionMetricSnapshot, ...], int]:
    metrics: list[DecisionMetricSnapshot] = []
    excluded_global = 0
    for fact in package.operations_facts.facts:
        if fact.scope is OperationsDataScope.OPC_GLOBAL:
            excluded_global += 1
            continue
        if fact.scope is not OperationsDataScope.CASE_SPECIFIC:
            continue
        evidence_ids = _metric_evidence(
            evidence_id=fact.evidence_id,
            source_evidence_ids=fact.source_evidence_ids,
            known_evidence_ids=known_evidence_ids,
        )
        if not evidence_ids:
            continue
        metric = DecisionMetricSnapshot(
            fact_id=fact.fact_id,
            metric=fact.metric.value,
            value=fact.value,
            unit=fact.unit.value,
            calculation=fact.calculation.value,
            quality=fact.quality.value,
            evidence_ids=evidence_ids,
            role=DecisionMetricRole.CASE_FACT,
            contract_attributable=True,
        )
        metrics.append(metric)
        _add_reference(
            references,
            reference_id=fact.fact_id,
            kind=DecisionReferenceKind.OPERATIONS_FACT,
            evidence_ids=evidence_ids,
        )
    return tuple(metrics), excluded_global


def _build_banking_options(
    package: InternalDecisionPackage,
    known_evidence_ids: tuple[str, ...],
    references: dict[str, DecisionReferenceEvidence],
) -> tuple[tuple[DecisionOptionSnapshot, ...], tuple[DecisionCalculation, ...]]:
    matrix = package.banking_option_matrix
    if matrix is None:
        return (), ()
    matrix_evidence = _usable_evidence(matrix.evidence_ids, known_evidence_ids)
    _add_reference(
        references,
        reference_id=matrix.matrix_id,
        kind=DecisionReferenceKind.BANKING_RESULT,
        evidence_ids=matrix_evidence,
    )
    result_by_option = {
        item.option_id: item
        for item in (
            package.banking_precheck_result_set.results
            if package.banking_precheck_result_set is not None
            else ()
        )
    }
    calculations: list[DecisionCalculation] = []
    options: list[DecisionOptionSnapshot] = []
    for candidate in matrix.candidates:
        option_evidence = _usable_evidence(candidate.evidence_ids, known_evidence_ids)
        if not option_evidence:
            continue
        calculation_ids: tuple[str, ...] = ()
        if matrix.requested_amount is not None and candidate.collateral_ratio is not None:
            operands = (
                DecisionCalculationOperand(
                    source_reference_id=matrix.matrix_id,
                    label="requested_amount",
                    value=matrix.requested_amount,
                    unit=matrix.requested_amount_currency.value,
                    evidence_ids=matrix_evidence,
                ),
                DecisionCalculationOperand(
                    source_reference_id=candidate.option_id,
                    label="collateral_ratio",
                    value=candidate.collateral_ratio,
                    unit="RATIO",
                    evidence_ids=option_evidence,
                ),
            )
            decimal_result = Decimal(matrix.requested_amount) * Decimal(
                str(candidate.collateral_ratio)
            )
            result: int | float = (
                int(decimal_result)
                if decimal_result == decimal_result.to_integral_value()
                else float(decimal_result)
            )
            calculation_id = deterministic_id(
                "DCALC",
                DecisionCalculationCode.MULTIPLY,
                "requested_amount * collateral_ratio",
                tuple(item.model_dump(mode="json") for item in operands),
                result,
                CurrencyCode.VND.value,
            )
            calculation = DecisionCalculation(
                calculation_id=calculation_id,
                code=DecisionCalculationCode.MULTIPLY,
                formula="requested_amount * collateral_ratio",
                operands=operands,
                result_value=result,
                result_unit=CurrencyCode.VND.value,
                evidence_ids=tuple(
                    dict.fromkeys(
                        evidence_id
                        for operand in operands
                        for evidence_id in operand.evidence_ids
                    )
                ),
            )
            calculations.append(calculation)
            calculation_ids = (calculation.calculation_id,)
        result = result_by_option.get(candidate.option_id)
        result_evidence = (
            _usable_evidence(result.evidence_ids, known_evidence_ids)
            if result is not None
            else ()
        )
        if result is not None:
            _add_reference(
                references,
                reference_id=result.normalized_result_id,
                kind=DecisionReferenceKind.BANKING_RESULT,
                evidence_ids=result_evidence,
            )
        combined_evidence = tuple(
            dict.fromkeys((*option_evidence, *result_evidence))
        )
        _add_reference(
            references,
            reference_id=candidate.option_id,
            kind=DecisionReferenceKind.BANKING_OPTION,
            evidence_ids=combined_evidence,
        )
        options.append(
            DecisionOptionSnapshot(
                option_id=candidate.option_id,
                bank_product_id=candidate.bank_product_id,
                provider=candidate.provider,
                product_name=candidate.product_name,
                requested_amount=matrix.requested_amount,
                supported_amount=result.supported_amount if result else None,
                currency=matrix.requested_amount_currency,
                annual_rate_or_fee=candidate.annual_rate_or_fee,
                processing_fee_rate=candidate.processing_fee_rate,
                collateral_ratio=candidate.collateral_ratio,
                minimum_amount=candidate.minimum_amount,
                precheck_outcome=result.outcome.value if result else None,
                precheck_authority=result.authority.value if result else None,
                non_binding=(
                    result is None
                    or result.authority
                    is BankingPrecheckResultAuthority.SIMULATED_NON_BINDING
                ),
                calculation_ids=calculation_ids,
                evidence_ids=combined_evidence,
            )
        )
    return tuple(options), tuple(calculations)


def _build_document_snapshot(
    package: InternalDecisionPackage,
    known_evidence_ids: tuple[str, ...],
    references: dict[str, DecisionReferenceEvidence],
) -> DecisionDocumentReleaseSnapshot | None:
    release = package.document_release_package
    artifact_id = package.document_release_package_artifact_id
    if release is None or artifact_id is None:
        return None
    evidence_ids = _usable_evidence(release.evidence_ids, known_evidence_ids)
    if not evidence_ids:
        raise DecisionAnalysisBoundaryError(
            "Document Release Package has no usable evidence lineage."
        )
    _add_reference(
        references,
        reference_id=release.release_package_id,
        kind=DecisionReferenceKind.DOCUMENT_RELEASE_PACKAGE,
        evidence_ids=evidence_ids,
    )
    return DecisionDocumentReleaseSnapshot(
        artifact=_source_artifact_ref(package, artifact_id),
        release_package_id=release.release_package_id,
        recipient=release.recipient,
        purpose=release.purpose,
        document_codes=tuple(item.value for item in release.document_codes),
        masking_manifest_id=release.masking_manifest_id,
        limitation_codes=release.limitation_codes,
        evidence_ids=evidence_ids,
    )


def _build_risk_snapshots(
    final_risk: FinalRiskAssessment,
    known_evidence_ids: tuple[str, ...],
    references: dict[str, DecisionReferenceEvidence],
) -> tuple[
    tuple[DecisionRiskFindingSnapshot, ...],
    tuple[DecisionControlSnapshot, ...],
    tuple[DecisionLimitationSnapshot, ...],
]:
    findings: list[DecisionRiskFindingSnapshot] = []
    controls: list[DecisionControlSnapshot] = []
    limitations: list[DecisionLimitationSnapshot] = []
    for finding in final_risk.residual_findings:
        evidence_ids = _usable_evidence(finding.evidence_ids, known_evidence_ids)
        if not evidence_ids:
            continue
        findings.append(
            DecisionRiskFindingSnapshot(
                finding_id=finding.residual_finding_id,
                code=finding.code,
                title=finding.title,
                detail=finding.detail,
                severity=finding.severity.value,
                status=finding.status.value,
                evidence_ids=evidence_ids,
            )
        )
        _add_reference(
            references,
            reference_id=finding.residual_finding_id,
            kind=DecisionReferenceKind.RESIDUAL_RISK_FINDING,
            evidence_ids=evidence_ids,
        )
    for control in final_risk.required_controls:
        evidence_ids = _usable_evidence(control.evidence_ids, known_evidence_ids)
        controls.append(
            DecisionControlSnapshot(
                control_id=control.control_id,
                code=control.code.value,
                description=control.description,
                protected_action=(
                    control.protected_action.value
                    if control.protected_action is not None
                    else None
                ),
                source_reference_ids=control.source_reference_ids,
                evidence_ids=evidence_ids,
            )
        )
        _add_reference(
            references,
            reference_id=control.control_id,
            kind=DecisionReferenceKind.REQUIRED_CONTROL,
            evidence_ids=evidence_ids,
        )
    for limitation in final_risk.limitations:
        evidence_ids = _usable_evidence(limitation.evidence_ids, known_evidence_ids)
        limitations.append(
            DecisionLimitationSnapshot(
                limitation_id=limitation.limitation_id,
                code=limitation.code,
                detail=limitation.detail,
                evidence_ids=evidence_ids,
            )
        )
        _add_reference(
            references,
            reference_id=limitation.limitation_id,
            kind=DecisionReferenceKind.RISK_LIMITATION,
            evidence_ids=evidence_ids,
        )
    return tuple(findings), tuple(controls), tuple(limitations)


def _observation_reasons(
    package: InternalDecisionPackage,
    known_evidence_ids: tuple[str, ...],
    references: dict[str, DecisionReferenceEvidence],
) -> tuple[DecisionReasonCandidate, ...]:
    reasons: list[DecisionReasonCandidate] = []
    groups: tuple[tuple[Any, DecisionReferenceKind, str], ...] = (
        (
            package.finance_assessment.observations,
            DecisionReferenceKind.FINANCE_OBSERVATION,
            "FINANCE_OBSERVATION",
        ),
        (
            package.finance_assessment.limitations,
            DecisionReferenceKind.FINANCE_LIMITATION,
            "FINANCE_LIMITATION",
        ),
        (
            package.operations_assessment.observations,
            DecisionReferenceKind.OPERATIONS_OBSERVATION,
            "OPERATIONS_OBSERVATION",
        ),
        (
            package.operations_assessment.limitations,
            DecisionReferenceKind.OPERATIONS_LIMITATION,
            "OPERATIONS_LIMITATION",
        ),
    )
    for values, kind, prefix in groups:
        for item in values:
            reference_id = getattr(
                item,
                "observation_id",
                getattr(item, "limitation_id", ""),
            )
            evidence_ids = _usable_evidence(item.evidence_ids, known_evidence_ids)
            if not reference_id or not evidence_ids:
                continue
            _add_reference(
                references,
                reference_id=reference_id,
                kind=kind,
                evidence_ids=evidence_ids,
            )
            title = getattr(item, "title", item.code)
            detail = item.detail
            reasons.append(
                _reason_candidate(
                    code=f"{prefix}_{item.code}_{reference_id}",
                    title=str(title),
                    detail=detail,
                    source_reference_ids=(reference_id,),
                    evidence_ids=evidence_ids,
                )
            )
    return tuple(reasons)


def _margin_negotiation_strategies(
    *,
    revenue: DecisionMetricSnapshot | None,
    cost: DecisionMetricSnapshot | None,
    target_margin: DecisionMetricSnapshot | None,
) -> tuple[
    tuple[DecisionNegotiationStrategyCandidate, ...],
    tuple[DecisionCalculation, ...],
]:
    """Precompute conservative VND alternatives for one margin condition."""

    if revenue is None or cost is None or target_margin is None:
        return (), ()
    if (
        revenue.unit != CurrencyCode.VND.value
        or cost.unit != CurrencyCode.VND.value
        or target_margin.unit != "RATIO"
        or isinstance(revenue.value, bool)
        or not isinstance(revenue.value, (int, float))
        or isinstance(cost.value, bool)
        or not isinstance(cost.value, (int, float))
        or isinstance(target_margin.value, bool)
        or not isinstance(target_margin.value, (int, float))
    ):
        return (), ()
    revenue_value = Decimal(str(revenue.value))
    cost_value = Decimal(str(cost.value))
    target_value = Decimal(str(target_margin.value))
    if (
        revenue_value <= 0
        or cost_value < 0
        or target_value <= 0
        or target_value >= 1
        or revenue_value != revenue_value.to_integral_value()
        or cost_value != cost_value.to_integral_value()
    ):
        return (), ()

    baseline_revenue = int(revenue_value)
    baseline_cost = int(cost_value)
    target_float = float(target_value)
    source_reference_ids = (revenue.fact_id, cost.fact_id, target_margin.fact_id)
    evidence_ids = tuple(
        dict.fromkeys(
            (*revenue.evidence_ids, *cost.evidence_ids, *target_margin.evidence_ids)
        )
    )
    operands = (
        DecisionCalculationOperand(
            source_reference_id=revenue.fact_id,
            label="explicit_order_revenue",
            value=baseline_revenue,
            unit=CurrencyCode.VND.value,
            evidence_ids=revenue.evidence_ids,
        ),
        DecisionCalculationOperand(
            source_reference_id=cost.fact_id,
            label="explicit_order_estimated_cost",
            value=baseline_cost,
            unit=CurrencyCode.VND.value,
            evidence_ids=cost.evidence_ids,
        ),
        DecisionCalculationOperand(
            source_reference_id=target_margin.fact_id,
            label="opc_target_gross_margin",
            value=target_float,
            unit="RATIO",
            evidence_ids=target_margin.evidence_ids,
        ),
    )

    def calculation(
        *,
        code: DecisionCalculationCode,
        formula: str,
        result: int,
    ) -> DecisionCalculation:
        calculation_id = deterministic_id(
            "DCALC",
            code,
            formula,
            tuple(item.model_dump(mode="json") for item in operands),
            result,
            CurrencyCode.VND.value,
        )
        return DecisionCalculation(
            calculation_id=calculation_id,
            code=code,
            formula=formula,
            operands=operands,
            result_value=result,
            result_unit=CurrencyCode.VND.value,
            evidence_ids=evidence_ids,
        )

    target_revenue = int(
        (cost_value / (Decimal("1") - target_value)).to_integral_value(
            rounding=ROUND_CEILING
        )
    )
    revenue_increase = target_revenue - baseline_revenue
    maximum_cost = int(
        (revenue_value * (Decimal("1") - target_value)).to_integral_value(
            rounding=ROUND_FLOOR
        )
    )
    cost_reduction = baseline_cost - maximum_cost
    if revenue_increase <= 0 or cost_reduction <= 0:
        return (), ()

    revenue_calculation = calculation(
        code=(
            DecisionCalculationCode.MINIMUM_REVENUE_INCREASE_FOR_TARGET_MARGIN
        ),
        formula=(
            "ceil(explicit_order_estimated_cost / "
            "(1 - opc_target_gross_margin)) - explicit_order_revenue"
        ),
        result=revenue_increase,
    )
    cost_calculation = calculation(
        code=DecisionCalculationCode.MINIMUM_COST_REDUCTION_FOR_TARGET_MARGIN,
        formula=(
            "explicit_order_estimated_cost - floor(explicit_order_revenue * "
            "(1 - opc_target_gross_margin))"
        ),
        result=cost_reduction,
    )
    condition_code = MARGIN_NEGOTIATION_CONDITION_CODE
    strategies = (
        _negotiation_strategy_candidate(
            condition_code=condition_code,
            strategy_type=DecisionNegotiationStrategyType.INCREASE_CUSTOMER_PRICE,
            title=decision_negotiation_strategy_title(
                DecisionNegotiationStrategyType.INCREASE_CUSTOMER_PRICE
            ),
            founder_instruction=decision_negotiation_strategy_founder_instruction(
                strategy_type=(
                    DecisionNegotiationStrategyType.INCREASE_CUSTOMER_PRICE
                ),
                baseline_revenue=baseline_revenue,
                baseline_cost=baseline_cost,
                required_adjustment_value=revenue_increase,
                resulting_revenue=target_revenue,
                resulting_cost=baseline_cost,
            ),
            assumptions=(
                "EXPLICITLY_LINKED_ORDER_SCOPE_ONLY",
                "ESTIMATED_COST_UNCHANGED",
            ),
            baseline_revenue=baseline_revenue,
            baseline_cost=baseline_cost,
            target_margin=target_float,
            required_adjustment_value=revenue_increase,
            resulting_revenue=target_revenue,
            resulting_cost=baseline_cost,
            calculation_id=revenue_calculation.calculation_id,
            verification_evidence_types=(
                decision_negotiation_strategy_verification_evidence_types(
                    DecisionNegotiationStrategyType.INCREASE_CUSTOMER_PRICE
                )
            ),
            source_reference_ids=source_reference_ids,
            evidence_ids=evidence_ids,
        ),
        _negotiation_strategy_candidate(
            condition_code=condition_code,
            strategy_type=(
                DecisionNegotiationStrategyType.REDUCE_EVIDENCED_COST_AT_FIXED_REVENUE
            ),
            title=decision_negotiation_strategy_title(
                DecisionNegotiationStrategyType.REDUCE_EVIDENCED_COST_AT_FIXED_REVENUE
            ),
            founder_instruction=decision_negotiation_strategy_founder_instruction(
                strategy_type=(
                    DecisionNegotiationStrategyType.REDUCE_EVIDENCED_COST_AT_FIXED_REVENUE
                ),
                baseline_revenue=baseline_revenue,
                baseline_cost=baseline_cost,
                required_adjustment_value=cost_reduction,
                resulting_revenue=baseline_revenue,
                resulting_cost=maximum_cost,
            ),
            assumptions=(
                "EXPLICITLY_LINKED_ORDER_SCOPE_ONLY",
                "ORDER_REVENUE_UNCHANGED",
            ),
            baseline_revenue=baseline_revenue,
            baseline_cost=baseline_cost,
            target_margin=target_float,
            required_adjustment_value=cost_reduction,
            resulting_revenue=baseline_revenue,
            resulting_cost=maximum_cost,
            calculation_id=cost_calculation.calculation_id,
            verification_evidence_types=(
                decision_negotiation_strategy_verification_evidence_types(
                    DecisionNegotiationStrategyType.REDUCE_EVIDENCED_COST_AT_FIXED_REVENUE
                )
            ),
            source_reference_ids=source_reference_ids,
            evidence_ids=evidence_ids,
        ),
    )
    return strategies, (revenue_calculation, cost_calculation)


def _metric_candidates(
    finance_metrics: tuple[DecisionMetricSnapshot, ...],
    *,
    fallback_reference_id: str | None = None,
    fallback_evidence_ids: tuple[str, ...] = (),
) -> tuple[
    tuple[DecisionReasonCandidate, ...],
    tuple[DecisionConditionCandidate, ...],
    tuple[DecisionNegotiationStrategyCandidate, ...],
    tuple[DecisionCalculation, ...],
]:
    by_metric = {item.metric: item for item in finance_metrics}
    reasons: list[DecisionReasonCandidate] = []
    conditions: list[DecisionConditionCandidate] = []
    current_margin = by_metric.get(FinanceMetric.ORDER_GROSS_MARGIN.value)
    target_margin = by_metric.get(FinanceMetric.OPC_TARGET_GROSS_MARGIN.value)
    negotiation_strategies: tuple[DecisionNegotiationStrategyCandidate, ...] = ()
    negotiation_calculations: tuple[DecisionCalculation, ...] = ()
    current_margin_ready = decision_current_margin_metric_is_evaluable(
        current_margin
    )
    target_margin_ready = decision_target_margin_metric_is_evaluable(
        target_margin
    )
    if not current_margin_ready or not target_margin_ready:
        available_metrics = tuple(
            item
            for item in (current_margin, target_margin)
            if item is not None
        )
        source_ids = tuple(item.fact_id for item in available_metrics)
        evidence_ids = tuple(
            dict.fromkeys(
                evidence_id
                for item in available_metrics
                for evidence_id in item.evidence_ids
            )
        )
        if not source_ids and fallback_reference_id and fallback_evidence_ids:
            source_ids = (fallback_reference_id,)
            evidence_ids = fallback_evidence_ids
        if source_ids and evidence_ids:
            reasons.append(
                _reason_candidate(
                    code="GROSS_MARGIN_BENCHMARKS_NOT_EVALUABLE",
                    title="Gross-margin policy comparison is not evaluable",
                    detail=MARGIN_BENCHMARK_INPUTS_CONDITION_DESCRIPTION,
                    source_reference_ids=source_ids,
                    evidence_ids=evidence_ids,
                )
            )
            conditions.append(
                _condition_candidate(
                    code=MARGIN_BENCHMARK_INPUTS_CONDITION_CODE,
                    category=DecisionConditionCategory.EVIDENCE,
                    title=MARGIN_BENCHMARK_INPUTS_CONDITION_TITLE,
                    description=MARGIN_BENCHMARK_INPUTS_CONDITION_DESCRIPTION,
                    status=DecisionConditionStatus.NOT_EVALUABLE,
                    enforcement_point=DecisionEnforcementPoint.BEFORE_ACCEPTANCE,
                    target=None,
                    verification_evidence_types=(
                        MARGIN_BENCHMARK_INPUTS_CONDITION_VERIFICATION_EVIDENCE_TYPES
                    ),
                    expected_risk_effect=(
                        MARGIN_BENCHMARK_INPUTS_CONDITION_EXPECTED_RISK_EFFECT
                    ),
                    source_reference_ids=source_ids,
                    evidence_ids=evidence_ids,
                )
            )
    if (
        current_margin_ready
        and target_margin_ready
        and current_margin is not None
        and target_margin is not None
        and current_margin.value < target_margin.value
    ):
        source_ids = (current_margin.fact_id, target_margin.fact_id)
        evidence_ids = tuple(
            dict.fromkeys((*current_margin.evidence_ids, *target_margin.evidence_ids))
        )
        reasons.append(
            _reason_candidate(
                code="GROSS_MARGIN_BELOW_OPC_TARGET",
                title="Contract-attributable gross margin is below OPC target",
                detail=(
                    "The verified order gross-margin fact is below the explicit OPC "
                    "target supplied as a policy benchmark."
                ),
                source_reference_ids=source_ids,
                evidence_ids=evidence_ids,
            )
        )
        target = DecisionConditionTarget(
            metric=FinanceMetric.ORDER_GROSS_MARGIN.value,
            operator=DecisionTargetOperator.GREATER_THAN_OR_EQUAL,
            current_value=current_margin.value,
            target_value=target_margin.value,
            unit=current_margin.unit,
            source_reference_ids=source_ids,
            evidence_ids=evidence_ids,
        )
        negotiation_strategies, negotiation_calculations = (
            _margin_negotiation_strategies(
                revenue=by_metric.get(FinanceMetric.ORDER_REVENUE_TOTAL.value),
                cost=by_metric.get(
                    FinanceMetric.ORDER_ESTIMATED_COST_TOTAL.value
                ),
                target_margin=target_margin,
            )
        )
        strategy_inputs_ready = bool(negotiation_strategies)
        conditions.append(
            _condition_candidate(
                code=(
                    MARGIN_NEGOTIATION_CONDITION_CODE
                    if strategy_inputs_ready
                    else MARGIN_STRATEGY_INPUTS_CONDITION_CODE
                ),
                category=(
                    DecisionConditionCategory.COMMERCIAL
                    if strategy_inputs_ready
                    else DecisionConditionCategory.EVIDENCE
                ),
                title=(
                    MARGIN_NEGOTIATION_CONDITION_TITLE
                    if strategy_inputs_ready
                    else MARGIN_STRATEGY_INPUTS_CONDITION_TITLE
                ),
                description=(
                    MARGIN_NEGOTIATION_CONDITION_DESCRIPTION
                    if strategy_inputs_ready
                    else MARGIN_STRATEGY_INPUTS_CONDITION_DESCRIPTION
                ),
                status=(
                    DecisionConditionStatus.OPEN
                    if strategy_inputs_ready
                    else DecisionConditionStatus.NOT_EVALUABLE
                ),
                enforcement_point=DecisionEnforcementPoint.BEFORE_ACCEPTANCE,
                target=target,
                verification_evidence_types=(
                    MARGIN_NEGOTIATION_CONDITION_VERIFICATION_EVIDENCE_TYPES
                    if strategy_inputs_ready
                    else MARGIN_STRATEGY_INPUTS_CONDITION_VERIFICATION_EVIDENCE_TYPES
                ),
                expected_risk_effect=(
                    MARGIN_NEGOTIATION_CONDITION_EXPECTED_RISK_EFFECT
                    if strategy_inputs_ready
                    else MARGIN_STRATEGY_INPUTS_CONDITION_EXPECTED_RISK_EFFECT
                ),
                source_reference_ids=source_ids,
                evidence_ids=evidence_ids,
            )
        )
    uncovered = by_metric.get(FinanceMetric.UNCOVERED_CONTRACT_VALUE.value)
    if (
        uncovered is not None
        and isinstance(uncovered.value, (int, float))
        and not isinstance(uncovered.value, bool)
        and uncovered.value > 0
    ):
        reasons.append(
            _reason_candidate(
                code="CONTRACT_VALUE_NOT_COVERED_BY_EXPLICIT_ORDERS",
                title="Part of the contract value lacks explicit order coverage",
                detail=(
                    "The verified uncovered-contract-value fact must not be treated "
                    "as explained revenue, cost, or delivery scope."
                ),
                source_reference_ids=(uncovered.fact_id,),
                evidence_ids=uncovered.evidence_ids,
            )
        )
        conditions.append(
            _condition_candidate(
                code="RESOLVE_EXPLICIT_ORDER_COVERAGE",
                category=DecisionConditionCategory.COMMERCIAL,
                title="Resolve the uncovered contract value",
                description=(
                    "Provide explicit order, phase, amendment, or scope relationships "
                    "and run Finance and Operations again."
                ),
                status=DecisionConditionStatus.OPEN,
                enforcement_point=DecisionEnforcementPoint.BEFORE_ACCEPTANCE,
                target=None,
                verification_evidence_types=(
                    "EXPLICIT_ORDER_PHASE_OR_AMENDMENT_RELATIONSHIP",
                    "UPDATED_FINANCE_ASSESSMENT",
                    "UPDATED_OPERATIONS_ASSESSMENT",
                ),
                expected_risk_effect=(
                    "Removes the evidence-coverage gap without inventing revenue, cost, "
                    "or delivery scope."
                ),
                source_reference_ids=(uncovered.fact_id,),
                evidence_ids=uncovered.evidence_ids,
            )
        )
    return (
        tuple(reasons),
        tuple(conditions),
        negotiation_strategies,
        negotiation_calculations,
    )


def _banking_condition_candidates(
    options: tuple[DecisionOptionSnapshot, ...],
) -> tuple[DecisionConditionCandidate, ...]:
    """Create exact amount/terms conditions without treating simulation as approval."""

    conditions: list[DecisionConditionCandidate] = []
    for option in options:
        if option.requested_amount is not None:
            conditions.append(
                _condition_candidate(
                    code=f"OBTAIN_BINDING_BANK_CAPACITY_{option.option_id}",
                    category=DecisionConditionCategory.BANKING,
                    title="Obtain binding confirmation of Banking capacity",
                    description=(
                        "Replace the current non-binding candidate or simulated result "
                        "with an authoritative provider response for the exact amount."
                    ),
                    status=DecisionConditionStatus.OPEN,
                    enforcement_point=(
                        DecisionEnforcementPoint.BEFORE_EXTERNAL_COMMITMENT
                    ),
                    target=DecisionConditionTarget(
                        metric="BINDING_SUPPORTED_AMOUNT",
                        operator=DecisionTargetOperator.GREATER_THAN_OR_EQUAL,
                        current_value=None,
                        target_value=option.requested_amount,
                        unit=CurrencyCode.VND.value,
                        currency=CurrencyCode.VND,
                        source_reference_ids=(option.option_id,),
                        evidence_ids=option.evidence_ids,
                    ),
                    verification_evidence_types=(
                        "BINDING_BANK_RESPONSE",
                        "APPROVED_TERM_SHEET",
                    ),
                    expected_risk_effect=(
                        "Provides authoritative evidence for the requested Banking "
                        "capacity; Risk must separately reassess residual risk."
                    ),
                    source_reference_ids=(option.option_id,),
                    evidence_ids=option.evidence_ids,
                )
            )
        if any(
            value is not None
            for value in (
                option.annual_rate_or_fee,
                option.processing_fee_rate,
                option.collateral_ratio,
            )
        ):
            conditions.append(
                _condition_candidate(
                    code=f"CONFIRM_BINDING_BANK_TERMS_{option.option_id}",
                    category=DecisionConditionCategory.BANKING,
                    title="Confirm binding Banking fees and collateral terms",
                    description=(
                        "Obtain the fee basis, tenor, charges, collateral terms, and "
                        "approval conditions in an authoritative provider response."
                    ),
                    status=DecisionConditionStatus.OPEN,
                    enforcement_point=(
                        DecisionEnforcementPoint.BEFORE_EXTERNAL_COMMITMENT
                    ),
                    target=None,
                    verification_evidence_types=(
                        "BINDING_BANK_RESPONSE",
                        "APPROVED_TERM_SHEET",
                    ),
                    expected_risk_effect=(
                        "Removes uncertainty in Banking terms without assuming that "
                        "a catalog rate or simulated response is binding."
                    ),
                    source_reference_ids=(option.option_id,),
                    evidence_ids=option.evidence_ids,
                )
            )
    return tuple(conditions)


def _cashflow_pressure_detail(
    finance_metrics: tuple[DecisionMetricSnapshot, ...],
) -> str | None:
    by_metric = {item.metric: item for item in finance_metrics}
    worst_gap = by_metric.get(FinanceMetric.WORST_RESERVE_GAP.value)
    worst_month = by_metric.get(FinanceMetric.WORST_RESERVE_GAP_MONTH.value)
    negative_months = by_metric.get(
        FinanceMetric.NEGATIVE_NET_CASHFLOW_MONTH_COUNT.value
    )
    details: list[str] = []
    if (
        worst_gap is not None
        and isinstance(worst_gap.value, (int, float))
        and not isinstance(worst_gap.value, bool)
        and worst_gap.value > 0
        and worst_month is not None
        and isinstance(worst_month.value, str)
        and worst_month.value
    ):
        details.append(
            "Theo dữ liệu dòng tiền cấp OPC, tháng có worst reserve gap là "
            f"{worst_month.value}, với khoảng thiếu hụt "
            f"{_business_display(worst_gap.value, worst_gap.unit)}."
        )
    if (
        negative_months is not None
        and isinstance(negative_months.value, (int, float))
        and not isinstance(negative_months.value, bool)
        and negative_months.value > 0
    ):
        month_count = Decimal(str(negative_months.value)).normalize()
        details.append(
            "Dự báo cũng ghi nhận "
            f"{format(month_count, 'f')} tháng có net cash âm ở cấp OPC."
        )
    if not details:
        return None
    return " ".join(details)


def _founder_risk_limitation_detail(
    limitation: DecisionLimitationSnapshot,
    *,
    cashflow_pressure_detail: str | None,
) -> str:
    normalized = limitation.detail.casefold().replace("_", " ")
    if "closing cash" not in normalized:
        return limitation.detail
    base = (
        "Chưa có closing cash riêng cho hợp đồng, nên Final Risk không tự thay thế "
        "bằng projected_closing_cash hoặc dữ liệu tương đương. "
        "Founder cần xem áp lực dòng tiền theo các tháng đang có bằng chứng trước "
        "khi chấp nhận điều kiện này."
    )
    if cashflow_pressure_detail is None:
        return base
    return f"{base} {cashflow_pressure_detail}"


def _risk_candidates(
    findings: tuple[DecisionRiskFindingSnapshot, ...],
    controls: tuple[DecisionControlSnapshot, ...],
    limitations: tuple[DecisionLimitationSnapshot, ...],
    *,
    has_banking_options: bool,
    finance_metrics: tuple[DecisionMetricSnapshot, ...] = (),
) -> tuple[tuple[DecisionReasonCandidate, ...], tuple[DecisionConditionCandidate, ...]]:
    reasons: list[DecisionReasonCandidate] = []
    conditions: list[DecisionConditionCandidate] = []
    cashflow_pressure = _cashflow_pressure_detail(finance_metrics)
    for finding in findings:
        reasons.append(
            _reason_candidate(
                code=f"OPEN_RESIDUAL_RISK_{finding.code}_{finding.finding_id}",
                title=finding.title,
                detail=finding.detail,
                source_reference_ids=(finding.finding_id,),
                evidence_ids=finding.evidence_ids,
            )
        )
        conditions.append(
            _condition_candidate(
                code=f"ADDRESS_RESIDUAL_RISK_{finding.code}_{finding.finding_id}",
                category=DecisionConditionCategory.EVIDENCE,
                title=f"Address open residual risk: {finding.title}",
                description=(
                    "Provide case-specific mitigation evidence and rerun Final Risk; "
                    "Decision cannot mark the risk as reduced."
                ),
                status=DecisionConditionStatus.OPEN,
                enforcement_point=DecisionEnforcementPoint.BEFORE_ACCEPTANCE,
                target=None,
                verification_evidence_types=("UPDATED_FINAL_RISK_ASSESSMENT",),
                expected_risk_effect=(
                    "Enables Risk to determine whether the finding remains open or is "
                    "mitigated; no reduction is claimed in this Decision analysis."
                ),
                source_reference_ids=(finding.finding_id,),
                evidence_ids=finding.evidence_ids,
            )
        )
    control_policy = {
        FinalRiskControlCode.SIMULATED_BANKING_RESULT_IS_NON_BINDING.value: (
            DecisionConditionCategory.BANKING,
            DecisionEnforcementPoint.BEFORE_EXTERNAL_COMMITMENT,
            ("BINDING_BANK_RESPONSE", "APPROVED_TERM_SHEET"),
        ),
        FinalRiskControlCode.DOCUMENT_RELEASE_REQUIRES_SEPARATE_AUTHORIZATION.value: (
            DecisionConditionCategory.DOCUMENT,
            DecisionEnforcementPoint.BEFORE_DOCUMENT_RELEASE,
            ("EXACT_FOUNDER_AUTHORIZATION",),
        ),
        FinalRiskControlCode.GOVERNANCE_EVALUATION_BEFORE_PROTECTED_ACTION.value: (
            DecisionConditionCategory.GOVERNANCE,
            DecisionEnforcementPoint.BEFORE_EXTERNAL_COMMITMENT,
            ("GOVERNANCE_PERMIT",),
        ),
        FinalRiskControlCode.HUMAN_CONFIRMATION_REQUIRED.value: (
            DecisionConditionCategory.GOVERNANCE,
            DecisionEnforcementPoint.BEFORE_ACCEPTANCE,
            ("FOUNDER_CONFIRMATION",),
        ),
        FinalRiskControlCode.EVIDENCE_LIMITATION_MUST_BE_PRESERVED.value: (
            DecisionConditionCategory.EVIDENCE,
            DecisionEnforcementPoint.BEFORE_ACCEPTANCE,
            ("CASE_SPECIFIC_SOURCE_EVIDENCE", "UPDATED_FINAL_RISK_ASSESSMENT"),
        ),
    }
    for control in controls:
        if not control.evidence_ids or control.code not in control_policy:
            continue
        if (
            has_banking_options
            and control.code
            == FinalRiskControlCode.SIMULATED_BANKING_RESULT_IS_NON_BINDING.value
        ):
            continue
        category, enforcement, verification = control_policy[control.code]
        conditions.append(
            _condition_candidate(
                code=f"PRESERVE_CONTROL_{control.code}_{control.control_id}",
                category=category,
                title=f"Satisfy required control: {control.code}",
                description=control.description,
                status=DecisionConditionStatus.OPEN,
                enforcement_point=enforcement,
                target=None,
                verification_evidence_types=verification,
                expected_risk_effect=(
                    "Prevents the proposal from bypassing the exact Final Risk control; "
                    "Risk remains authoritative for any later risk change."
                ),
                source_reference_ids=(control.control_id,),
                evidence_ids=control.evidence_ids,
            )
        )
    for limitation in limitations:
        if not limitation.evidence_ids:
            continue
        detail = _founder_risk_limitation_detail(
            limitation,
            cashflow_pressure_detail=cashflow_pressure,
        )
        reasons.append(
            _reason_candidate(
                code=(
                    f"FINAL_RISK_LIMITATION_{limitation.code}_{limitation.limitation_id}"
                ),
                title="Final Risk is limited by evidence",
                detail=detail,
                source_reference_ids=(limitation.limitation_id,),
                evidence_ids=limitation.evidence_ids,
            )
        )
        conditions.append(
            _condition_candidate(
                code=(
                    "RESOLVE_FINAL_RISK_LIMITATION_"
                    f"{limitation.code}_{limitation.limitation_id}"
                ),
                category=DecisionConditionCategory.EVIDENCE,
                title="Resolve the Final Risk evidence limitation",
                description=detail,
                status=DecisionConditionStatus.NOT_EVALUABLE,
                enforcement_point=DecisionEnforcementPoint.BEFORE_ACCEPTANCE,
                target=None,
                verification_evidence_types=(
                    "CASE_SPECIFIC_SOURCE_EVIDENCE",
                    "UPDATED_FINAL_RISK_ASSESSMENT",
                ),
                expected_risk_effect=(
                    "Allows Final Risk to replace an unknown with an evidence-based "
                    "conclusion; no risk reduction is pre-claimed."
                ),
                source_reference_ids=(limitation.limitation_id,),
                evidence_ids=limitation.evidence_ids,
            )
        )
    return tuple(reasons), tuple(conditions)


def build_decision_scenario_packet(
    *,
    package_artifact: ArtifactEnvelope,
    package: InternalDecisionPackage,
    final_risk_artifact: ArtifactEnvelope,
    final_risk: FinalRiskAssessment,
) -> DecisionScenarioPacket:
    """Build the exact deterministic packet consumed by the AI composer."""

    if package_artifact.artifact_type is not ArtifactType.INTERNAL_DECISION_PACKAGE:
        raise DecisionAnalysisBoundaryError("Decision requires Internal Decision Package")
    if final_risk_artifact.artifact_type is not ArtifactType.FINAL_RISK_ASSESSMENT:
        raise DecisionAnalysisBoundaryError("Decision requires Final Risk Assessment")
    expected_identity = (
        package.evaluation_case_id,
        package.dataset_id,
        package.contract_id,
    )
    if (
        final_risk.evaluation_case_id,
        final_risk.dataset_id,
        final_risk.contract_id,
    ) != expected_identity:
        raise DecisionAnalysisBoundaryError(
            "Final Risk and Internal Decision Package belong to different cases."
        )
    if (
        final_risk.internal_decision_package_id != package.package_id
        or final_risk.internal_decision_package_artifact_id
        != package_artifact.artifact_id
        or final_risk.internal_decision_package_artifact_version
        != package_artifact.version
        or final_risk.internal_decision_package_input_hash
        != package_artifact.input_hash
    ):
        raise DecisionAnalysisBoundaryError(
            "Final Risk is not bound to the exact Internal Decision Package."
        )
    canonical_final_risk = build_final_risk_assessment(
        package_artifact=package_artifact,
        package=package,
    )
    if canonical_final_risk != final_risk:
        raise DecisionAnalysisBoundaryError(
            "Final Risk differs from the canonical evidence-based derivation."
        )
    known_evidence_ids = _known_evidence(package, final_risk)
    if not known_evidence_ids:
        raise DecisionAnalysisBoundaryError(
            "Decision cannot run without evidence lineage."
        )

    references: dict[str, DecisionReferenceEvidence] = {}
    _add_reference(
        references,
        reference_id=package.package_id,
        kind=DecisionReferenceKind.INTERNAL_DECISION_PACKAGE,
        evidence_ids=known_evidence_ids,
    )
    _add_reference(
        references,
        reference_id=final_risk.assessment_id,
        kind=DecisionReferenceKind.FINAL_RISK_ASSESSMENT,
        evidence_ids=known_evidence_ids,
    )
    finance_metrics, excluded_finance = _build_finance_metrics(
        package, known_evidence_ids, references
    )
    operations_metrics, excluded_operations = _build_operations_metrics(
        package, known_evidence_ids, references
    )
    options, banking_calculations = _build_banking_options(
        package, known_evidence_ids, references
    )
    findings, controls, limitations = _build_risk_snapshots(
        final_risk, known_evidence_ids, references
    )
    document_snapshot = _build_document_snapshot(
        package, known_evidence_ids, references
    )

    observation_reasons = _observation_reasons(
        package, known_evidence_ids, references
    )
    (
        metric_reasons,
        metric_conditions,
        negotiation_strategies,
        negotiation_calculations,
    ) = _metric_candidates(
        finance_metrics,
        fallback_reference_id=package.package_id,
        fallback_evidence_ids=known_evidence_ids,
    )
    calculations = (*banking_calculations, *negotiation_calculations)
    risk_reasons, risk_conditions = _risk_candidates(
        findings,
        controls,
        limitations,
        has_banking_options=bool(options),
        finance_metrics=finance_metrics,
    )
    banking_conditions = _banking_condition_candidates(options)
    option_reasons = tuple(
        _reason_candidate(
            code=f"BANKING_OPTION_CANDIDATE_AVAILABLE_{item.option_id}",
            title="A configured Banking candidate is available",
            detail=(
                "The candidate is evidence-backed but remains non-binding unless a "
                "later authoritative provider response proves otherwise."
            ),
            source_reference_ids=(item.option_id,),
            evidence_ids=item.evidence_ids,
        )
        for item in options
    )
    reasons_by_id: dict[str, DecisionReasonCandidate] = {}
    for item in (
        *risk_reasons,
        *metric_reasons,
        *observation_reasons,
        *option_reasons,
    ):
        reasons_by_id.setdefault(item.candidate_id, item)
    reasons = tuple(reasons_by_id.values())
    if not reasons:
        reasons = (
            _reason_candidate(
                code="FINAL_RISK_EVIDENCE_PACKET_AVAILABLE",
                title="Final Risk evidence packet is available",
                detail=(
                    "The proposal must remain within the exact Final Risk conclusion "
                    "and its evidence limitations."
                ),
                source_reference_ids=(final_risk.assessment_id,),
                evidence_ids=known_evidence_ids,
            ),
        )
    conditions_by_id: dict[str, DecisionConditionCandidate] = {}
    for item in (*risk_conditions, *metric_conditions, *banking_conditions):
        conditions_by_id.setdefault(item.candidate_id, item)
    conditions = tuple(conditions_by_id.values())
    allowed: list[DecisionRecommendation] = [DecisionRecommendation.NOT_EVALUABLE]
    if final_risk.major_exception_status is MajorExceptionStatus.DETECTED:
        allowed.insert(0, DecisionRecommendation.DO_NOT_ACCEPT)
    if decision_conditions_support_negotiation(conditions):
        allowed.insert(0, DecisionRecommendation.NEGOTIATE_CONDITIONS_TO_ACCEPT)
    if (
        final_risk.assessment_status is FinalRiskAssessmentStatus.COMPLETE
        and final_risk.major_exception_status is MajorExceptionStatus.NOT_DETECTED
        and not findings
        and not conditions
    ):
        allowed.insert(0, DecisionRecommendation.ACCEPT)

    all_metrics = (*finance_metrics, *operations_metrics)
    kwargs: dict[str, Any] = {
        "evaluation_case_id": package.evaluation_case_id,
        "dataset_id": package.dataset_id,
        "contract_id": package.contract_id,
        "internal_decision_package_id": package.package_id,
        "final_risk_assessment_id": final_risk.assessment_id,
        "internal_decision_package_artifact": _exact_artifact_ref(package_artifact),
        "final_risk_artifact": _exact_artifact_ref(final_risk_artifact),
        "assembly_path": package.assembly_path.value,
        "finance_metrics": finance_metrics,
        "operations_metrics": operations_metrics,
        "calculations": calculations,
        "banking_options": options,
        "negotiation_strategy_candidates": negotiation_strategies,
        "allowed_option_combinations": tuple(
            combination
            for combination in (
                package.banking_option_matrix.allowed_option_combinations
                if package.banking_option_matrix is not None
                else ()
            )
            if set(combination).issubset({item.option_id for item in options})
        ),
        "residual_risk_level": final_risk.residual_risk_level,
        "final_risk_status": final_risk.assessment_status,
        "major_exception_status": final_risk.major_exception_status,
        "residual_findings": findings,
        "required_controls": controls,
        "limitations": limitations,
        "document_release_package": document_snapshot,
        "reason_candidates": reasons,
        "condition_candidates": conditions,
        "allowed_recommendations": tuple(allowed),
        "allowed_numeric_display_values": _allowed_numeric_displays(
            metrics=tuple(all_metrics),
            options=options,
            calculations=calculations,
            negotiation_strategies=negotiation_strategies,
        ),
        "reference_evidence": tuple(references.values()),
        "known_evidence_ids": known_evidence_ids,
        "excluded_opc_global_finance_fact_count": excluded_finance,
        "excluded_opc_global_operations_fact_count": excluded_operations,
    }
    unvalidated = DecisionScenarioPacket.model_construct(packet_id="PENDING", **kwargs)
    return DecisionScenarioPacket(
        packet_id=decision_scenario_packet_id(unvalidated),
        **kwargs,
    )


def _candidate_payload(value: Any) -> dict[str, Any]:
    return value.model_dump(mode="json", exclude={"candidate_id"})


def _model_authored_text(
    proposal: AIDecisionProposalDraft,
    *,
    canonical_executive_summary: str | None,
) -> tuple[str, ...]:
    """Return only prose that is not an exact deterministic candidate copy."""

    summary = (
        ()
        if proposal.executive_summary == canonical_executive_summary
        else (proposal.executive_summary,)
    )
    return (
        *summary,
        *(item.action for item in proposal.recommended_actions),
        *(point.text for point in proposal.human_attention_points),
    )


def _iter_identifier_values(value: Any, *, field_name: str = "") -> Iterable[str]:
    if hasattr(value, "model_dump"):
        yield from _iter_identifier_values(value.model_dump(mode="json"))
        return
    if isinstance(value, dict):
        for key, item in value.items():
            yield from _iter_identifier_values(item, field_name=str(key))
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            yield from _iter_identifier_values(item, field_name=field_name)
        return
    if isinstance(value, str) and (
        field_name.endswith("_id")
        or field_name.endswith("_ids")
        or field_name in {"code", "metric", "formula"}
    ):
        yield value


def _selected_numeric_displays(
    *,
    proposal: AIDecisionProposalDraft,
    packet: DecisionScenarioPacket,
) -> tuple[str, ...]:
    """Limit numeric prose to evidence selected by this exact proposal."""

    displays: list[str] = []
    grounded_reason_displays: list[str] = []

    def add(value: int | float | None, unit: str) -> None:
        if value is not None:
            displays.append(_business_display(value, unit))

    selected_reference_ids = {
        reference_id
        for item in (
            *proposal.reasons,
            *proposal.recommended_actions,
            *proposal.conditions,
            *proposal.human_attention_points,
        )
        for reference_id in item.source_reference_ids
    }
    selected_reason_codes = {item.code for item in proposal.reasons}
    for candidate in packet.reason_candidates:
        if candidate.code not in selected_reason_codes:
            continue
        for grounded_text in (candidate.title, candidate.detail):
            for match in _GROUNDED_NUMBER_WITH_LABEL.finditer(grounded_text):
                number = match.group("number")
                source_label = match.group("label").casefold()
                labels = _GROUNDED_NUMERIC_LABEL_ALIASES.get(
                    source_label,
                    (source_label,),
                )
                for label in labels:
                    grounded_reason_displays.extend(
                        (f"{number} {label}", f"{number}-{label}")
                    )
    for metric in (*packet.finance_metrics, *packet.operations_metrics):
        if metric.fact_id in selected_reference_ids and isinstance(
            metric.value, (int, float)
        ) and not isinstance(metric.value, bool):
            add(metric.value, metric.unit)
    for condition in proposal.conditions:
        if condition.target is not None:
            add(condition.target.current_value, condition.target.unit)
            add(condition.target.target_value, condition.target.unit)

    strategies_by_id = {
        item.strategy_id: item for item in packet.negotiation_strategy_candidates
    }
    selected_strategies = tuple(
        strategies_by_id[strategy_id]
        for strategy_id in proposal.selected_negotiation_strategy_ids
        if strategy_id in strategies_by_id
    )
    if selected_strategies:
        # The Founder-facing margin instruction is rendered canonically after the
        # selection. Only numeric tokens copied from an exact selected reason may
        # remain in model-authored actions.
        return tuple(dict.fromkeys(grounded_reason_displays))
    selected_calculation_ids = {
        item.calculation_id for item in selected_strategies
    }
    for strategy in selected_strategies:
        for value in (
            strategy.baseline_revenue,
            strategy.baseline_cost,
            strategy.required_adjustment_value,
            strategy.resulting_revenue,
            strategy.resulting_cost,
        ):
            add(value, strategy.currency.value)
        add(strategy.target_margin, "RATIO")

    options_by_id = {item.option_id: item for item in packet.banking_options}
    for option_id in proposal.selected_option_ids:
        option = options_by_id.get(option_id)
        if option is None:
            continue
        selected_calculation_ids.update(option.calculation_ids)
        for value in (
            option.requested_amount,
            option.supported_amount,
            option.minimum_amount,
        ):
            add(value, option.currency.value)
        for value in (
            option.annual_rate_or_fee,
            option.processing_fee_rate,
            option.collateral_ratio,
        ):
            add(value, "RATIO")
    for calculation in packet.calculations:
        if calculation.calculation_id in selected_calculation_ids:
            add(calculation.result_value, calculation.result_unit)

    packet_allowlist = set(packet.allowed_numeric_display_values)
    grounded_reason_allowlist = set(grounded_reason_displays)
    return tuple(
        value
        for value in dict.fromkeys((*displays, *grounded_reason_displays))
        if value in packet_allowlist or value in grounded_reason_allowlist
    )


def _contains_forbidden_claim(text: str, claim: str) -> bool:
    return claim in text


def validate_decision_proposal_prose(
    *,
    proposal: AIDecisionProposalDraft,
    packet: DecisionScenarioPacket,
) -> None:
    """Reject ungrounded numbers and false completion claims at the domain boundary."""

    strategies_by_id = {
        item.strategy_id: item for item in packet.negotiation_strategy_candidates
    }
    selected_strategies = tuple(
        strategies_by_id[strategy_id]
        for strategy_id in proposal.selected_negotiation_strategy_ids
        if strategy_id in strategies_by_id
    )
    canonical_executive_summary = _strategy_founder_summary(selected_strategies)
    model_authored_text = _model_authored_text(
        proposal,
        canonical_executive_summary=canonical_executive_summary,
    )
    allowed_displays = _selected_numeric_displays(
        proposal=proposal,
        packet=packet,
    )
    masks = tuple(
        sorted(
            set((*allowed_displays, *_iter_identifier_values(packet))),
            key=len,
            reverse=True,
        )
    )
    for text in model_authored_text:
        remaining = text.casefold()
        for allowed in masks:
            remaining = remaining.replace(allowed.casefold(), "")
        if _NUMERIC_TOKEN.search(remaining) or _UNMASKED_NUMERIC_UNIT.search(
            remaining
        ):
            raise DecisionAnalysisBoundaryError(
                "Decision proposal contains numeric prose outside its exact selected "
                "evidence."
            )

    for text in model_authored_text:
        normalized = text.casefold()
        if any(
            _contains_forbidden_claim(normalized, claim)
            for claim in _FORBIDDEN_COMPLETION_CLAIMS
        ):
            raise DecisionAnalysisBoundaryError(
                "Decision proposal claims an approval, external action, or risk "
                "reduction occurred."
            )
    if any(
        condition.status
        in {DecisionConditionStatus.OPEN, DecisionConditionStatus.NOT_EVALUABLE}
        for condition in proposal.conditions
    ):
        for text in model_authored_text:
            normalized = text.casefold()
            if any(
                _contains_forbidden_claim(normalized, claim)
                for claim in _OPEN_CONDITION_COMPLETION_CLAIMS
            ):
                raise DecisionAnalysisBoundaryError(
                    "Decision proposal claims an unresolved condition is already met."
                )


def _strategy_founder_summary(
    strategies: tuple[DecisionNegotiationStrategyCandidate, ...],
) -> str | None:
    """Build authoritative Founder prose from exact AI-selected strategy snapshots."""

    if not strategies:
        return None
    sections: list[str] = []
    for strategy in strategies:
        current_margin = (
            Decimal(strategy.baseline_revenue) - Decimal(strategy.baseline_cost)
        ) / Decimal(strategy.baseline_revenue)
        title = decision_negotiation_strategy_title(strategy.strategy_type)
        founder_instruction = decision_negotiation_strategy_founder_instruction(
            strategy_type=strategy.strategy_type,
            baseline_revenue=strategy.baseline_revenue,
            baseline_cost=strategy.baseline_cost,
            required_adjustment_value=strategy.required_adjustment_value,
            resulting_revenue=strategy.resulting_revenue,
            resulting_cost=strategy.resulting_cost,
        )
        sections.append(
            "Biên lợi nhuận của phạm vi order đã liên kết hiện là "
            f"{_business_display(float(current_margin), 'RATIO')}, thấp hơn mục "
            f"tiêu {_business_display(strategy.target_margin, 'RATIO')}. "
            f"Phương án được đề xuất: {title}. "
            f"{founder_instruction}"
        )
    sections.append(
        "Điều kiện vẫn OPEN cho đến khi có bằng chứng khách hàng đồng ý và Finance "
        "cùng Final Risk đã chạy lại; không áp dụng các số liệu này cho phần giá trị "
        "hợp đồng chưa được explicit order cover."
    )
    sections.append(
        "Nếu Founder chấp nhận hướng này, case sẽ đi tiếp như một phương án chấp "
        "nhận có điều kiện: đội thương mại cần lấy xác nhận của khách hàng theo "
        "phương án đã chọn, sau đó hệ thống chạy lại Finance và Final Risk trước "
        "khi coi điều kiện là đủ cơ sở."
    )
    return " ".join(sections)


def _validate_reference_lineage(
    *,
    source_reference_ids: tuple[str, ...],
    evidence_ids: tuple[str, ...],
    reference_map: dict[str, DecisionReferenceEvidence],
) -> None:
    if not set(source_reference_ids).issubset(reference_map):
        raise DecisionAnalysisBoundaryError(
            "AI Decision output references an unknown deterministic source."
        )
    allowed_evidence = {
        evidence_id
        for reference_id in source_reference_ids
        for evidence_id in reference_map[reference_id].evidence_ids
    }
    if not evidence_ids or not set(evidence_ids).issubset(allowed_evidence):
        raise DecisionAnalysisBoundaryError(
            "AI Decision output has missing or unrelated evidence lineage."
        )


def guard_ai_decision_composition(
    *,
    packet: DecisionScenarioPacket,
    composition: AIDecisionComposition,
) -> AIDecisionAnalysis:
    """Turn an untrusted AI proposal into a canonical, evidence-bound analysis."""

    expected_input_hash = decision_packet_input_hash(packet)
    if composition.input_hash != expected_input_hash:
        raise DecisionAnalysisBoundaryError(
            "AI Decision composition was produced from a different input packet."
        )
    proposal = composition.proposal
    if proposal.recommendation not in packet.allowed_recommendations:
        raise DecisionAnalysisBoundaryError(
            "AI recommendation is not eligible for this deterministic packet."
        )
    if (
        composition.source.value == "DETERMINISTIC_FALLBACK"
        and proposal.recommendation is not DecisionRecommendation.NOT_EVALUABLE
    ):
        raise DecisionAnalysisBoundaryError(
            "Deterministic fallback may only return NOT_EVALUABLE."
        )
    selected_reason_candidates: list[DecisionReasonCandidate] = []
    for draft in proposal.reasons:
        matches = tuple(
            item
            for item in packet.reason_candidates
            if _candidate_payload(item) == draft.model_dump(mode="json")
        )
        if len(matches) != 1:
            raise DecisionAnalysisBoundaryError(
                "AI Decision reason was not selected exactly from supplied candidates."
            )
        selected_reason_candidates.append(matches[0])
    if len({item.candidate_id for item in selected_reason_candidates}) != len(
        selected_reason_candidates
    ):
        raise DecisionAnalysisBoundaryError("AI Decision selected a duplicate reason.")
    actions_by_reason_code = {
        item.reason_code: item for item in proposal.recommended_actions
    }
    selected_reason_codes = {item.code for item in proposal.reasons}
    if len(actions_by_reason_code) != len(proposal.recommended_actions):
        raise DecisionAnalysisBoundaryError(
            "AI Decision supplied duplicate actions for a selected reason."
        )
    if proposal.recommendation is DecisionRecommendation.NOT_EVALUABLE:
        if actions_by_reason_code:
            raise DecisionAnalysisBoundaryError(
                "NOT_EVALUABLE cannot carry recommended actions."
            )
    elif set(actions_by_reason_code) != selected_reason_codes:
        raise DecisionAnalysisBoundaryError(
            "Each selected AI Decision reason requires exactly one action."
        )

    selected_condition_candidates: list[DecisionConditionCandidate] = []
    for draft in proposal.conditions:
        matches = tuple(
            item
            for item in packet.condition_candidates
            if _candidate_payload(item) == draft.model_dump(mode="json")
        )
        if len(matches) != 1:
            raise DecisionAnalysisBoundaryError(
                "AI Decision condition was not selected exactly from supplied candidates."
            )
        selected_condition_candidates.append(matches[0])
    if len({item.candidate_id for item in selected_condition_candidates}) != len(
        selected_condition_candidates
    ):
        raise DecisionAnalysisBoundaryError("AI Decision selected a duplicate condition.")

    reference_map = {item.reference_id: item for item in packet.reference_evidence}
    for point in proposal.human_attention_points:
        if any(
            reference_map.get(reference_id) is None
            or reference_map[reference_id].kind
            is not DecisionReferenceKind.REQUIRED_CONTROL
            for reference_id in point.source_reference_ids
        ):
            raise DecisionAnalysisBoundaryError(
                "AI Decision attention points must reference supplied required controls."
            )
    for item in (
        *proposal.reasons,
        *proposal.recommended_actions,
        *proposal.human_attention_points,
    ):
        _validate_reference_lineage(
            source_reference_ids=item.source_reference_ids,
            evidence_ids=item.evidence_ids,
            reference_map=reference_map,
        )
    for item in proposal.conditions:
        _validate_reference_lineage(
            source_reference_ids=item.source_reference_ids,
            evidence_ids=item.evidence_ids,
            reference_map=reference_map,
        )
        if item.target is not None:
            _validate_reference_lineage(
                source_reference_ids=item.target.source_reference_ids,
                evidence_ids=item.target.evidence_ids,
                reference_map=reference_map,
            )

    strategies_by_id = {
        item.strategy_id: item for item in packet.negotiation_strategy_candidates
    }
    if (
        len(set(proposal.selected_negotiation_strategy_ids))
        != len(proposal.selected_negotiation_strategy_ids)
        or not set(proposal.selected_negotiation_strategy_ids).issubset(
            strategies_by_id
        )
    ):
        raise DecisionAnalysisBoundaryError(
            "AI Decision selected an unknown or duplicate negotiation strategy."
        )
    selected_strategies = tuple(
        strategies_by_id[strategy_id]
        for strategy_id in proposal.selected_negotiation_strategy_ids
    )
    selected_condition_codes = {
        item.code for item in selected_condition_candidates
    }
    if any(
        item.condition_code not in selected_condition_codes
        for item in selected_strategies
    ):
        raise DecisionAnalysisBoundaryError(
            "AI Decision strategy is unrelated to its selected condition."
        )
    for strategy in selected_strategies:
        _validate_reference_lineage(
            source_reference_ids=strategy.source_reference_ids,
            evidence_ids=strategy.evidence_ids,
            reference_map=reference_map,
        )

    known_options = {item.option_id for item in packet.banking_options}
    if (
        len(set(proposal.selected_option_ids)) != len(proposal.selected_option_ids)
        or not set(proposal.selected_option_ids).issubset(known_options)
    ):
        raise DecisionAnalysisBoundaryError(
            "AI Decision selected an unknown or duplicate Banking option."
        )
    if len(proposal.selected_option_ids) > 1:
        canonical = tuple(sorted(proposal.selected_option_ids))
        allowed = {
            tuple(sorted(item)) for item in packet.allowed_option_combinations
        }
        if canonical not in allowed:
            raise DecisionAnalysisBoundaryError(
                "AI Decision selected an unconfigured Banking option combination."
            )

    if proposal.recommendation is DecisionRecommendation.ACCEPT:
        if proposal.conditions or proposal.selected_negotiation_strategy_ids:
            raise DecisionAnalysisBoundaryError(
                "ACCEPT cannot carry unresolved conditions or negotiation strategies."
            )
    elif proposal.recommendation is DecisionRecommendation.NEGOTIATE_CONDITIONS_TO_ACCEPT:
        if not proposal.conditions or not any(
            item.status
            in {DecisionConditionStatus.OPEN, DecisionConditionStatus.NOT_EVALUABLE}
            for item in proposal.conditions
        ):
            raise DecisionAnalysisBoundaryError(
                "NEGOTIATE requires at least one unresolved supplied condition."
            )
        unresolved_candidate_ids = {
            item.candidate_id
            for item in packet.condition_candidates
            if item.status
            in {DecisionConditionStatus.OPEN, DecisionConditionStatus.NOT_EVALUABLE}
        }
        if {
            item.candidate_id for item in selected_condition_candidates
        } != unresolved_candidate_ids:
            raise DecisionAnalysisBoundaryError(
                "NEGOTIATE must preserve every unresolved supplied condition."
            )
        strategy_condition_codes = {
            item.condition_code for item in packet.negotiation_strategy_candidates
        }
        for condition_code in selected_condition_codes & strategy_condition_codes:
            chosen = tuple(
                item
                for item in selected_strategies
                if item.condition_code == condition_code
            )
            if len(chosen) != 1:
                raise DecisionAnalysisBoundaryError(
                    "NEGOTIATE must select exactly one supplied strategy for each "
                    "strategy-backed condition."
                )
    elif proposal.recommendation in {
        DecisionRecommendation.DO_NOT_ACCEPT,
        DecisionRecommendation.NOT_EVALUABLE,
    }:
        if (
            proposal.selected_option_ids
            or proposal.selected_negotiation_strategy_ids
        ):
            raise DecisionAnalysisBoundaryError(
                "A non-proceeding recommendation cannot select an option or strategy."
            )
        if proposal.conditions:
            raise DecisionAnalysisBoundaryError(
                "A non-proceeding recommendation cannot select negotiation conditions."
            )
        if proposal.recommendation is DecisionRecommendation.NOT_EVALUABLE and (
            proposal.confidence is not DecisionConfidence.NOT_EVALUABLE
        ):
            raise DecisionAnalysisBoundaryError(
                "NOT_EVALUABLE requires NOT_EVALUABLE confidence."
            )

    validate_decision_proposal_prose(proposal=proposal, packet=packet)
    executive_summary = (
        _strategy_founder_summary(selected_strategies)
        or proposal.executive_summary
    )

    reasons = tuple(
        DecisionReason(
            reason_id=deterministic_id(
                "DREASON", packet.packet_id, candidate.candidate_id
            ),
            recommended_action=(
                actions_by_reason_code[draft.code].action
                if draft.code in actions_by_reason_code
                else None
            ),
            **draft.model_dump(),
        )
        for draft, candidate in zip(
            proposal.reasons, selected_reason_candidates, strict=True
        )
    )
    conditions = tuple(
        NegotiationCondition(
            condition_id=deterministic_id(
                "DCOND", packet.packet_id, candidate.candidate_id
            ),
            **draft.model_dump(),
        )
        for draft, candidate in zip(
            proposal.conditions, selected_condition_candidates, strict=True
        )
    )
    attention_points = tuple(
        DecisionHumanAttentionPoint(
            attention_point_id=deterministic_id(
                "DATN",
                packet.packet_id,
                item.code,
                item.text,
                item.source_reference_ids,
                item.evidence_ids,
            ),
            **item.model_dump(),
        )
        for item in proposal.human_attention_points
    )
    evidence_ids = tuple(
        dict.fromkeys(
            evidence_id
            for item in (
                *reasons,
                *conditions,
                *selected_strategies,
                *attention_points,
            )
            for evidence_id in item.evidence_ids
        )
    )
    analysis_id = ai_decision_analysis_id(
        packet_id=packet.packet_id,
        recommendation=proposal.recommendation,
        executive_summary=executive_summary,
        reasons=reasons,
        conditions=conditions,
        selected_negotiation_strategy_ids=(
            proposal.selected_negotiation_strategy_ids
        ),
        selected_option_ids=proposal.selected_option_ids,
        confidence=proposal.confidence,
        human_attention_points=attention_points,
        source=composition.source,
        model=composition.model,
        prompt_version=composition.prompt_version,
        input_hash=composition.input_hash,
    )
    return AIDecisionAnalysis(
        analysis_id=analysis_id,
        packet_id=packet.packet_id,
        evaluation_case_id=packet.evaluation_case_id,
        dataset_id=packet.dataset_id,
        contract_id=packet.contract_id,
        internal_decision_package_artifact=packet.internal_decision_package_artifact,
        final_risk_artifact=packet.final_risk_artifact,
        recommendation=proposal.recommendation,
        executive_summary=executive_summary,
        reasons=reasons,
        conditions=conditions,
        selected_negotiation_strategy_ids=(
            proposal.selected_negotiation_strategy_ids
        ),
        selected_negotiation_strategies=selected_strategies,
        selected_option_ids=proposal.selected_option_ids,
        confidence=proposal.confidence,
        human_attention_points=attention_points,
        source=composition.source,
        model=composition.model,
        prompt_version=composition.prompt_version,
        input_hash=composition.input_hash,
        fallback_reason=composition.fallback_reason,
        evidence_ids=evidence_ids,
    )


def assemble_decision_card(
    *,
    packet: DecisionScenarioPacket,
    analysis_artifact: ArtifactEnvelope,
    analysis: AIDecisionAnalysis,
) -> DecisionCard:
    """Assemble a detailed Card from one exact guarded analysis artifact."""

    if analysis_artifact.artifact_type is not ArtifactType.AI_DECISION_ANALYSIS:
        raise DecisionAnalysisBoundaryError(
            "Decision Card requires an AI Decision Analysis artifact."
        )
    if AIDecisionAnalysis.model_validate(analysis_artifact.payload) != analysis:
        raise DecisionAnalysisBoundaryError(
            "Decision Card analysis differs from the persisted artifact payload."
        )
    if (
        analysis.packet_id != packet.packet_id
        or analysis.evaluation_case_id != packet.evaluation_case_id
        or analysis.dataset_id != packet.dataset_id
        or analysis.contract_id != packet.contract_id
        or analysis.internal_decision_package_artifact
        != packet.internal_decision_package_artifact
        or analysis.final_risk_artifact != packet.final_risk_artifact
    ):
        raise DecisionAnalysisBoundaryError(
            "Decision Card inputs do not share exact upstream lineage."
        )
    options_by_id = {item.option_id: item for item in packet.banking_options}
    selected_options = tuple(
        options_by_id[option_id] for option_id in analysis.selected_option_ids
    )
    strategies_by_id = {
        item.strategy_id: item for item in packet.negotiation_strategy_candidates
    }
    selected_strategies = tuple(
        strategies_by_id[strategy_id]
        for strategy_id in analysis.selected_negotiation_strategy_ids
    )
    if analysis.selected_negotiation_strategies != selected_strategies:
        raise DecisionAnalysisBoundaryError(
            "AI Decision Analysis strategy snapshots differ from its packet."
        )
    kwargs: dict[str, Any] = {
        "evaluation_case_id": packet.evaluation_case_id,
        "dataset_id": packet.dataset_id,
        "contract_id": packet.contract_id,
        "ai_analysis_id": analysis.analysis_id,
        "ai_analysis_artifact": _exact_artifact_ref(analysis_artifact),
        "internal_decision_package_artifact": packet.internal_decision_package_artifact,
        "final_risk_artifact": packet.final_risk_artifact,
        "recommendation": analysis.recommendation,
        "executive_summary": analysis.executive_summary,
        "reasons": analysis.reasons,
        "conditions": analysis.conditions,
        "selected_negotiation_strategy_ids": (
            analysis.selected_negotiation_strategy_ids
        ),
        "selected_negotiation_strategies": selected_strategies,
        "confidence": analysis.confidence,
        "selected_option_ids": analysis.selected_option_ids,
        "selected_options": selected_options,
        "finance_metrics": packet.finance_metrics,
        "operations_metrics": packet.operations_metrics,
        "calculations": packet.calculations,
        "residual_risk_level": packet.residual_risk_level,
        "major_exception_status": packet.major_exception_status,
        "residual_findings": packet.residual_findings,
        "required_controls": packet.required_controls,
        "limitations": packet.limitations,
        "human_attention_points": analysis.human_attention_points,
        "document_release_package": packet.document_release_package,
        "evidence_ids": packet.known_evidence_ids,
    }
    unvalidated = DecisionCard.model_construct(decision_card_id="PENDING", **kwargs)
    return DecisionCard(
        decision_card_id=decision_card_id(unvalidated),
        **kwargs,
    )
