"""Safely parse and evaluate the finite initial Risk rule vocabulary."""

import re
from numbers import Real
from typing import NamedTuple

from opc_mis.business.agents.risk.context_loader import RiskContext
from opc_mis.domain.enums import (
    FinanceMetric,
    RiskDependency,
    RiskScope,
    RuleEvaluationStatus,
    RuleOperator,
)
from opc_mis.domain.evidence import EvidenceRef
from opc_mis.domain.lineage import LineageFactory, deterministic_id
from opc_mis.domain.risk_models import (
    RiskRuleDependency,
    RiskSourceRule,
    RuleEvaluation,
)
from opc_mis.domain.team_pack import SheetRegistry

_CONDITION_PATTERN = re.compile(
    r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*(>=|<=|=|>|<)\s*"
    r"(true|false|-?\d+(?:\.\d+)?|[A-Za-z_][A-Za-z0-9_]*)\s*$",
    re.IGNORECASE,
)
_OPERATORS = {
    ">=": RuleOperator.GREATER_THAN_OR_EQUAL,
    "<=": RuleOperator.LESS_THAN_OR_EQUAL,
    ">": RuleOperator.GREATER_THAN,
    "<": RuleOperator.LESS_THAN,
    "=": RuleOperator.EQUAL,
}
_EVENT_FIELDS = {"document_sent_to_partner", "requested_amount", "confidence_score"}


class ParsedCondition(NamedTuple):
    """Small immutable parsed form that cannot execute source text."""

    field: str
    operator: RuleOperator
    threshold: bool | int | float | str


def parse_condition(condition: str) -> ParsedCondition | None:
    """Parse one comparison only; arbitrary expressions are rejected."""
    match = _CONDITION_PATTERN.fullmatch(condition)
    if match is None:
        return None
    field, raw_operator, raw_threshold = match.groups()
    normalized = raw_threshold.casefold()
    if normalized in {"true", "false"}:
        threshold: bool | int | float | str = normalized == "true"
    elif "." in raw_threshold:
        threshold = float(raw_threshold)
    elif raw_threshold.lstrip("-").isdigit():
        threshold = int(raw_threshold)
    else:
        threshold = raw_threshold
    return ParsedCondition(field, _OPERATORS[raw_operator], threshold)


def rule_dependency(rule: RiskSourceRule) -> RiskRuleDependency:
    """Describe dependency gates separately from whether a rule is applicable."""
    parsed = parse_condition(rule.declared_condition)
    field = parsed.field if parsed is not None else None
    if field in {"gross_margin", "closing_cash"}:
        dependencies = (RiskDependency.FINANCE_FACTS,)
    elif field == "delivery_delay_days":
        dependencies = (RiskDependency.OPERATIONS_FACTS,)
    else:
        dependencies = ()
    return RiskRuleDependency(rule_id=rule.rule_id, dependencies=dependencies)


