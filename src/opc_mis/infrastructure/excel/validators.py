"""Deterministic Excel record and relationship validation."""

from typing import Any

from opc_mis.domain.dataset import ValidationIssue
from opc_mis.domain.validation import valid_date_like, valid_identifier, valid_numeric

IDENTIFIER_FIELDS = {
    "contract_id",
    "customer_id",
    "order_id",
    "invoice_id",
    "service_id",
    "credit_case_id",
    "company_id",
    "alert_id",
    "txn_id",
    "account_id",
}

NUMERIC_FIELDS = {
    "contract_value",
    "gross_margin",
    "payment_reliability",
    "list_price",
    "target_margin",
    "order_revenue",
    "estimated_cost",
    "invoice_amount",
    "requested_amount",
    "eligibility_score",
    "amount",
    "transaction_risk_score",
    "expected_cash_in",
    "expected_cash_out",
    "direct_cost",
    "opex",
    "cash_reserve_minimum",
    "projected_closing_cash",
}

DATE_FIELDS = {
    "start_date",
    "end_date",
    "order_date",
    "due_date",
    "issue_date",
    "paid_date",
    "txn_date",
}

TEXT_FIELDS = {
    "customer_name",
    "customer_type",
    "province",
    "industry",
    "strategic_value",
    "revenue_model",
    "banking_fit_hint",
    "status",
    "description",
    "payment_terms",
    "service_name",
    "pricing_model",
    "target_segment",
    "delivery_note",
    "request_type",
    "tenor",
    "collateral_or_basis",
    "precheck_note",
    "approval_status",
    "management_note",
    "alert_type",
    "related_record",
    "severity",
    "recommended_action",
    "bank",
    "direction",
    "counterparty_id",
    "txn_status",
}


def validate_record_types(
    sheet: str, record_id: str, values: dict[str, Any]
) -> list[ValidationIssue]:
    """Report invalid present values; nullable fields are evaluated by requirements."""
    issues: list[ValidationIssue] = []
    for field, value in values.items():
        if value is None:
            continue
        valid = True
        expected = ""
        if field in IDENTIFIER_FIELDS:
            valid = valid_identifier(value)
            expected = "non-empty identifier"
        elif field in NUMERIC_FIELDS:
            valid = valid_numeric(value)
            expected = "number"
        elif field in DATE_FIELDS:
            valid = valid_date_like(value)
            expected = "date, ISO date string, or Excel serial number"
        elif field in TEXT_FIELDS:
            valid = isinstance(value, str)
            expected = "text"
        if not valid:
            issues.append(
                ValidationIssue(
                    code="INVALID_DATA_TYPE",
                    sheet=sheet,
                    record_id=record_id,
                    field=field,
                    reason=f"Expected {expected}; received {type(value).__name__}",
                )
            )
    return issues


def validate_foreign_key_values(
    *,
    child_sheet: str,
    child_rows: list[tuple[str, dict[str, Any]]],
    child_field: str,
    parent_sheet: str,
    parent_values: set[str],
) -> list[ValidationIssue]:
    """Validate one explicit ID relationship without fuzzy or descriptive matching."""
    issues: list[ValidationIssue] = []
    for record_id, values in child_rows:
        value = values.get(child_field)
        if value is None or value not in parent_values:
            issues.append(
                ValidationIssue(
                    code="BROKEN_FOREIGN_KEY",
                    sheet=child_sheet,
                    record_id=record_id,
                    field=child_field,
                    reason=(f"Value {value!r} does not resolve in parent sheet {parent_sheet}."),
                )
            )
    return issues
