"""Deterministic boundary checks for model-composed Banking option advice."""

import re

from opc_mis.domain.banking_models import BankingAdvisorInput, BankingOptionAdviceDraft

FORBIDDEN_TERMS = (
    "approval",
    "approved",
    "approve",
    "authorization",
    "authorized",
    "phê duyệt",
    "chấp thuận",
    "submission",
    "submitted",
    "submit",
    "gửi hồ sơ",
    "gửi ngân hàng",
    "final decision",
    "decided",
    "decision made",
    "quyết định cuối cùng",
    "đã quyết định",
    "selected",
    "has been selected",
    "đã chọn",
    "được chọn",
    "precheck passed",
    "precheck succeeded",
    "precheck successful",
    "precheck approved",
    "kiểm tra sơ bộ thành công",
    "đủ điều kiện ngân hàng",
)


def _canonical_option_set(option_ids: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(sorted(option_ids))


def _validate_prose(text: str, known_option_ids: frozenset[str]) -> None:
    normalized = text.casefold()
    if any(term in normalized for term in FORBIDDEN_TERMS):
        raise ValueError("Banking advice crossed a decision, approval, or execution boundary.")

    without_option_ids = text
    for option_id in sorted(known_option_ids, key=len, reverse=True):
        without_option_ids = without_option_ids.replace(option_id, "")
    if re.search(r"\d", without_option_ids):
        raise ValueError("Banking advice contains numeric prose outside a known option ID.")


def validate_banking_advice(
    advice: BankingOptionAdviceDraft,
    payload: BankingAdvisorInput,
) -> None:
    """Reject unknown options, unauthorized combinations, numbers, and protected claims."""
    known_option_ids = frozenset(option.option_id for option in payload.options)
    allowed_combinations = {
        _canonical_option_set(combination)
        for combination in payload.allowed_option_combinations
    }

    _validate_prose(advice.overview, known_option_ids)
    seen_suggestions: set[tuple[str, ...]] = set()
    for suggestion in advice.suggestions:
        option_ids = suggestion.option_ids
        if len(set(option_ids)) != len(option_ids):
            raise ValueError("Banking advice suggestion contains duplicate option IDs.")
        if not set(option_ids).issubset(known_option_ids):
            raise ValueError("Banking advice references an unknown option ID.")

        canonical = _canonical_option_set(option_ids)
        if len(option_ids) > 1 and canonical not in allowed_combinations:
            raise ValueError("Banking advice contains an unconfigured option combination.")
        if canonical in seen_suggestions:
            raise ValueError("Banking advice contains a duplicate suggestion.")
        seen_suggestions.add(canonical)
        _validate_prose(suggestion.rationale, known_option_ids)
