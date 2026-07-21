"""Deterministic boundary checks for model-composed Finance text."""

import re
from decimal import ROUND_HALF_UP, Decimal

from opc_mis.domain.enums import FinanceUnit
from opc_mis.domain.finance_models import FinanceComposerInput, FinanceFact, FinanceNarrative

FORBIDDEN_TERMS = (
    "risk",
    "rủi ro",
    "severity",
    "approval",
    "phê duyệt",
    "risk score",
    "risk level",
    "ngân hàng",
    "banking",
    "khoản vay",
    "tín dụng",
    "rr-",
)


def _decimal_text(value: Decimal, places: Decimal) -> str:
    rounded = value.quantize(places, rounding=ROUND_HALF_UP)
    text = format(rounded, "f").rstrip("0").rstrip(".")
    return text.replace(".", ",")


def founder_display_value(fact: FinanceFact) -> str:
    """Format a verified fact once so OpenAI never owns numeric presentation logic."""
    value = fact.value
    if value is None:
        return "không có dữ liệu"
    if fact.unit is FinanceUnit.VND and isinstance(value, (int, float)):
        amount = Decimal(str(value))
        absolute = abs(amount)
        if absolute >= Decimal("1000000000"):
            return f"{_decimal_text(amount / Decimal('1000000000'), Decimal('0.001'))} tỷ đồng"
        if absolute >= Decimal("1000000"):
            return f"{_decimal_text(amount / Decimal('1000000'), Decimal('0.001'))} triệu đồng"
        grouped = f"{int(amount):,}".replace(",", ".")
        return f"{grouped} đồng"
    if fact.unit is FinanceUnit.RATIO and isinstance(value, (int, float)):
        percent = Decimal(str(value)) * Decimal("100")
        return f"{_decimal_text(percent, Decimal('0.01'))}%"
    if fact.unit is FinanceUnit.COUNT and isinstance(value, (int, float)):
        return _decimal_text(Decimal(str(value)), Decimal("0.01"))
    if fact.unit is FinanceUnit.BOOLEAN and isinstance(value, bool):
        return "có" if value else "không"
    return str(value)


def validate_narrative(narrative: FinanceNarrative, payload: FinanceComposerInput) -> None:
    """Reject unverified displays, unknown facts, and downstream responsibilities."""
    known_facts = {fact.fact_id: fact for fact in payload.facts}
    texts = (narrative.headline, *(item.text for item in narrative.statements))
    for text in texts:
        normalized = text.casefold()
        if any(term in normalized for term in FORBIDDEN_TERMS):
            raise ValueError("Finance narrative crossed a downstream responsibility boundary.")
    if re.search(r"\d", narrative.headline):
        raise ValueError("Finance narrative headline must not contain numeric text.")
    if not narrative.statements:
        raise ValueError("Finance narrative must contain at least one cited statement.")
    for statement in narrative.statements:
        if not statement.fact_ids or not set(statement.fact_ids).issubset(known_facts):
            raise ValueError("Finance narrative contains unknown or missing fact references.")
        remaining = statement.text
        allowed_displays = sorted(
            {
                founder_display_value(known_facts[fact_id])
                for fact_id in statement.fact_ids
                if re.search(r"\d", founder_display_value(known_facts[fact_id]))
            },
            key=len,
            reverse=True,
        )
        for display in allowed_displays:
            remaining = remaining.replace(display, "")
        if re.search(r"\d", remaining):
            raise ValueError(
                "Finance narrative contains a numeric display not backed by a cited fact."
            )
