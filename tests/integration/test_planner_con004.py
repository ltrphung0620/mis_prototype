"""Integration expectations for CON-004, derived from the official TeamPack."""

from pathlib import Path

import pandas as pd

from opc_mis.domain.enums import (
    CashflowScope,
    ReadinessStatus,
    SourceType,
    WorkflowStatus,
)
from tests.conftest import execute_planner, make_request


def test_con004_creates_traceable_case_from_actual_workbook(team_pack_path: Path) -> None:
    contract_id = "CON-004"
    contracts = pd.read_excel(team_pack_path, sheet_name="04_CONTRACTS", dtype=object)
    customers = pd.read_excel(team_pack_path, sheet_name="03_CUSTOMERS", dtype=object)
    orders = pd.read_excel(team_pack_path, sheet_name="06_ORDERS", dtype=object)
    invoices = pd.read_excel(team_pack_path, sheet_name="07_INVOICES", dtype=object)
    products = pd.read_excel(team_pack_path, sheet_name="05_PRODUCTS", dtype=object)

    contract = contracts.loc[contracts["contract_id"] == contract_id].iloc[0]
    expected_customer = str(contract["customer_id"])
    assert not customers.loc[customers["customer_id"] == expected_customer].empty
    related_orders = orders.loc[orders["contract_id"] == contract_id]
    expected_order_ids = tuple(related_orders["order_id"].astype(str))
    expected_invoice_ids = tuple(
        invoices.loc[invoices["order_id"].isin(expected_order_ids), "invoice_id"].astype(str)
    )
    expected_service_ids = tuple(
        products.loc[
            products["service_id"].isin(set(related_orders["service_id"])), "service_id"
        ].astype(str)
    )

    result = execute_planner(make_request(team_pack_path, contract_id))

    assert result.status is WorkflowStatus.COMPLETED
    assert result.planner_result is not None
    assert result.planner_result.data_readiness.status in {
        ReadinessStatus.READY,
        ReadinessStatus.READY_WITH_WARNINGS,
    }
    case = result.planner_result.evaluation_case
    assert case is not None
    assert case.customer_id == expected_customer
    assert case.related_order_ids == expected_order_ids
    assert case.related_invoice_ids == expected_invoice_ids
    assert case.related_service_ids == expected_service_ids
    assert case.related_credit_case_ids == ()
    assert case.cashflow_scope is CashflowScope.OPC_GLOBAL

    selected_records = {evidence.record_id for evidence in case.evidence_refs}
    assert {contract_id, expected_customer, *expected_order_ids}.issubset(selected_records)
    for record_id in {contract_id, expected_customer, *expected_order_ids}:
        assert any(
            evidence.record_id == record_id and evidence.source_type is SourceType.TEAM_PACK
            for evidence in case.evidence_refs
        )


def test_con004_coverage_warning_is_derived_from_source_values(
    team_pack_path: Path,
) -> None:
    contract_id = "CON-004"
    contracts = pd.read_excel(team_pack_path, sheet_name="04_CONTRACTS", dtype=object)
    orders = pd.read_excel(team_pack_path, sheet_name="06_ORDERS", dtype=object)
    contract_value = contracts.loc[contracts["contract_id"] == contract_id, "contract_value"].iloc[
        0
    ]
    order_revenue = orders.loc[orders["contract_id"] == contract_id, "order_revenue"].sum()
    expected_gap = contract_value - order_revenue

    result = execute_planner(make_request(team_pack_path, contract_id))
    assert result.planner_result is not None
    warnings = {warning.warning_code: warning for warning in result.planner_result.warnings}

    if expected_gap != 0:
        warning = warnings["ORDER_COVERAGE_GAP"]
        assert warning.details["unmapped_contract_value"] == expected_gap
        assert any(
            evidence.source_type is SourceType.DERIVED
            and evidence.field == "unmapped_contract_value"
            for evidence in warning.evidence_refs
        )
        assert (
            len(warning.evidence_refs) == len(orders.loc[orders["contract_id"] == contract_id]) + 2
        )
    else:
        assert "ORDER_COVERAGE_GAP" not in warnings
