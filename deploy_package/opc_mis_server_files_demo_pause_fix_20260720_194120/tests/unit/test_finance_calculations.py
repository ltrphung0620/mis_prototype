"""Unit tests for generic deterministic Finance calculations."""

from types import SimpleNamespace

from opc_mis.business.agents.finance.cashflow import calculate_cashflow
from opc_mis.business.agents.finance.profitability import calculate_profitability
from opc_mis.business.agents.finance.receivables import calculate_receivables
from opc_mis.business.agents.finance.requirements import validate_finance_records
from opc_mis.business.agents.finance.transaction_evidence import (
    has_explicit_case_transaction_link,
)
from opc_mis.domain.dataset import DatasetRecord
from opc_mis.domain.team_pack import SheetRegistry


def record(record_id: str, **values: object) -> DatasetRecord:
    return DatasetRecord(
        sheet="TEST",
        row_number=2,
        record_id=record_id,
        values=dict(values),
        display_values=dict(values),
    )


def test_profitability_uses_only_explicit_order_values() -> None:
    contract = record("CON-X", contract_value=1_000.0)
    orders = (
        record("ORD-A", order_revenue=300.0, estimated_cost=180.0),
        record("ORD-B", order_revenue=200.0, estimated_cost=150.0),
    )

    result = calculate_profitability(contract, orders)

    assert result.revenue_total == 500.0
    assert result.estimated_cost_total == 330.0
    assert result.gross_profit == 170.0
    assert result.gross_margin == 0.34
    assert result.order_coverage_ratio == 0.5
    assert result.uncovered_contract_value == 500.0


def test_profitability_safe_ratio_does_not_divide_by_zero() -> None:
    result = calculate_profitability(
        record("CON-X", contract_value=0.0),
        (),
    )

    assert result.gross_margin is None
    assert result.order_coverage_ratio is None


def test_receivables_respect_source_status_without_date_assumptions() -> None:
    contract = record("CON-X", contract_value=1_000.0)
    invoices = (
        record("INV-A", invoice_amount=100.0, status="Paid"),
        record("INV-B", invoice_amount=200.0, status="Open"),
        record("INV-C", invoice_amount=300.0, status="Not issued"),
    )

    result = calculate_receivables(contract, invoices)

    assert result.invoice_total == 600.0
    assert result.paid_total == 100.0
    assert result.open_total == 200.0
    assert result.not_issued_total == 300.0
    assert result.outstanding_issued == 200.0
    assert result.invoice_coverage_ratio == 0.6


def test_cashflow_calculation_remains_opc_global() -> None:
    rows = (
        record(
            "MONTH-A",
            month="PERIOD-A",
            expected_cash_in=100.0,
            expected_cash_out=200.0,
            cash_reserve_minimum=500.0,
            projected_closing_cash=300.0,
        ),
        record(
            "MONTH-B",
            month="PERIOD-B",
            expected_cash_in=300.0,
            expected_cash_out=100.0,
            cash_reserve_minimum=500.0,
            projected_closing_cash=-100.0,
        ),
    )

    result = calculate_cashflow(rows)

    assert result.month_count == 2
    assert result.worst_reserve_gap == 600.0
    assert result.worst_reserve_gap_month == "PERIOD-B"
    assert result.negative_net_month_count == 1


def test_finance_requirements_block_invalid_calculation_inputs_only() -> None:
    failures = validate_finance_records(
        contract=record(
            "CON-X",
            contract_value="not-a-number",
            gross_margin=0.2,
            payment_terms="Monthly",
        ),
        orders=(record("ORD-X", order_revenue=None, estimated_cost=1.0),),
        invoices=(record("INV-X", invoice_amount=2.0, status=None),),
    )

    assert {failure.field for failure in failures} == {
        "contract_value",
        "order_revenue",
        "status",
    }
    assert all("bank" not in failure.code.casefold() for failure in failures)


def test_transaction_descriptions_never_create_a_relationship() -> None:
    no_key_dataset = SimpleNamespace(
        headers={
            SheetRegistry.BANK_TRANSACTIONS.sheet_name: (
                "txn_id",
                "description",
                "amount",
            )
        }
    )
    explicit_key_dataset = SimpleNamespace(
        headers={
            SheetRegistry.BANK_TRANSACTIONS.sheet_name: (
                "txn_id",
                "invoice_id",
                "description",
            )
        }
    )

    assert has_explicit_case_transaction_link(no_key_dataset) is False
    assert has_explicit_case_transaction_link(explicit_key_dataset) is True
