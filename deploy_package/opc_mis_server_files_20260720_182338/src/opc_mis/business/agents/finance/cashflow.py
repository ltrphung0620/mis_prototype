"""Pure OPC-level cashflow calculations with explicit non-case scope."""

from dataclasses import dataclass

from opc_mis.business.agents.finance.requirements import numeric_value
from opc_mis.domain.dataset import DatasetRecord


@dataclass(frozen=True)
class CashflowValues:
    month_count: int
    worst_reserve_gap: float | None
    worst_reserve_gap_month: str | None
    negative_net_month_count: int


def calculate_cashflow(records: tuple[DatasetRecord, ...]) -> CashflowValues:
    """Calculate only global projections because TeamPack has no contract key."""
    evaluated: list[tuple[str, float, float]] = []
    for record in records:
        cash_in = numeric_value(record, "expected_cash_in")
        cash_out = numeric_value(record, "expected_cash_out")
        reserve = numeric_value(record, "cash_reserve_minimum")
        closing = numeric_value(record, "projected_closing_cash")
        if None in {cash_in, cash_out, reserve, closing}:
            continue
        month = str(record.values.get("month") or record.record_id)
        evaluated.append((month, max(reserve - closing, 0.0), cash_in - cash_out))
    if not evaluated:
        return CashflowValues(0, None, None, 0)
    worst = max(evaluated, key=lambda item: item[1])
    return CashflowValues(
        month_count=len(evaluated),
        worst_reserve_gap=worst[1],
        worst_reserve_gap_month=worst[0],
        negative_net_month_count=sum(1 for _, _, net in evaluated if net < 0),
    )