class TypedRiskRuleEngine:
    """Evaluate only explicit source fields with audited, typed mappings."""

    def evaluate(
        self,
        context: RiskContext,
        rules: tuple[RiskSourceRule, ...],
        lineage: LineageFactory,
    ) -> tuple[tuple[RuleEvaluation, ...], tuple[EvidenceRef, ...]]:
        evidence: dict[str, EvidenceRef] = {}
        evaluations = tuple(
            self._evaluate_rule(context, rule, lineage, evidence) for rule in rules
        )
        return evaluations, tuple(evidence[key] for key in sorted(evidence))

    def _evaluate_rule(
        self,
        context: RiskContext,
        rule: RiskSourceRule,
        lineage: LineageFactory,
        evidence: dict[str, EvidenceRef],
    ) -> RuleEvaluation:
        parsed = parse_condition(rule.declared_condition)
        if parsed is None:
            return self._result(
                rule,
                context.evaluation_case.evaluation_case_id,
                RiskScope.EVENT_SPECIFIC,
                RuleEvaluationStatus.NOT_EVALUABLE,
                None,
                None,
                None,
                (),
                rule.evidence_ids,
                "Condition is outside the whitelisted single-comparison grammar.",
            )
        if parsed.field in _EVENT_FIELDS:
            return self._result(
                rule,
                context.evaluation_case.evaluation_case_id,
                RiskScope.EVENT_SPECIFIC,
                RuleEvaluationStatus.NOT_APPLICABLE,
                parsed,
                None,
                None,
                (),
                rule.evidence_ids,
                "This event-specific rule is outside the initial contract Risk scan.",
            )
        if parsed.field == "transaction_risk_score":
            return self._transaction_rule(context, rule, parsed, lineage, evidence)
        if parsed.field == "gross_margin":
            return self._finance_margin_rule(context, rule, parsed)
        if parsed.field == "closing_cash":
            return self._result(
                rule,
                context.evaluation_case.evaluation_case_id,
                RiskScope.OPC_GLOBAL,
                RuleEvaluationStatus.NOT_EVALUABLE,
                parsed,
                None,
                None,
                (),
                rule.evidence_ids,
                "No exact closing_cash fact exists; projected_closing_cash is not "
                "silently aliased.",
            )
        if parsed.field == "delivery_delay_days":
            return self._result(
                rule,
                context.evaluation_case.evaluation_case_id,
                RiskScope.CASE_SPECIFIC,
                RuleEvaluationStatus.NOT_EVALUABLE,
                parsed,
                None,
                None,
                (),
                rule.evidence_ids,
                "Operations has planned/past-due evidence but no exact delivery_delay_days fact.",
            )
        return self._result(
            rule,
            context.evaluation_case.evaluation_case_id,
            RiskScope.EVENT_SPECIFIC,
            RuleEvaluationStatus.NOT_EVALUABLE,
            parsed,
            None,
            None,
            (),
            rule.evidence_ids,
            f"No typed source mapping is registered for {parsed.field}.",
        )

    def _transaction_rule(
        self,
        context: RiskContext,
        rule: RiskSourceRule,
        parsed: ParsedCondition,
        lineage: LineageFactory,
        evidence: dict[str, EvidenceRef],
    ) -> RuleEvaluation:
        values: list[tuple[float, EvidenceRef]] = []
        for record in context.dataset.records(SheetRegistry.BANK_TRANSACTIONS):
            value = record.values.get("transaction_risk_score")
            if isinstance(value, bool) or not isinstance(value, Real):
                continue
            ref = lineage.record_field(record, "transaction_risk_score")
            evidence[ref.evidence_id] = ref
            values.append((float(value), ref))
        if not values:
            return self._result(
                rule,
                context.evaluation_case.evaluation_case_id,
                RiskScope.OPC_GLOBAL,
                RuleEvaluationStatus.NOT_EVALUABLE,
                parsed,
                None,
                None,
                (),
                rule.evidence_ids,
                "No numeric transaction_risk_score values are available.",
            )
        actual = max(item[0] for item in values)
        triggered = self._compare(actual, parsed.operator, parsed.threshold)
        evidence_ids = (*rule.evidence_ids, *(item[1].evidence_id for item in values))
        return self._result(
            rule,
            context.evaluation_case.evaluation_case_id,
            RiskScope.OPC_GLOBAL,
            RuleEvaluationStatus.TRIGGERED if triggered else RuleEvaluationStatus.NOT_TRIGGERED,
            parsed,
            actual,
            None,
            (),
            tuple(dict.fromkeys(evidence_ids)),
            "Evaluated across transaction records at OPC scope; no contract link was inferred.",
        )

    def _finance_margin_rule(
        self,
        context: RiskContext,
        rule: RiskSourceRule,
        parsed: ParsedCondition,
    ) -> RuleEvaluation:
        if context.finance_facts is None:
            return self._result(
                rule,
                context.evaluation_case.evaluation_case_id,
                RiskScope.CASE_SPECIFIC,
                RuleEvaluationStatus.NOT_EVALUABLE,
                parsed,
                None,
                None,
                (),
                rule.evidence_ids,
                "FINANCE_FACTS has not arrived yet.",
            )
        matches = tuple(
            fact
            for fact in context.finance_facts.facts
            if fact.metric is FinanceMetric.CONTRACT_GROSS_MARGIN_SOURCE
        )
        if len(matches) != 1 or isinstance(matches[0].value, bool) or not isinstance(
            matches[0].value, Real
        ):
            return self._result(
                rule,
                context.evaluation_case.evaluation_case_id,
                RiskScope.CASE_SPECIFIC,
                RuleEvaluationStatus.NOT_EVALUABLE,
                parsed,
                None,
                None,
                (),
                rule.evidence_ids,
                "An exact numeric contract gross-margin fact is unavailable.",
            )
        fact = matches[0]
        actual = float(fact.value)
        triggered = self._compare(actual, parsed.operator, parsed.threshold)
        return self._result(
            rule,
            context.evaluation_case.evaluation_case_id,
            RiskScope.CASE_SPECIFIC,
            RuleEvaluationStatus.TRIGGERED if triggered else RuleEvaluationStatus.NOT_TRIGGERED,
            parsed,
            actual,
            fact.fact_id,
            (fact.fact_id,),
            tuple(dict.fromkeys((*rule.evidence_ids, fact.evidence_id))),
            "Evaluated from the verified contract source-margin Finance fact.",
        )

    @staticmethod
    def _compare(actual: object, operator: RuleOperator, threshold: object) -> bool:
        if operator is RuleOperator.EQUAL:
            return actual == threshold
        if isinstance(actual, bool) or isinstance(threshold, bool):
            return False
        if not isinstance(actual, Real) or not isinstance(threshold, Real):
            return False
        if operator is RuleOperator.GREATER_THAN_OR_EQUAL:
            return actual >= threshold
        if operator is RuleOperator.LESS_THAN_OR_EQUAL:
            return actual <= threshold
        if operator is RuleOperator.GREATER_THAN:
            return actual > threshold
        return actual < threshold

    @staticmethod
    def _result(
        rule: RiskSourceRule,
        evaluation_case_id: str,
        scope: RiskScope,
        status: RuleEvaluationStatus,
        parsed: ParsedCondition | None,
        actual: object,
        source_fact_id: str | None,
        source_fact_ids: tuple[str, ...],
        evidence_ids: tuple[str, ...],
        explanation: str,
    ) -> RuleEvaluation:
        return RuleEvaluation(
            evaluation_id=deterministic_id(
                "RRE",
                evaluation_case_id,
                rule.rule_id,
                scope,
                status,
                actual,
                source_fact_id,
                evidence_ids,
            ),
            rule_id=rule.rule_id,
            risk_type=rule.risk_type,
            declared_condition=rule.declared_condition,
            applicability_scope=scope,
            status=status,
            severity=rule.severity,
            source_field=parsed.field if parsed is not None else None,
            operator=parsed.operator if parsed is not None else None,
            threshold=parsed.threshold if parsed is not None else None,
            actual_value=actual,  # type: ignore[arg-type]
            source_fact_ids=source_fact_ids,
            evidence_ids=evidence_ids,
            explanation=explanation,
        )
