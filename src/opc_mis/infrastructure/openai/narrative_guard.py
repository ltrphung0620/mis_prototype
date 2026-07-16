"""Deterministic boundary checks for model-composed Finance text."""

import re

from opc_mis.domain.finance_models import FinanceComposerInput, FinanceNarrative

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


def validate_narrative(narrative: FinanceNarrative, payload: FinanceComposerInput) -> None:
    """Reject unsupported numbers, unknown facts, and downstream responsibilities."""
    known_facts = {fact.fact_id for fact in payload.facts}
    texts = (narrative.headline, *(item.text for item in narrative.statements))
    for text in texts:
        normalized = text.casefold()
        if re.search(r"\d", text):
            raise ValueError("Finance narrative must not introduce numeric text.")
        if any(term in normalized for term in FORBIDDEN_TERMS):
            raise ValueError("Finance narrative crossed a downstream responsibility boundary.")
    if not narrative.statements:
        raise ValueError("Finance narrative must contain at least one cited statement.")
    for statement in narrative.statements:
        if not statement.fact_ids or not set(statement.fact_ids).issubset(known_facts):
            raise ValueError("Finance narrative contains unknown or missing fact references.")
