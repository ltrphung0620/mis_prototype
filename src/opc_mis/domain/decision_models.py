"""Typed contracts for evidence-bound AI Decision analysis and Decision Cards.

OpenAI may propose a recommendation and negotiation conditions, but it never
owns deterministic calculations, evidence identity, approval, persistence, or
external execution.  The canonical models in this module are intentionally
strict so an untrusted model draft can only reference deterministic candidates
and evidence supplied by :class:`DecisionScenarioPacket`.
"""

from __future__ import annotations

import math
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal
from enum import StrEnum
from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictFloat,
    StrictInt,
    StrictStr,
    field_validator,
    model_validator,
)

from opc_mis.domain.artifacts import ArtifactEnvelope
from opc_mis.domain.components import ComponentResult
from opc_mis.domain.enums import (
    ArtifactType,
    ComponentStatus,
    CurrencyCode,
    FinalRiskAssessmentStatus,
    FinanceMetric,
    MajorExceptionStatus,
    RiskLevel,
    WorkflowStatus,
)
from opc_mis.domain.lineage import deterministic_id
from opc_mis.domain.missing_data import MissingDataRequest
from opc_mis.domain.validation_reports import ValidationReport

DecisionScalar = StrictBool | StrictInt | StrictFloat | StrictStr | None


class DecisionRecommendation(StrEnum):
    """Recommendations the AI may propose for deterministic validation."""

    ACCEPT = "ACCEPT"
    NEGOTIATE_CONDITIONS_TO_ACCEPT = "NEGOTIATE_CONDITIONS_TO_ACCEPT"
    DO_NOT_ACCEPT = "DO_NOT_ACCEPT"
    NOT_EVALUABLE = "NOT_EVALUABLE"


class DecisionConfidence(StrEnum):
    """Qualitative confidence; no ungrounded numeric score is synthesized."""

    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    NOT_EVALUABLE = "NOT_EVALUABLE"


class DecisionAnalysisSource(StrEnum):
    """How the untrusted structured proposal was composed."""

    OPENAI = "OPENAI"
    DETERMINISTIC_FALLBACK = "DETERMINISTIC_FALLBACK"


class DecisionReferenceKind(StrEnum):
    """Whitelisted source-reference kinds exposed to the Decision model."""

    FINANCE_FACT = "FINANCE_FACT"
    FINANCE_OBSERVATION = "FINANCE_OBSERVATION"
    FINANCE_LIMITATION = "FINANCE_LIMITATION"
    OPERATIONS_FACT = "OPERATIONS_FACT"
    OPERATIONS_OBSERVATION = "OPERATIONS_OBSERVATION"
    OPERATIONS_LIMITATION = "OPERATIONS_LIMITATION"
    RESIDUAL_RISK_FINDING = "RESIDUAL_RISK_FINDING"
    REQUIRED_CONTROL = "REQUIRED_CONTROL"
    RISK_LIMITATION = "RISK_LIMITATION"
    BANKING_OPTION = "BANKING_OPTION"
    BANKING_RESULT = "BANKING_RESULT"
    DOCUMENT_RELEASE_PACKAGE = "DOCUMENT_RELEASE_PACKAGE"
    INTERNAL_DECISION_PACKAGE = "INTERNAL_DECISION_PACKAGE"
    FINAL_RISK_ASSESSMENT = "FINAL_RISK_ASSESSMENT"


class DecisionMetricRole(StrEnum):
    """Permitted use of one deterministic metric in Decision analysis."""

    CASE_FACT = "CASE_FACT"
    POLICY_TARGET = "POLICY_TARGET"


class DecisionConditionCategory(StrEnum):
    """Business area addressed by a proposed negotiation condition."""

    COMMERCIAL = "COMMERCIAL"
    FINANCE = "FINANCE"
    BANKING = "BANKING"
    DELIVERY_CAPACITY = "DELIVERY_CAPACITY"
    DOCUMENT = "DOCUMENT"
    GOVERNANCE = "GOVERNANCE"
    EVIDENCE = "EVIDENCE"


class DecisionConditionStatus(StrEnum):
    """Evidence status of one condition at card-creation time."""

    OPEN = "OPEN"
    SATISFIED = "SATISFIED"
    NOT_EVALUABLE = "NOT_EVALUABLE"


class DecisionEnforcementPoint(StrEnum):
    """Latest workflow boundary at which a condition must be verified."""

    BEFORE_ACCEPTANCE = "BEFORE_ACCEPTANCE"
    BEFORE_CONTRACT_SIGNING = "BEFORE_CONTRACT_SIGNING"
    BEFORE_EXTERNAL_COMMITMENT = "BEFORE_EXTERNAL_COMMITMENT"
    BEFORE_DOCUMENT_RELEASE = "BEFORE_DOCUMENT_RELEASE"
    BEFORE_EXECUTION = "BEFORE_EXECUTION"


class DecisionTargetOperator(StrEnum):
    """Safe operators supported by structured negotiation targets."""

    GREATER_THAN_OR_EQUAL = "GTE"
    LESS_THAN_OR_EQUAL = "LTE"
    EQUAL = "EQ"


class DecisionCalculationCode(StrEnum):
    """Whitelisted deterministic calculations available to the Decision Card."""

    MULTIPLY = "MULTIPLY"
    DIFFERENCE = "DIFFERENCE"
    PERCENTAGE_POINT_DIFFERENCE = "PERCENTAGE_POINT_DIFFERENCE"
    MINIMUM_REVENUE_INCREASE_FOR_TARGET_MARGIN = (
        "MINIMUM_REVENUE_INCREASE_FOR_TARGET_MARGIN"
    )
    MINIMUM_COST_REDUCTION_FOR_TARGET_MARGIN = (
        "MINIMUM_COST_REDUCTION_FOR_TARGET_MARGIN"
    )


class DecisionNegotiationStrategyType(StrEnum):
    """Deterministic commercial levers from which OpenAI may select."""

    INCREASE_CUSTOMER_PRICE = "INCREASE_CUSTOMER_PRICE"
    REDUCE_EVIDENCED_COST_AT_FIXED_REVENUE = (
        "REDUCE_EVIDENCED_COST_AT_FIXED_REVENUE"
    )


MARGIN_NEGOTIATION_CONDITION_CODE = "MEET_OPC_GROSS_MARGIN_TARGET"
MARGIN_NEGOTIATION_CONDITION_TITLE = "Meet the explicit OPC gross-margin target"
MARGIN_NEGOTIATION_CONDITION_DESCRIPTION = (
    "Select one precomputed price or evidenced-cost strategy, obtain the "
    "customer's agreement, and rerun Finance before treating the target as met."
)
MARGIN_NEGOTIATION_CONDITION_VERIFICATION_EVIDENCE_TYPES = (
    "UPDATED_FINANCE_ASSESSMENT",
)
MARGIN_NEGOTIATION_CONDITION_EXPECTED_RISK_EFFECT = (
    "Closes the measured margin gap; Risk must separately reassess the residual "
    "risk after new evidence arrives."
)
MARGIN_STRATEGY_INPUTS_CONDITION_CODE = "OBTAIN_MARGIN_STRATEGY_INPUTS"
MARGIN_STRATEGY_INPUTS_CONDITION_TITLE = (
    "Obtain inputs for a bounded gross-margin strategy"
)
MARGIN_STRATEGY_INPUTS_CONDITION_DESCRIPTION = (
    "The current margin is below target, but exact attributable linked-order "
    "revenue and estimated-cost operands cannot support a bounded strategy. "
    "Correct the inputs and rerun Finance before proposing a commercial adjustment."
)
MARGIN_STRATEGY_INPUTS_CONDITION_VERIFICATION_EVIDENCE_TYPES = (
    "CORRECTED_LINKED_ORDER_REVENUE_AND_COST_EVIDENCE",
    "UPDATED_FINANCE_ASSESSMENT",
)
MARGIN_STRATEGY_INPUTS_CONDITION_EXPECTED_RISK_EFFECT = (
    "Enables deterministic strategy calculation; it does not establish that the "
    "margin target has been met."
)
MARGIN_BENCHMARK_INPUTS_CONDITION_CODE = "OBTAIN_GROSS_MARGIN_BENCHMARKS"
MARGIN_BENCHMARK_INPUTS_CONDITION_TITLE = (
    "Obtain evaluable gross-margin benchmarks"
)
MARGIN_BENCHMARK_INPUTS_CONDITION_DESCRIPTION = (
    "A valid current linked-order gross margin and explicit OPC target margin are "
    "both required before Decision can evaluate acceptance or propose a bounded "
    "commercial adjustment. Correct the evidence and rerun Finance."
)
MARGIN_BENCHMARK_INPUTS_CONDITION_VERIFICATION_EVIDENCE_TYPES = (
    "VALID_ORDER_GROSS_MARGIN",
    "VALID_OPC_TARGET_GROSS_MARGIN",
    "UPDATED_FINANCE_ASSESSMENT",
)
MARGIN_BENCHMARK_INPUTS_CONDITION_EXPECTED_RISK_EFFECT = (
    "Enables deterministic comparison against the OPC margin policy; it does not "
    "establish acceptance eligibility."
)


