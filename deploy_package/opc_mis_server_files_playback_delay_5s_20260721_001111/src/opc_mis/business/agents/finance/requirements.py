"""Blocking Finance input requirements; banking inputs are intentionally excluded."""

from dataclasses import dataclass
from numbers import Real

from opc_mis.domain.dataset import DatasetRecord
from opc_mis.domain.evidence import EvidenceRef


@dataclass(frozen=True)
class FinanceRequirementFailure:
    """One actual blocker for deterministic Finance calculations."""

    code: str
    target_record: str
    field: str
    expected_type: str
    reason: str
    evidence_refs: tuple[EvidenceRef, ...] = ()


def numeric_value(record: DatasetRecord, field: str) -> float | None:
    """Return a finite numeric value without accepting booleans or coercing text."""
    value = record.values.get(field)
    if isinstance(value, bool) or not isinstance(value, Real):
        return None
    converted = float(value)
    if converted != converted or converted in {float("inf"), float("-inf")}:
        return None
    return converted


def validate_finance_records(
    *,
    contract: DatasetRecord,
    orders: tuple[DatasetRecord, ...],
    invoices: tuple[DatasetRecord, ...],
) -> tuple[FinanceRequirementFailure, ...]:
    """Validate only fields required to calculate the case-specific finance facts."""
    failures: list[FinanceRequirementFailure] = []
    for field in ("contract_value", "gross_margin"):
        if numeric_value(contract, field) is None:
            failures.append(
                FinanceRequirementFailure(
                    code="FINANCE_CONTRACT_VALUE_INVALID",
                    target_record=contract.record_id,
                    field=field,
                    expected_type="finite number",
                    reason=f"Finance requires a finite {field} from the selected contract.",
                )
            )
    payment_terms = contract.values.get("payment_terms")
    if not isinstance(payment_terms, str) or not payment_terms.strip():
        failures.append(
            FinanceRequirementFailure(
                code="FINANCE_PAYMENT_TERMS_MISSING",
                target_record=contract.record_id,
                field="payment_terms",
                expected_type="non-empty text",
                reason="Payment terms are required to record explicit finance conditions.",
            )
        )
    for order in orders:
        for field in ("order_revenue", "estimated_cost"):
            if numeric_value(order, field) is None:
                failures.append(
                    FinanceRequirementFailure(
                        code="FINANCE_ORDER_VALUE_INVALID",
                        target_record=order.record_id,
                        field=field,
                        expected_type="finite number",
                        reason=(
                            "An explicitly related order needs a finite value for "
                            "deterministic profitability calculations."
                        ),
                    )
                )
    for invoice in invoices:
        if numeric_value(invoice, "invoice_amount") is None:
            failures.append(
                FinanceRequirementFailure(
                    code="FINANCE_INVOICE_VALUE_INVALID",
                    target_record=invoice.record_id,
                    field="invoice_amount",
                    expected_type="finite number",
                    reason="An explicitly related invoice needs a finite invoice amount.",
                )
            )
        status = invoice.values.get("status")
        if not isinstance(status, str) or not status.strip():
            failures.append(
                FinanceRequirementFailure(
                    code="FINANCE_INVOICE_STATUS_MISSING",
                    target_record=invoice.record_id,
                    field="status",
                    expected_type="non-empty text",
                    reason="Invoice status is required to classify receivables.",
                )
            )
    return tuple(failures)
