"""Pure profitability calculations for explicitly related orders."""

from dataclasses import dataclass

from opc_mis.business.agents.finance.requirements import numeric_value
from opc_mis.domain.dataset import DatasetRecord


@dataclass(frozen=True)
class ProfitabilityValues:
    order_count: int
    revenue_total: float
    estimated_cost_total: float
    gross_profit: float
    gross_margin: float | None
    order_coverage_ratio: float | None
    uncovered_contract_value: float


def calculate_profitability(
    contract: DatasetRecord, orders: tuple[DatasetRecord, ...]
) -> ProfitabilityValues:
    """Calculate sums and safe ratios without interpreting their risk."""
    contract_value = numeric_value(contract, "contract_value")
    if contract_value is None:
        raise ValueError("contract_value must be validated before calculation")
    revenue = sum(numeric_value(order, "order_revenue") or 0.0 for order in orders)
    cost = sum(numeric_value(order, "estimated_cost") or 0.0 for order in orders)
    profit = revenue - cost
    margin = profit / revenue if revenue > 0 else None
    coverage = revenue / contract_value if contract_value > 0 else None
    return ProfitabilityValues(
        order_count=len(orders),
        revenue_total=revenue,
        estimated_cost_total=cost,
        gross_profit=profit,
        gross_margin=margin,
        order_coverage_ratio=coverage,
        uncovered_contract_value=max(contract_value - revenue, 0.0),
    )