class ExactDecisionArtifactRef(BaseModel):
    """Exact immutable upstream artifact identity."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    artifact_id: StrictStr = Field(min_length=1)
    artifact_type: ArtifactType
    version: int = Field(ge=1)
    input_hash: StrictStr = Field(min_length=1)


class DecisionReferenceEvidence(BaseModel):
    """Evidence IDs authorized for one source reference."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    reference_id: StrictStr = Field(min_length=1)
    kind: DecisionReferenceKind
    evidence_ids: tuple[StrictStr, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_evidence(self) -> DecisionReferenceEvidence:
        if len(set(self.evidence_ids)) != len(self.evidence_ids):
            raise ValueError("Decision reference evidence IDs must be unique")
        return self


class DecisionMetricSnapshot(BaseModel):
    """One deterministic, case-attributable Finance or Operations metric."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    fact_id: StrictStr = Field(min_length=1)
    metric: StrictStr = Field(min_length=1)
    value: DecisionScalar
    unit: StrictStr = Field(min_length=1)
    calculation: StrictStr = Field(min_length=1)
    quality: StrictStr = Field(min_length=1)
    evidence_ids: tuple[StrictStr, ...] = Field(min_length=1)
    role: DecisionMetricRole
    contract_attributable: StrictBool

    @field_validator("value")
    @classmethod
    def reject_non_finite_value(cls, value: DecisionScalar) -> DecisionScalar:
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("Decision metrics cannot contain NaN or infinity")
        return value

    @model_validator(mode="after")
    def validate_evidence(self) -> DecisionMetricSnapshot:
        if len(set(self.evidence_ids)) != len(self.evidence_ids):
            raise ValueError("Decision metric evidence IDs must be unique")
        if (self.role is DecisionMetricRole.CASE_FACT) != self.contract_attributable:
            raise ValueError(
                "Only CASE_FACT metrics may be attributed to the contract"
            )
        return self


def decision_current_margin_metric_is_evaluable(
    metric: DecisionMetricSnapshot | None,
) -> bool:
    """Return whether a current linked-order margin is authoritative and usable."""

    return bool(
        metric is not None
        and metric.metric == FinanceMetric.ORDER_GROSS_MARGIN.value
        and metric.role is DecisionMetricRole.CASE_FACT
        and metric.contract_attributable
        and metric.unit == "RATIO"
        and isinstance(metric.value, (int, float))
        and not isinstance(metric.value, bool)
        and metric.value <= 1
    )


def decision_target_margin_metric_is_evaluable(
    metric: DecisionMetricSnapshot | None,
) -> bool:
    """Return whether the OPC target is an explicit, plausible policy ratio."""

    return bool(
        metric is not None
        and metric.metric == FinanceMetric.OPC_TARGET_GROSS_MARGIN.value
        and metric.role is DecisionMetricRole.POLICY_TARGET
        and not metric.contract_attributable
        and metric.unit == "RATIO"
        and isinstance(metric.value, (int, float))
        and not isinstance(metric.value, bool)
        and 0 < metric.value < 1
    )


class DecisionCalculationOperand(BaseModel):
    """One exact operand of a Decision-owned deterministic calculation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_reference_id: StrictStr = Field(min_length=1)
    label: StrictStr = Field(min_length=1)
    value: StrictInt | StrictFloat
    unit: StrictStr = Field(min_length=1)
    evidence_ids: tuple[StrictStr, ...] = Field(min_length=1)

    @field_validator("value")
    @classmethod
    def reject_non_finite_value(cls, value: int | float) -> int | float:
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("Decision calculation operands must be finite")
        return value


class DecisionCalculation(BaseModel):
    """Auditable calculation performed before OpenAI sees the packet."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    calculation_id: StrictStr = Field(min_length=1)
    code: DecisionCalculationCode
    formula: StrictStr = Field(min_length=1)
    operands: tuple[DecisionCalculationOperand, ...] = Field(min_length=2)
    result_value: StrictInt | StrictFloat
    result_unit: StrictStr = Field(min_length=1)
    evidence_ids: tuple[StrictStr, ...] = Field(min_length=1)

    @field_validator("result_value")
    @classmethod
    def reject_non_finite_result(cls, value: int | float) -> int | float:
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("Decision calculation results must be finite")
        return value

    @model_validator(mode="after")
    def validate_calculation(self) -> DecisionCalculation:
        expected_evidence = tuple(
            dict.fromkeys(
                evidence_id
                for operand in self.operands
                for evidence_id in operand.evidence_ids
            )
        )
        if self.evidence_ids != expected_evidence:
            raise ValueError("Calculation evidence must exactly index operand evidence")
        expected_id = deterministic_id(
            "DCALC",
            self.code,
            self.formula,
            tuple(item.model_dump(mode="json") for item in self.operands),
            self.result_value,
            self.result_unit,
        )
        if self.calculation_id != expected_id:
            raise ValueError("Decision calculation_id is unstable")
        return self


def decision_negotiation_strategy_title(
    strategy_type: DecisionNegotiationStrategyType,
) -> str:
    """Return the canonical Founder-facing title for a bounded strategy."""

    if strategy_type is DecisionNegotiationStrategyType.INCREASE_CUSTOMER_PRICE:
        return "Tăng giá cho phạm vi order đã liên kết"
    return "Giảm chi phí có bằng chứng trong khi giữ nguyên doanh thu"


def decision_negotiation_strategy_founder_instruction(
    *,
    strategy_type: DecisionNegotiationStrategyType,
    baseline_revenue: int,
    baseline_cost: int,
    required_adjustment_value: int,
    resulting_revenue: int,
    resulting_cost: int,
) -> str:
    """Render exact negotiation instructions from deterministic numeric fields."""

    if strategy_type is DecisionNegotiationStrategyType.INCREASE_CUSTOMER_PRICE:
        return (
            "Đàm phán tăng doanh thu của phạm vi order đã liên kết tối thiểu "
            f"{required_adjustment_value:,} VND, từ {baseline_revenue:,} VND lên "
            f"{resulting_revenue:,} VND, trong khi giữ nguyên estimated cost "
            f"{baseline_cost:,} VND; phải cập nhật order hoặc amendment và chạy "
            "lại Finance trước khi coi điều kiện đã đạt."
        )
    return (
        "Đàm phán điều chỉnh phạm vi hoặc điều kiện thực hiện để giảm estimated "
        f"cost tối thiểu {required_adjustment_value:,} VND, từ {baseline_cost:,} VND "
        f"xuống tối đa {resulting_cost:,} VND, trong khi giữ nguyên doanh thu "
        f"order {baseline_revenue:,} VND; phải có cost evidence mới và chạy "
        "lại Finance trước khi coi điều kiện đã đạt."
    )


def decision_negotiation_strategy_verification_evidence_types(
    strategy_type: DecisionNegotiationStrategyType,
) -> tuple[str, ...]:
    """Return the only evidence types allowed to verify one selected strategy."""

    if strategy_type is DecisionNegotiationStrategyType.INCREASE_CUSTOMER_PRICE:
        return (
            "CUSTOMER_ACCEPTED_COMMERCIAL_AMENDMENT",
            "UPDATED_ORDER_REVENUE",
            "UPDATED_FINANCE_ASSESSMENT",
        )
    return (
        "CUSTOMER_ACCEPTED_SCOPE_OR_DELIVERY_AMENDMENT",
        "UPDATED_ESTIMATED_COST_EVIDENCE",
        "UPDATED_FINANCE_ASSESSMENT",
    )


class DecisionNegotiationStrategyCandidate(BaseModel):
    """One precomputed alternative that can satisfy a negotiation condition.

    OpenAI may select the candidate ID, but every amount, instruction, assumption,
    formula reference, verification requirement, and evidence reference is prepared
    before the model is invoked.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    strategy_id: StrictStr = Field(min_length=1)
    condition_code: StrictStr = Field(min_length=1)
    strategy_type: DecisionNegotiationStrategyType
    title: StrictStr = Field(min_length=1)
    founder_instruction: StrictStr = Field(min_length=1)
    assumptions: tuple[StrictStr, ...] = Field(min_length=1)
    baseline_revenue: StrictInt = Field(gt=0)
    baseline_cost: StrictInt = Field(ge=0)
    target_margin: StrictFloat = Field(gt=0, lt=1)
    required_adjustment_value: StrictInt = Field(gt=0)
    resulting_revenue: StrictInt = Field(gt=0)
    resulting_cost: StrictInt = Field(ge=0)
    currency: CurrencyCode = CurrencyCode.VND
    calculation_id: StrictStr = Field(min_length=1)
    verification_evidence_types: tuple[StrictStr, ...] = Field(min_length=1)
    source_reference_ids: tuple[StrictStr, ...] = Field(min_length=1)
    evidence_ids: tuple[StrictStr, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_strategy(self) -> DecisionNegotiationStrategyCandidate:
        if self.condition_code != MARGIN_NEGOTIATION_CONDITION_CODE:
            raise ValueError(
                "Margin strategy must reference the canonical margin condition"
            )
        if self.currency is not CurrencyCode.VND:
            raise ValueError("Negotiation strategy amounts must use VND")
        for label, values in (
            ("assumptions", self.assumptions),
            ("verification_evidence_types", self.verification_evidence_types),
            ("source_reference_ids", self.source_reference_ids),
            ("evidence_ids", self.evidence_ids),
        ):
            if len(set(values)) != len(values):
                raise ValueError(f"Negotiation strategy {label} must be unique")
        baseline_revenue = Decimal(self.baseline_revenue)
        baseline_cost = Decimal(self.baseline_cost)
        resulting_revenue = Decimal(self.resulting_revenue)
        resulting_cost = Decimal(self.resulting_cost)
        target_margin = Decimal(str(self.target_margin))
        baseline_margin = (
            baseline_revenue - baseline_cost
        ) / baseline_revenue
        resulting_margin = (
            resulting_revenue - resulting_cost
        ) / resulting_revenue
        if baseline_margin >= target_margin:
            raise ValueError(
                "Negotiation strategy is unnecessary because baseline margin meets target"
            )
        if self.strategy_type is DecisionNegotiationStrategyType.INCREASE_CUSTOMER_PRICE:
            if (
                self.resulting_cost != self.baseline_cost
                or self.resulting_revenue - self.baseline_revenue
                != self.required_adjustment_value
            ):
                raise ValueError(
                    "Price strategy must increase revenue by the exact adjustment and "
                    "hold cost constant"
                )
        elif (
            self.strategy_type
            is DecisionNegotiationStrategyType.REDUCE_EVIDENCED_COST_AT_FIXED_REVENUE
        ) and (
            self.resulting_revenue != self.baseline_revenue
            or self.baseline_cost - self.resulting_cost
            != self.required_adjustment_value
        ):
            raise ValueError(
                "Cost strategy must reduce cost by the exact adjustment and hold "
                "revenue constant"
            )
        if resulting_margin < target_margin:
            raise ValueError("Negotiation strategy does not reach its target margin")
        expected_title = decision_negotiation_strategy_title(self.strategy_type)
        expected_instruction = decision_negotiation_strategy_founder_instruction(
            strategy_type=self.strategy_type,
            baseline_revenue=self.baseline_revenue,
            baseline_cost=self.baseline_cost,
            required_adjustment_value=self.required_adjustment_value,
            resulting_revenue=self.resulting_revenue,
            resulting_cost=self.resulting_cost,
        )
        expected_verification = (
            decision_negotiation_strategy_verification_evidence_types(
                self.strategy_type
            )
        )
        expected_assumptions = (
            (
                "EXPLICITLY_LINKED_ORDER_SCOPE_ONLY",
                "ESTIMATED_COST_UNCHANGED",
            )
            if self.strategy_type
            is DecisionNegotiationStrategyType.INCREASE_CUSTOMER_PRICE
            else (
                "EXPLICITLY_LINKED_ORDER_SCOPE_ONLY",
                "ORDER_REVENUE_UNCHANGED",
            )
        )
        if (
            self.title != expected_title
            or self.founder_instruction != expected_instruction
            or self.assumptions != expected_assumptions
            or self.verification_evidence_types != expected_verification
        ):
            raise ValueError(
                "Negotiation strategy display, assumptions, and verification are "
                "not canonical"
            )
        expected_id = deterministic_id(
            "DNSTRAT",
            self.condition_code,
            self.strategy_type,
            self.title,
            self.founder_instruction,
            self.assumptions,
            self.baseline_revenue,
            self.baseline_cost,
            self.target_margin,
            self.required_adjustment_value,
            self.resulting_revenue,
            self.resulting_cost,
            self.currency,
            self.calculation_id,
            self.verification_evidence_types,
            self.source_reference_ids,
            self.evidence_ids,
        )
        if self.strategy_id != expected_id:
            raise ValueError("Negotiation strategy_id is unstable")
        return self


class DecisionOptionSnapshot(BaseModel):
    """One real Banking candidate and its exact non-binding result, if any."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    option_id: StrictStr = Field(min_length=1)
    bank_product_id: StrictStr = Field(min_length=1)
    provider: StrictStr = Field(min_length=1)
    product_name: StrictStr = Field(min_length=1)
    requested_amount: StrictInt | None = Field(default=None, gt=0)
    supported_amount: StrictInt | None = Field(default=None, gt=0)
    currency: CurrencyCode = CurrencyCode.VND
    annual_rate_or_fee: StrictInt | StrictFloat | None = None
    processing_fee_rate: StrictInt | StrictFloat | None = None
    collateral_ratio: StrictInt | StrictFloat | None = None
    minimum_amount: StrictInt | StrictFloat | None = None
    precheck_outcome: StrictStr | None = None
    precheck_authority: StrictStr | None = None
    non_binding: StrictBool = True
    calculation_ids: tuple[StrictStr, ...] = ()
    evidence_ids: tuple[StrictStr, ...] = Field(min_length=1)

    @field_validator(
        "annual_rate_or_fee",
        "processing_fee_rate",
        "collateral_ratio",
        "minimum_amount",
    )
    @classmethod
    def reject_non_finite_catalog_value(
        cls, value: int | float | None
    ) -> int | float | None:
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("Decision option values must be finite")
        return value

    @model_validator(mode="after")
    def validate_option(self) -> DecisionOptionSnapshot:
        if self.currency is not CurrencyCode.VND:
            raise ValueError("Decision option amounts must use VND")
        if self.supported_amount is not None and self.requested_amount is None:
            raise ValueError("supported_amount requires requested_amount")
        if len(set(self.calculation_ids)) != len(self.calculation_ids):
            raise ValueError("Decision option calculation IDs must be unique")
        if len(set(self.evidence_ids)) != len(self.evidence_ids):
            raise ValueError("Decision option evidence IDs must be unique")
        return self


class DecisionRiskFindingSnapshot(BaseModel):
    """Open residual finding supplied to OpenAI without reinterpretation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    finding_id: StrictStr = Field(min_length=1)
    code: StrictStr = Field(min_length=1)
    title: StrictStr = Field(min_length=1)
    detail: StrictStr = Field(min_length=1)
    severity: StrictStr = Field(min_length=1)
    status: StrictStr = Field(min_length=1)
    evidence_ids: tuple[StrictStr, ...] = Field(min_length=1)


class DecisionControlSnapshot(BaseModel):
    """Required control supplied as a constraint, never as an executed action."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    control_id: StrictStr = Field(min_length=1)
    code: StrictStr = Field(min_length=1)
    description: StrictStr = Field(min_length=1)
    protected_action: StrictStr | None = None
    source_reference_ids: tuple[StrictStr, ...] = Field(min_length=1)
    evidence_ids: tuple[StrictStr, ...] = ()


class DecisionLimitationSnapshot(BaseModel):
    """Evidence limitation that the model must preserve as unknown."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    limitation_id: StrictStr = Field(min_length=1)
    code: StrictStr = Field(min_length=1)
    detail: StrictStr = Field(min_length=1)
    evidence_ids: tuple[StrictStr, ...] = ()


class DecisionDocumentReleaseSnapshot(BaseModel):
    """Exact masked package shown on a Card; it is not release authorization."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    artifact: ExactDecisionArtifactRef
    release_package_id: StrictStr = Field(min_length=1)
    recipient: StrictStr = Field(min_length=1)
    purpose: StrictStr = Field(min_length=1)
    document_codes: tuple[StrictStr, ...] = Field(min_length=1)
    masking_manifest_id: StrictStr = Field(min_length=1)
    limitation_codes: tuple[StrictStr, ...] = ()
    evidence_ids: tuple[StrictStr, ...] = Field(min_length=1)
    release_authorized: Literal[False] = False


class DecisionConditionTarget(BaseModel):
    """Evidence-backed measurable target prepared before OpenAI is invoked."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    metric: StrictStr = Field(min_length=1)
    operator: DecisionTargetOperator
    current_value: StrictInt | StrictFloat | None = None
    target_value: StrictInt | StrictFloat
    unit: StrictStr = Field(min_length=1)
    currency: CurrencyCode | None = None
    source_reference_ids: tuple[StrictStr, ...] = Field(min_length=1)
    evidence_ids: tuple[StrictStr, ...] = Field(min_length=1)

    @field_validator("current_value", "target_value")
    @classmethod
    def reject_non_finite_target(
        cls, value: int | float | None
    ) -> int | float | None:
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("Decision targets must be finite")
        return value

    @model_validator(mode="after")
    def validate_currency(self) -> DecisionConditionTarget:
        if self.currency is not None and self.currency is not CurrencyCode.VND:
            raise ValueError("Decision monetary targets must use VND")
        return self


class DecisionReasonCandidate(BaseModel):
    """Deterministic reason candidate from which OpenAI may select."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    candidate_id: StrictStr = Field(min_length=1)
    code: StrictStr = Field(min_length=1)
    title: StrictStr = Field(min_length=1)
    detail: StrictStr = Field(min_length=1)
    source_reference_ids: tuple[StrictStr, ...] = Field(min_length=1)
    evidence_ids: tuple[StrictStr, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_candidate_id(self) -> DecisionReasonCandidate:
        expected_id = deterministic_id(
            "DRC",
            self.code,
            self.title,
            self.detail,
            self.source_reference_ids,
            self.evidence_ids,
        )
        if self.candidate_id != expected_id:
            raise ValueError("Decision reason candidate_id is unstable")
        return self


class DecisionConditionCandidate(BaseModel):
    """Deterministic condition candidate from which OpenAI may select."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    candidate_id: StrictStr = Field(min_length=1)
    code: StrictStr = Field(min_length=1)
    category: DecisionConditionCategory
    title: StrictStr = Field(min_length=1)
    description: StrictStr = Field(min_length=1)
    status: DecisionConditionStatus
    enforcement_point: DecisionEnforcementPoint
    target: DecisionConditionTarget | None = None
    verification_evidence_types: tuple[StrictStr, ...] = Field(min_length=1)
    expected_risk_effect: StrictStr = Field(min_length=1)
    source_reference_ids: tuple[StrictStr, ...] = Field(min_length=1)
    evidence_ids: tuple[StrictStr, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_candidate_id(self) -> DecisionConditionCandidate:
        expected_id = deterministic_id(
            "DCC",
            self.code,
            self.category,
            self.title,
            self.description,
            self.status,
            self.enforcement_point,
            self.target.model_dump(mode="json") if self.target else None,
            self.verification_evidence_types,
            self.expected_risk_effect,
            self.source_reference_ids,
            self.evidence_ids,
        )
        if self.candidate_id != expected_id:
            raise ValueError("Decision condition candidate_id is unstable")
        return self


def decision_conditions_support_negotiation(
    conditions: tuple[DecisionConditionCandidate, ...],
) -> bool:
    """Return whether exact conditions support negotiation rather than data repair."""

    non_negotiable_evidence_conditions = {
        MARGIN_BENCHMARK_INPUTS_CONDITION_CODE,
        MARGIN_STRATEGY_INPUTS_CONDITION_CODE,
    }
    return bool(conditions) and all(
        item.code not in non_negotiable_evidence_conditions
        for item in conditions
    )


class DecisionScenarioPacket(BaseModel):
    """Canonical deterministic packet and the only input allowed into OpenAI."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    packet_id: StrictStr = Field(min_length=1)
    evaluation_case_id: StrictStr = Field(min_length=1)
    dataset_id: StrictStr = Field(min_length=1)
    contract_id: StrictStr = Field(min_length=1)
    internal_decision_package_id: StrictStr = Field(min_length=1)
    final_risk_assessment_id: StrictStr = Field(min_length=1)
    internal_decision_package_artifact: ExactDecisionArtifactRef
    final_risk_artifact: ExactDecisionArtifactRef
    assembly_path: StrictStr = Field(min_length=1)

    finance_metrics: tuple[DecisionMetricSnapshot, ...] = ()
    operations_metrics: tuple[DecisionMetricSnapshot, ...] = ()
    calculations: tuple[DecisionCalculation, ...] = ()
    banking_options: tuple[DecisionOptionSnapshot, ...] = ()
    allowed_option_combinations: tuple[tuple[StrictStr, ...], ...] = ()
    negotiation_strategy_candidates: tuple[
        DecisionNegotiationStrategyCandidate, ...
    ] = ()

    residual_risk_level: RiskLevel
    final_risk_status: FinalRiskAssessmentStatus
    major_exception_status: MajorExceptionStatus
    residual_findings: tuple[DecisionRiskFindingSnapshot, ...] = ()
    required_controls: tuple[DecisionControlSnapshot, ...] = ()
    limitations: tuple[DecisionLimitationSnapshot, ...] = ()
    document_release_package: DecisionDocumentReleaseSnapshot | None = None

    reason_candidates: tuple[DecisionReasonCandidate, ...] = Field(min_length=1)
    condition_candidates: tuple[DecisionConditionCandidate, ...] = ()
    allowed_recommendations: tuple[DecisionRecommendation, ...] = Field(
        min_length=1
    )
    allowed_numeric_display_values: tuple[StrictStr, ...] = ()
    reference_evidence: tuple[DecisionReferenceEvidence, ...] = Field(min_length=1)
    known_evidence_ids: tuple[StrictStr, ...] = Field(min_length=1)
    excluded_opc_global_finance_fact_count: int = Field(ge=0)
    excluded_opc_global_operations_fact_count: int = Field(ge=0)
    deterministic_calculations_complete: Literal[True] = True

    @model_validator(mode="after")
    def validate_packet(self) -> DecisionScenarioPacket:
        if (
            self.internal_decision_package_artifact.artifact_type
            is not ArtifactType.INTERNAL_DECISION_PACKAGE
            or self.final_risk_artifact.artifact_type
            is not ArtifactType.FINAL_RISK_ASSESSMENT
        ):
            raise ValueError("Decision packet has incorrect upstream artifact types")
        collections = (
            ("Finance fact IDs", tuple(item.fact_id for item in self.finance_metrics)),
            (
                "Finance metric names",
                tuple(item.metric for item in self.finance_metrics),
            ),
            (
                "Operations fact IDs",
                tuple(item.fact_id for item in self.operations_metrics),
            ),
            (
                "Calculation IDs",
                tuple(item.calculation_id for item in self.calculations),
            ),
            ("Banking option IDs", tuple(item.option_id for item in self.banking_options)),
            (
                "Residual finding IDs",
                tuple(item.finding_id for item in self.residual_findings),
            ),
            ("Control IDs", tuple(item.control_id for item in self.required_controls)),
            ("Limitation IDs", tuple(item.limitation_id for item in self.limitations)),
            (
                "Reason candidate IDs",
                tuple(item.candidate_id for item in self.reason_candidates),
            ),
            (
                "Condition candidate IDs",
                tuple(item.candidate_id for item in self.condition_candidates),
            ),
            (
                "Reference IDs",
                tuple(item.reference_id for item in self.reference_evidence),
            ),
            ("Evidence IDs", self.known_evidence_ids),
            ("Numeric displays", self.allowed_numeric_display_values),
            (
                "Allowed recommendations",
                tuple(item.value for item in self.allowed_recommendations),
            ),
            (
                "Negotiation strategy IDs",
                tuple(item.strategy_id for item in self.negotiation_strategy_candidates),
            ),
            (
                "Reason candidate codes",
                tuple(item.code for item in self.reason_candidates),
            ),
            (
                "Condition candidate codes",
                tuple(item.code for item in self.condition_candidates),
            ),
        )
        for label, values in collections:
            if len(set(values)) != len(values):
                raise ValueError(f"Decision packet {label} must be unique")
        known_options = {item.option_id for item in self.banking_options}
        canonical_combinations: set[tuple[str, ...]] = set()
        for combination in self.allowed_option_combinations:
            canonical = tuple(sorted(combination))
            if (
                len(combination) < 2
                or len(set(combination)) != len(combination)
                or not set(combination).issubset(known_options)
                or canonical in canonical_combinations
            ):
                raise ValueError("Decision packet has an invalid option combination")
            canonical_combinations.add(canonical)
        reference_evidence_ids = {
            evidence_id
            for item in self.reference_evidence
            for evidence_id in item.evidence_ids
        }
        if not reference_evidence_ids.issubset(set(self.known_evidence_ids)):
            raise ValueError("Decision references contain unknown evidence")
        known_references = {item.reference_id for item in self.reference_evidence}
        reference_map = {
            item.reference_id: set(item.evidence_ids)
            for item in self.reference_evidence
        }
        for calculation in self.calculations:
            for operand in calculation.operands:
                if operand.source_reference_id not in known_references:
                    raise ValueError(
                        "Decision calculation operand references an unknown source"
                    )
                if not set(operand.evidence_ids).issubset(
                    reference_map[operand.source_reference_id]
                ):
                    raise ValueError(
                        "Decision calculation operand evidence is unrelated to its source"
                    )
        candidate_references = {
            reference_id
            for item in (*self.reason_candidates, *self.condition_candidates)
            for reference_id in item.source_reference_ids
        }
        target_references = {
            reference_id
            for item in self.condition_candidates
            if item.target is not None
            for reference_id in item.target.source_reference_ids
        }
        if not (candidate_references | target_references).issubset(known_references):
            raise ValueError("Decision candidates contain unknown source references")
        for item in (*self.reason_candidates, *self.condition_candidates):
            authorized = {
                evidence_id
                for reference_id in item.source_reference_ids
                for evidence_id in reference_map[reference_id]
            }
            if not set(item.evidence_ids).issubset(authorized):
                raise ValueError("Decision candidate evidence is unrelated to its sources")
        for item in self.condition_candidates:
            if item.target is None:
                continue
            authorized = {
                evidence_id
                for reference_id in item.target.source_reference_ids
                for evidence_id in reference_map[reference_id]
            }
            if not set(item.target.evidence_ids).issubset(authorized):
                raise ValueError("Decision target evidence is unrelated to its sources")
        if DecisionRecommendation.NOT_EVALUABLE not in self.allowed_recommendations:
            raise ValueError("NOT_EVALUABLE must always remain a safe recommendation")
        if (
            DecisionRecommendation.ACCEPT in self.allowed_recommendations
            and (
                self.final_risk_status is not FinalRiskAssessmentStatus.COMPLETE
                or self.major_exception_status is not MajorExceptionStatus.NOT_DETECTED
                or self.residual_findings
                or self.condition_candidates
            )
        ):
            raise ValueError("ACCEPT eligibility contradicts deterministic safety inputs")
        if (
            DecisionRecommendation.NEGOTIATE_CONDITIONS_TO_ACCEPT
            in self.allowed_recommendations
        ) != decision_conditions_support_negotiation(self.condition_candidates):
            raise ValueError("NEGOTIATE eligibility must match condition availability")
        if (
            DecisionRecommendation.DO_NOT_ACCEPT in self.allowed_recommendations
            and self.major_exception_status is not MajorExceptionStatus.DETECTED
        ):
            raise ValueError("DO_NOT_ACCEPT lacks explicit non-viability evidence")
        calculation_map = {
            item.calculation_id: item for item in self.calculations
        }
        calculation_ids = set(calculation_map)
        if any(
            not set(item.calculation_ids).issubset(calculation_ids)
            for item in self.banking_options
        ):
            raise ValueError("Decision option references an unknown calculation")
        condition_map = {item.code: item for item in self.condition_candidates}
        condition_codes = set(condition_map)
        finance_metric_map = {item.fact_id: item for item in self.finance_metrics}
        finance_metrics_by_name = {
            item.metric: item for item in self.finance_metrics
        }
        margin_strategies = tuple(
            item
            for item in self.negotiation_strategy_candidates
            if item.condition_code == MARGIN_NEGOTIATION_CONDITION_CODE
        )
        margin_condition = condition_map.get(MARGIN_NEGOTIATION_CONDITION_CODE)
        missing_strategy_inputs_condition = condition_map.get(
            MARGIN_STRATEGY_INPUTS_CONDITION_CODE
        )
        current_margin_metric = finance_metrics_by_name.get(
            FinanceMetric.ORDER_GROSS_MARGIN.value
        )
        target_margin_metric = finance_metrics_by_name.get(
            FinanceMetric.OPC_TARGET_GROSS_MARGIN.value
        )
        margin_benchmark_inputs_condition = condition_map.get(
            MARGIN_BENCHMARK_INPUTS_CONDITION_CODE
        )
        margin_benchmarks_missing = not (
            decision_current_margin_metric_is_evaluable(current_margin_metric)
            and decision_target_margin_metric_is_evaluable(target_margin_metric)
        )
        if margin_benchmarks_missing != (
            margin_benchmark_inputs_condition is not None
        ):
            raise ValueError(
                "Missing gross-margin benchmarks require a non-evaluable condition"
            )
        if margin_benchmark_inputs_condition is not None:
            available_benchmarks = tuple(
                item
                for item in (current_margin_metric, target_margin_metric)
                if item is not None
            )
            expected_benchmark_sources = tuple(
                item.fact_id for item in available_benchmarks
            ) or (self.internal_decision_package_id,)
            expected_benchmark_evidence = tuple(
                dict.fromkeys(
                    evidence_id
                    for item in available_benchmarks
                    for evidence_id in item.evidence_ids
                )
            ) or self.known_evidence_ids
            if (
                margin_benchmark_inputs_condition.category
                is not DecisionConditionCategory.EVIDENCE
                or margin_benchmark_inputs_condition.title
                != MARGIN_BENCHMARK_INPUTS_CONDITION_TITLE
                or margin_benchmark_inputs_condition.description
                != MARGIN_BENCHMARK_INPUTS_CONDITION_DESCRIPTION
                or margin_benchmark_inputs_condition.status
                is not DecisionConditionStatus.NOT_EVALUABLE
                or margin_benchmark_inputs_condition.enforcement_point
                is not DecisionEnforcementPoint.BEFORE_ACCEPTANCE
                or margin_benchmark_inputs_condition.target is not None
                or margin_benchmark_inputs_condition.verification_evidence_types
                != MARGIN_BENCHMARK_INPUTS_CONDITION_VERIFICATION_EVIDENCE_TYPES
                or margin_benchmark_inputs_condition.expected_risk_effect
                != MARGIN_BENCHMARK_INPUTS_CONDITION_EXPECTED_RISK_EFFECT
                or margin_benchmark_inputs_condition.source_reference_ids
                != expected_benchmark_sources
                or margin_benchmark_inputs_condition.evidence_ids
                != expected_benchmark_evidence
            ):
                raise ValueError(
                    "Gross-margin benchmark evidence condition is not canonical"
                )
        margin_gap_is_explicit = bool(
            not margin_benchmarks_missing
            and current_margin_metric is not None
            and target_margin_metric is not None
            and current_margin_metric.value < target_margin_metric.value
        )
        if (
            margin_condition is not None
            and missing_strategy_inputs_condition is not None
        ):
            raise ValueError("Margin resolution paths are mutually exclusive")
        if margin_gap_is_explicit != (
            (margin_condition is not None)
            ^ (missing_strategy_inputs_condition is not None)
        ):
            raise ValueError(
                "A below-target margin must have exactly one canonical resolution path"
            )
        if missing_strategy_inputs_condition is not None:
            if current_margin_metric is None or target_margin_metric is None:
                raise ValueError(
                    "Missing margin inputs condition lacks authoritative metrics"
                )
            missing_target = missing_strategy_inputs_condition.target
            expected_sources = (
                current_margin_metric.fact_id,
                target_margin_metric.fact_id,
            )
            expected_evidence = tuple(
                dict.fromkeys(
                    (
                        *current_margin_metric.evidence_ids,
                        *target_margin_metric.evidence_ids,
                    )
                )
            )
            if (
                missing_strategy_inputs_condition.category
                is not DecisionConditionCategory.EVIDENCE
                or missing_strategy_inputs_condition.title
                != MARGIN_STRATEGY_INPUTS_CONDITION_TITLE
                or missing_strategy_inputs_condition.description
                != MARGIN_STRATEGY_INPUTS_CONDITION_DESCRIPTION
                or missing_strategy_inputs_condition.status
                is not DecisionConditionStatus.NOT_EVALUABLE
                or missing_strategy_inputs_condition.enforcement_point
                is not DecisionEnforcementPoint.BEFORE_ACCEPTANCE
                or missing_strategy_inputs_condition.verification_evidence_types
                != MARGIN_STRATEGY_INPUTS_CONDITION_VERIFICATION_EVIDENCE_TYPES
                or missing_strategy_inputs_condition.expected_risk_effect
                != MARGIN_STRATEGY_INPUTS_CONDITION_EXPECTED_RISK_EFFECT
                or missing_strategy_inputs_condition.source_reference_ids
                != expected_sources
                or missing_strategy_inputs_condition.evidence_ids
                != expected_evidence
                or missing_target is None
                or missing_target.metric
                != FinanceMetric.ORDER_GROSS_MARGIN.value
                or missing_target.operator
                is not DecisionTargetOperator.GREATER_THAN_OR_EQUAL
                or missing_target.current_value != current_margin_metric.value
                or missing_target.target_value != target_margin_metric.value
                or missing_target.unit != "RATIO"
                or missing_target.currency is not None
                or missing_target.source_reference_ids != expected_sources
                or missing_target.evidence_ids != expected_evidence
                or margin_strategies
            ):
                raise ValueError(
                    "Missing margin strategy inputs condition is not canonical"
                )
        if margin_condition is None:
            if margin_strategies:
                raise ValueError(
                    "Margin strategies require their canonical negotiation condition"
                )
        elif (
            margin_condition.category is not DecisionConditionCategory.COMMERCIAL
            or margin_condition.title != MARGIN_NEGOTIATION_CONDITION_TITLE
            or margin_condition.description
            != MARGIN_NEGOTIATION_CONDITION_DESCRIPTION
            or margin_condition.status is not DecisionConditionStatus.OPEN
            or margin_condition.enforcement_point
            is not DecisionEnforcementPoint.BEFORE_ACCEPTANCE
            or margin_condition.verification_evidence_types
            != MARGIN_NEGOTIATION_CONDITION_VERIFICATION_EVIDENCE_TYPES
            or margin_condition.expected_risk_effect
            != MARGIN_NEGOTIATION_CONDITION_EXPECTED_RISK_EFFECT
            or len(margin_strategies) != len(DecisionNegotiationStrategyType)
            or {item.strategy_type for item in margin_strategies}
            != set(DecisionNegotiationStrategyType)
        ):
            raise ValueError(
                "Margin negotiation condition and strategy set are not canonical"
            )
        margin_calculation_codes = {
            DecisionCalculationCode.MINIMUM_REVENUE_INCREASE_FOR_TARGET_MARGIN,
            DecisionCalculationCode.MINIMUM_COST_REDUCTION_FOR_TARGET_MARGIN,
        }
        margin_calculation_ids = {
            item.calculation_id
            for item in self.calculations
            if item.code in margin_calculation_codes
        }
        if margin_calculation_ids != {
            item.calculation_id for item in margin_strategies
        }:
            raise ValueError(
                "Margin calculations must exactly match the canonical strategy set"
            )
        if any(
            item.condition_code not in condition_codes
            or item.calculation_id not in calculation_ids
            for item in self.negotiation_strategy_candidates
        ):
            raise ValueError(
                "Negotiation strategy references an unknown condition or calculation"
            )
        for strategy in self.negotiation_strategy_candidates:
            if not set(strategy.source_reference_ids).issubset(known_references):
                raise ValueError("Negotiation strategy contains an unknown source reference")
            authorized = {
                evidence_id
                for reference_id in strategy.source_reference_ids
                for evidence_id in reference_map[reference_id]
            }
            if not set(strategy.evidence_ids).issubset(authorized):
                raise ValueError(
                    "Negotiation strategy evidence is unrelated to its sources"
                )
            calculation = calculation_map[strategy.calculation_id]
            expected_code = (
                DecisionCalculationCode.MINIMUM_REVENUE_INCREASE_FOR_TARGET_MARGIN
                if strategy.strategy_type
                is DecisionNegotiationStrategyType.INCREASE_CUSTOMER_PRICE
                else DecisionCalculationCode.MINIMUM_COST_REDUCTION_FOR_TARGET_MARGIN
            )
            expected_formula = (
                "ceil(explicit_order_estimated_cost / "
                "(1 - opc_target_gross_margin)) - explicit_order_revenue"
                if strategy.strategy_type
                is DecisionNegotiationStrategyType.INCREASE_CUSTOMER_PRICE
                else "explicit_order_estimated_cost - "
                "floor(explicit_order_revenue * (1 - opc_target_gross_margin))"
            )
            if (
                calculation.code is not expected_code
                or calculation.formula != expected_formula
                or calculation.result_value != strategy.required_adjustment_value
                or calculation.result_unit != CurrencyCode.VND.value
                or calculation.evidence_ids != strategy.evidence_ids
                or tuple(
                    operand.source_reference_id
                    for operand in calculation.operands
                )
                != strategy.source_reference_ids
            ):
                raise ValueError(
                    "Negotiation strategy is inconsistent with its exact calculation"
                )
            operands_by_label = {
                operand.label: operand for operand in calculation.operands
            }
            if set(operands_by_label) != {
                "explicit_order_revenue",
                "explicit_order_estimated_cost",
                "opc_target_gross_margin",
            }:
                raise ValueError(
                    "Margin strategy calculation has unexpected operands"
                )
            revenue_operand = operands_by_label["explicit_order_revenue"]
            cost_operand = operands_by_label["explicit_order_estimated_cost"]
            target_operand = operands_by_label["opc_target_gross_margin"]
            if (
                revenue_operand.value != strategy.baseline_revenue
                or revenue_operand.unit != CurrencyCode.VND.value
                or cost_operand.value != strategy.baseline_cost
                or cost_operand.unit != CurrencyCode.VND.value
                or target_operand.value != strategy.target_margin
                or target_operand.unit != "RATIO"
            ):
                raise ValueError(
                    "Margin strategy operands do not match its baseline and target"
                )
            revenue_metric = finance_metric_map.get(
                revenue_operand.source_reference_id
            )
            cost_metric = finance_metric_map.get(cost_operand.source_reference_id)
            if (
                revenue_metric is None
                or revenue_metric.metric != FinanceMetric.ORDER_REVENUE_TOTAL.value
                or revenue_metric.role is not DecisionMetricRole.CASE_FACT
                or not revenue_metric.contract_attributable
                or revenue_metric.unit != CurrencyCode.VND.value
                or revenue_metric.value != revenue_operand.value
                or revenue_metric.evidence_ids != revenue_operand.evidence_ids
                or cost_metric is None
                or cost_metric.metric
                != FinanceMetric.ORDER_ESTIMATED_COST_TOTAL.value
                or cost_metric.role is not DecisionMetricRole.CASE_FACT
                or not cost_metric.contract_attributable
                or cost_metric.unit != CurrencyCode.VND.value
                or cost_metric.value != cost_operand.value
                or cost_metric.evidence_ids != cost_operand.evidence_ids
            ):
                raise ValueError(
                    "Margin strategy baseline is not bound to its Finance metrics"
                )
            condition = condition_map[strategy.condition_code]
            condition_target = condition.target
            if (
                condition_target is None
                or condition_target.metric != FinanceMetric.ORDER_GROSS_MARGIN.value
                or condition_target.operator
                is not DecisionTargetOperator.GREATER_THAN_OR_EQUAL
                or condition_target.unit != "RATIO"
                or condition_target.currency is not None
                or condition_target.target_value != strategy.target_margin
            ):
                raise ValueError(
                    "Margin strategy target is inconsistent with its condition"
                )
            current_margin_metrics = tuple(
                item
                for reference_id in condition_target.source_reference_ids
                if (
                    (item := finance_metric_map.get(reference_id)) is not None
                    and item.metric == FinanceMetric.ORDER_GROSS_MARGIN.value
                )
            )
            target_margin_metric = finance_metric_map.get(
                target_operand.source_reference_id
            )
            if (
                len(current_margin_metrics) != 1
                or target_margin_metric is None
                or target_margin_metric.metric
                != FinanceMetric.OPC_TARGET_GROSS_MARGIN.value
                or target_margin_metric.role is not DecisionMetricRole.POLICY_TARGET
                or target_margin_metric.contract_attributable
                or target_margin_metric.unit != "RATIO"
                or target_margin_metric.value != strategy.target_margin
            ):
                raise ValueError(
                    "Margin strategy is not bound to authoritative Finance metrics"
                )
            current_margin_metric = current_margin_metrics[0]
            expected_target_sources = (
                current_margin_metric.fact_id,
                target_margin_metric.fact_id,
            )
            expected_target_evidence = tuple(
                dict.fromkeys(
                    (
                        *current_margin_metric.evidence_ids,
                        *target_margin_metric.evidence_ids,
                    )
                )
            )
            if (
                current_margin_metric.role is not DecisionMetricRole.CASE_FACT
                or not current_margin_metric.contract_attributable
                or current_margin_metric.unit != "RATIO"
                or isinstance(current_margin_metric.value, bool)
                or not isinstance(current_margin_metric.value, (int, float))
                or condition_target.current_value != current_margin_metric.value
                or condition_target.source_reference_ids != expected_target_sources
                or condition_target.evidence_ids != expected_target_evidence
                or condition.source_reference_ids != expected_target_sources
                or condition.evidence_ids != expected_target_evidence
                or target_operand.source_reference_id != target_margin_metric.fact_id
                or target_operand.evidence_ids != target_margin_metric.evidence_ids
            ):
                raise ValueError(
                    "Margin condition is not exactly bound to its Finance facts"
                )
            revenue_value = Decimal(strategy.baseline_revenue)
            cost_value = Decimal(strategy.baseline_cost)
            target_value = Decimal(str(strategy.target_margin))
            current_margin_value = Decimal(str(current_margin_metric.value))
            calculated_current_margin = (
                revenue_value - cost_value
            ) / revenue_value
            if abs(current_margin_value - calculated_current_margin) > Decimal(
                "0.000000000001"
            ):
                raise ValueError(
                    "Margin condition current value contradicts its baseline"
                )
            if (
                strategy.strategy_type
                is DecisionNegotiationStrategyType.INCREASE_CUSTOMER_PRICE
            ):
                exact_minimum = int(
                    (
                        cost_value / (Decimal("1") - target_value)
                    ).to_integral_value(rounding=ROUND_CEILING)
                ) - strategy.baseline_revenue
            else:
                exact_minimum = strategy.baseline_cost - int(
                    (
                        revenue_value * (Decimal("1") - target_value)
                    ).to_integral_value(rounding=ROUND_FLOOR)
                )
            if strategy.required_adjustment_value != exact_minimum:
                raise ValueError(
                    "Negotiation strategy adjustment is not the exact minimum"
                )
        expected_id = decision_scenario_packet_id(self)
        if self.packet_id != expected_id:
            raise ValueError("Decision scenario packet_id is unstable")
        return self


class AIDecisionReasonDraft(BaseModel):
    """Untrusted model reason before stable identity is attached."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    code: StrictStr = Field(min_length=1)
    title: StrictStr = Field(min_length=1)
    detail: StrictStr = Field(min_length=1)
    source_reference_ids: tuple[StrictStr, ...] = Field(min_length=1)
    evidence_ids: tuple[StrictStr, ...] = Field(min_length=1)


class NegotiationConditionDraft(BaseModel):
    """Untrusted proposed condition limited to packet references and targets."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    code: StrictStr = Field(min_length=1)
    category: DecisionConditionCategory
    title: StrictStr = Field(min_length=1)
    description: StrictStr = Field(min_length=1)
    status: DecisionConditionStatus
    enforcement_point: DecisionEnforcementPoint
    target: DecisionConditionTarget | None = None
    verification_evidence_types: tuple[StrictStr, ...] = Field(min_length=1)
    expected_risk_effect: StrictStr = Field(min_length=1)
    source_reference_ids: tuple[StrictStr, ...] = Field(min_length=1)
    evidence_ids: tuple[StrictStr, ...] = Field(min_length=1)


class AIDecisionAttentionPointDraft(BaseModel):
    """Founder-facing point that cites exact packet evidence."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    code: StrictStr = Field(min_length=1)
    text: StrictStr = Field(min_length=1)
    source_reference_ids: tuple[StrictStr, ...] = Field(min_length=1)
    evidence_ids: tuple[StrictStr, ...] = Field(min_length=1)


class AIDecisionProposalDraft(BaseModel):
    """Structured OpenAI proposal; still untrusted and never an approval."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    recommendation: DecisionRecommendation
    executive_summary: StrictStr = Field(min_length=1)
    reasons: tuple[AIDecisionReasonDraft, ...] = Field(min_length=1)
    conditions: tuple[NegotiationConditionDraft, ...] = ()
    selected_negotiation_strategy_ids: tuple[StrictStr, ...] = ()
    selected_option_ids: tuple[StrictStr, ...] = ()
    confidence: DecisionConfidence
    human_attention_points: tuple[AIDecisionAttentionPointDraft, ...] = ()
    calculations_performed_by_model: Literal[False] = False


class AIDecisionComposition(BaseModel):
    """Port result with model provenance and exact deterministic input hash."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    proposal: AIDecisionProposalDraft
    source: DecisionAnalysisSource
    model: StrictStr = Field(min_length=1)
    prompt_version: StrictStr = Field(min_length=1)
    input_hash: StrictStr = Field(min_length=1)
    fallback_reason: StrictStr | None = None

    @model_validator(mode="after")
    def validate_source(self) -> AIDecisionComposition:
        if (self.source is DecisionAnalysisSource.DETERMINISTIC_FALLBACK) != (
            self.fallback_reason is not None
        ):
            raise ValueError("Only deterministic fallback composition carries a reason")
        if (
            self.source is DecisionAnalysisSource.DETERMINISTIC_FALLBACK
            and self.proposal.recommendation is not DecisionRecommendation.NOT_EVALUABLE
        ):
            raise ValueError(
                "Deterministic fallback cannot produce an AI business recommendation"
            )
        return self


class DecisionReason(AIDecisionReasonDraft):
    """Guarded reason with stable identity."""

    reason_id: StrictStr = Field(min_length=1)


class NegotiationCondition(NegotiationConditionDraft):
    """Guarded condition with stable identity."""

    condition_id: StrictStr = Field(min_length=1)


class DecisionHumanAttentionPoint(AIDecisionAttentionPointDraft):
    """Guarded Founder-attention point with stable identity."""

    attention_point_id: StrictStr = Field(min_length=1)


class AIDecisionAnalysis(BaseModel):
    """Canonical guarded AI proposal, still not the Founder's final decision."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    analysis_id: StrictStr = Field(min_length=1)
    packet_id: StrictStr = Field(min_length=1)
    evaluation_case_id: StrictStr = Field(min_length=1)
    dataset_id: StrictStr = Field(min_length=1)
    contract_id: StrictStr = Field(min_length=1)
    internal_decision_package_artifact: ExactDecisionArtifactRef
    final_risk_artifact: ExactDecisionArtifactRef
    recommendation: DecisionRecommendation
    executive_summary: StrictStr = Field(min_length=1)
    reasons: tuple[DecisionReason, ...] = Field(min_length=1)
    conditions: tuple[NegotiationCondition, ...] = ()
    selected_negotiation_strategy_ids: tuple[StrictStr, ...] = ()
    selected_negotiation_strategies: tuple[
        DecisionNegotiationStrategyCandidate, ...
    ] = ()
    selected_option_ids: tuple[StrictStr, ...] = ()
    confidence: DecisionConfidence
    human_attention_points: tuple[DecisionHumanAttentionPoint, ...] = ()
    source: DecisionAnalysisSource
    model: StrictStr = Field(min_length=1)
    prompt_version: StrictStr = Field(min_length=1)
    input_hash: StrictStr = Field(min_length=1)
    fallback_reason: StrictStr | None = None
    evidence_ids: tuple[StrictStr, ...] = Field(min_length=1)
    deterministic_guard_passed: Literal[True] = True
    calculations_performed_by_model: Literal[False] = False
    approval_requested: Literal[False] = False
    external_action_performed: Literal[False] = False

    @model_validator(mode="after")
    def validate_analysis_identity(self) -> AIDecisionAnalysis:
        if (
            self.source is DecisionAnalysisSource.DETERMINISTIC_FALLBACK
            and self.recommendation is not DecisionRecommendation.NOT_EVALUABLE
        ):
            raise ValueError(
                "Only an OpenAI analysis may carry an evaluable recommendation"
            )
        if self.selected_negotiation_strategy_ids != tuple(
            item.strategy_id for item in self.selected_negotiation_strategies
        ):
            raise ValueError(
                "AI Decision selected negotiation strategy index is inconsistent"
            )
        selected_condition_codes = {item.code for item in self.conditions}
        if any(
            item.condition_code not in selected_condition_codes
            for item in self.selected_negotiation_strategies
        ):
            raise ValueError(
                "AI Decision strategy is unrelated to its selected conditions"
            )
        expected_id = ai_decision_analysis_id(
            packet_id=self.packet_id,
            recommendation=self.recommendation,
            executive_summary=self.executive_summary,
            reasons=self.reasons,
            conditions=self.conditions,
            selected_negotiation_strategy_ids=(
                self.selected_negotiation_strategy_ids
            ),
            selected_option_ids=self.selected_option_ids,
            confidence=self.confidence,
            human_attention_points=self.human_attention_points,
            source=self.source,
            model=self.model,
            prompt_version=self.prompt_version,
            input_hash=self.input_hash,
        )
        if self.analysis_id != expected_id:
            raise ValueError("AI Decision analysis_id is unstable")
        return self


class DecisionCard(BaseModel):
    """Detailed evidence-bound proposal shown to Founder before approval."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    decision_card_id: StrictStr = Field(min_length=1)
    evaluation_case_id: StrictStr = Field(min_length=1)
    dataset_id: StrictStr = Field(min_length=1)
    contract_id: StrictStr = Field(min_length=1)
    ai_analysis_id: StrictStr = Field(min_length=1)
    ai_analysis_artifact: ExactDecisionArtifactRef
    internal_decision_package_artifact: ExactDecisionArtifactRef
    final_risk_artifact: ExactDecisionArtifactRef
    recommendation: DecisionRecommendation
    executive_summary: StrictStr = Field(min_length=1)
    reasons: tuple[DecisionReason, ...] = Field(min_length=1)
    conditions: tuple[NegotiationCondition, ...] = ()
    selected_negotiation_strategy_ids: tuple[StrictStr, ...] = ()
    selected_negotiation_strategies: tuple[
        DecisionNegotiationStrategyCandidate, ...
    ] = ()
    confidence: DecisionConfidence
    selected_option_ids: tuple[StrictStr, ...] = ()
    selected_options: tuple[DecisionOptionSnapshot, ...] = ()
    finance_metrics: tuple[DecisionMetricSnapshot, ...] = ()
    operations_metrics: tuple[DecisionMetricSnapshot, ...] = ()
    calculations: tuple[DecisionCalculation, ...] = ()
    residual_risk_level: RiskLevel
    major_exception_status: MajorExceptionStatus
    residual_findings: tuple[DecisionRiskFindingSnapshot, ...] = ()
    required_controls: tuple[DecisionControlSnapshot, ...] = ()
    limitations: tuple[DecisionLimitationSnapshot, ...] = ()
    human_attention_points: tuple[DecisionHumanAttentionPoint, ...] = ()
    document_release_package: DecisionDocumentReleaseSnapshot | None = None
    evidence_ids: tuple[StrictStr, ...] = Field(min_length=1)
    founder_decision_recorded: Literal[False] = False
    approval_requested: Literal[False] = False
    document_release_authorized: Literal[False] = False
    external_action_performed: Literal[False] = False

    @model_validator(mode="after")
    def validate_card(self) -> DecisionCard:
        if self.ai_analysis_artifact.artifact_type is not ArtifactType.AI_DECISION_ANALYSIS:
            raise ValueError("Decision Card must bind an AI Decision Analysis artifact")
        if self.selected_option_ids != tuple(
            item.option_id for item in self.selected_options
        ):
            raise ValueError("Decision Card selected option index is inconsistent")
        if self.selected_negotiation_strategy_ids != tuple(
            item.strategy_id for item in self.selected_negotiation_strategies
        ):
            raise ValueError(
                "Decision Card selected negotiation strategy index is inconsistent"
            )
        selected_condition_codes = {item.code for item in self.conditions}
        if any(
            item.condition_code not in selected_condition_codes
            for item in self.selected_negotiation_strategies
        ):
            raise ValueError(
                "Decision Card strategy is unrelated to its selected conditions"
            )
        expected_id = decision_card_id(self)
        if self.decision_card_id != expected_id:
            raise ValueError("Decision Card identity is unstable")
        return self


class DecisionAnalysisComponentResult(ComponentResult):
    """Side-effect-free Decision analysis result containing at most one draft."""

    scenario_packet: DecisionScenarioPacket | None = None
    analysis: AIDecisionAnalysis | None = None


class DecisionCardComponentResult(ComponentResult):
    """Side-effect-free Decision Card assembly result."""

    decision_card: DecisionCard | None = None


class DecisionAnalysisExecutionResult(BaseModel):
    """Validated Decision analysis result returned by workflow boundaries."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: WorkflowStatus
    component_status: ComponentStatus
    current_node: StrictStr = Field(min_length=1)
    scenario_packet: DecisionScenarioPacket | None = None
    analysis: AIDecisionAnalysis | None = None
    generated_artifacts: tuple[ArtifactEnvelope, ...] = ()
    validation_reports: tuple[ValidationReport, ...] = ()
    validation_errors: tuple[StrictStr, ...] = ()
    missing_data_requests: tuple[MissingDataRequest, ...] = ()
    warnings: tuple[StrictStr, ...] = ()
    runtime_events: tuple[dict[str, Any], ...] = ()


class DecisionCardExecutionResult(BaseModel):
    """Validated Decision Card result returned by workflow boundaries."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: WorkflowStatus
    component_status: ComponentStatus
    current_node: StrictStr = Field(min_length=1)
    decision_card: DecisionCard | None = None
    generated_artifacts: tuple[ArtifactEnvelope, ...] = ()
    validation_reports: tuple[ValidationReport, ...] = ()
    validation_errors: tuple[StrictStr, ...] = ()
    missing_data_requests: tuple[MissingDataRequest, ...] = ()
    warnings: tuple[StrictStr, ...] = ()
    runtime_events: tuple[dict[str, Any], ...] = ()


def decision_scenario_packet_id(packet: DecisionScenarioPacket) -> str:
    """Build packet identity without its self-referential ID."""

    payload = packet.model_dump(mode="json", exclude={"packet_id"})
    return deterministic_id("DSP", payload)


def decision_packet_input_hash(packet: DecisionScenarioPacket) -> str:
    """Canonical input hash shared with the AI composer port."""

    return deterministic_id("DIN", packet.model_dump(mode="json"))


def ai_decision_analysis_id(
    *,
    packet_id: str,
    recommendation: DecisionRecommendation,
    executive_summary: str,
    reasons: tuple[DecisionReason, ...],
    conditions: tuple[NegotiationCondition, ...],
    selected_negotiation_strategy_ids: tuple[str, ...],
    selected_option_ids: tuple[str, ...],
    confidence: DecisionConfidence,
    human_attention_points: tuple[DecisionHumanAttentionPoint, ...],
    source: DecisionAnalysisSource,
    model: str,
    prompt_version: str,
    input_hash: str,
) -> str:
    """Build stable analysis identity from exact inputs and guarded output."""

    return deterministic_id(
        "AIDA",
        packet_id,
        recommendation,
        executive_summary,
        tuple(item.model_dump(mode="json") for item in reasons),
        tuple(item.model_dump(mode="json") for item in conditions),
        selected_negotiation_strategy_ids,
        selected_option_ids,
        confidence,
        tuple(item.model_dump(mode="json") for item in human_attention_points),
        source,
        model,
        prompt_version,
        input_hash,
    )


def decision_card_id(card: DecisionCard) -> str:
    """Build exact Card identity without runtime IDs, timestamps, or approval state."""

    payload: dict[str, Any] = card.model_dump(
        mode="json",
        exclude={"decision_card_id"},
    )
    return deterministic_id("DCARD", payload)
