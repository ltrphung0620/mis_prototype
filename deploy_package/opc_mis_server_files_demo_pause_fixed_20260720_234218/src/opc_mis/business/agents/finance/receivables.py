"""Pure invoice aggregation for invoices selected through case orders."""

from dataclasses import dataclass

from opc_mis.business.agents.finance.requirements import numeric_value
from opc_mis.domain.dataset import DatasetRecord


@dataclass(frozen=True)
class ReceivableValues:
    invoice_count: int
    invoice_total: float
    paid_total: float
    open_total: float
    not_issued_total: float
    outstanding_issued: float
    invoice_coverage_ratio: float | None


def calculate_receivables(
    contract: DatasetRecord, invoices: tuple[DatasetRecord, ...]
) -> ReceivableValues:
    """Aggregate status-labelled invoice amounts without date assumptions."""
    contract_value = numeric_value(contract, "contract_value")
    if contract_value is None:
        raise ValueError("contract_value must be validated before calculation")
    amounts = [(invoice, numeric_value(invoice, "invoice_amount") or 0.0) for invoice in invoices]
    total = sum(amount for _, amount in amounts)
    paid = sum(
        amount
        for invoice, amount in amounts
        if str(invoice.values.get("status", "")).casefold() == "paid"
    )
    opened = sum(
        amount
        for invoice, amount in amounts
        if str(invoice.values.get("status", "")).casefold() == "open"
    )
    not_issued = sum(
        amount
        for invoice, amount in amounts
        if str(invoice.values.get("status", "")).casefold() == "not issued"
    )
    outstanding = sum(
        amount
        for invoice, amount in amounts
        if str(invoice.values.get("status", "")).casefold() not in {"paid", "not issued"}
    )
    coverage = total / contract_value if contract_value > 0 else None
    return ReceivableValues(
        invoice_count=len(invoices),
        invoice_total=total,
        paid_total=paid,
        open_total=opened,
        not_issued_total=not_issued,
        outstanding_issued=outstanding,
        invoice_coverage_ratio=coverage,
    )
