"""Integration expectations for CON-004, derived from the official TeamPack."""

from pathlib import Path

import pandas as pd

from opc_mis.domain.enums import (
    CashflowScope,
    ContractRequirementType,
    CurrencyCode,
    ReadinessStatus,
    RequirementAmountSemantics,
    RequirementCertainty,
    SourceType,
    WorkflowStatus,
)
from opc_mis.domain.evidence import DataPatch
from tests.conftest import execute_planner, make_request


def test_con004_creates_traceable_case_from_actual_workbook(team_pack_path: Path) -> None:
    contract_id = "CON-004"
    contracts = pd.read_excel(team_pack_path, sheet_name="04_CONTRACTS", dtype=object)
    customers = pd.read_excel(team_pack_path, sheet_name="03_CUSTOMERS", dtype=object)
    orders = pd.read_excel(team_pack_path, sheet_name="06_ORDERS", dtype=object)
    invoices = pd.read_excel(team_pack_path, sheet_name="07_INVOICES", dtype=object)
    products = pd.read_excel(team_pack_path, sheet_name="05_PRODUCTS", dtype=object)
    credit_profiles = pd.read_excel(
        team_pack_path, sheet_name="10_CREDIT_PROFILE", dtype=object
    )

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
    expected_credit = credit_profiles.loc[
        (credit_profiles["request_type"] == "Performance bond")
        & (credit_profiles["collateral_or_basis"] == f"Contract {contract_id}")
    ].iloc[0]

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
    assert case.related_credit_case_ids == (str(expected_credit["credit_case_id"]),)
    assert case.cashflow_scope is CashflowScope.OPC_GLOBAL

    requirements = {item.requirement_type: item for item in case.contract_requirements}
    performance_bond = requirements[ContractRequirementType.PERFORMANCE_BOND]
    assert performance_bond.certainty is RequirementCertainty.REQUIRED
    assert performance_bond.requested_amount == int(expected_credit["requested_amount"])
    assert performance_bond.requested_amount_currency is CurrencyCode.VND
    assert (
        performance_bond.amount_semantics
        is RequirementAmountSemantics.CREDIT_PROFILE_REQUESTED_AMOUNT
    )
    assert performance_bond.credit_case_id == str(expected_credit["credit_case_id"])
    assert performance_bond.source_record_ids == (contract_id, "ORD-005")
    assert performance_bond.source_fields == ("payment_terms", "delivery_note")

    working_capital = requirements[ContractRequirementType.WORKING_CAPITAL]
    assert working_capital.certainty is RequirementCertainty.REQUIRED
    assert working_capital.requested_amount is None
    assert working_capital.amount_semantics is None
    assert working_capital.credit_case_id is None
    assert any(
        warning.warning_code == "CONTRACT_REQUIREMENT_CREDIT_PROFILE_UNLINKED"
        and warning.details["requirement_id"] == working_capital.requirement_id
        for warning in result.planner_result.warnings
    )

    selected_records = {evidence.record_id for evidence in case.evidence_refs}
    required_records = {
        contract_id,
        expected_customer,
        *expected_order_ids,
        str(expected_credit["credit_case_id"]),
    }
    assert required_records.issubset(selected_records)
    for record_id in required_records:
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


def test_con004_pauses_at_planner_when_performance_bond_amount_is_missing(
    team_pack_path: Path,
) -> None:
    patch = DataPatch(
        patch_id="PATCH-CR-002-MISSING-AMOUNT",
        source=SourceType.USER_INPUT,
        target_sheet="10_CREDIT_PROFILE",
        target_record="CR-002",
        field="requested_amount",
        value=None,
        evidence_note="Exercise Planner source-data readiness for a required performance bond.",
    )

    result = execute_planner(
        make_request(team_pack_path, "CON-004", data_patches=(patch,))
    )

    assert result.status is WorkflowStatus.WAITING_FOR_INPUT
    assert result.planner_result is not None
    assert tuple(
        item.requirement_code for item in result.planner_result.missing_data_requests
    ) == ("PERFORMANCE_BOND_REQUESTED_AMOUNT_REQUIRED",)
    case = result.planner_result.evaluation_case
    assert case is not None
    performance_bond = next(
        item
        for item in case.contract_requirements
        if item.requirement_type is ContractRequirementType.PERFORMANCE_BOND
    )
    assert performance_bond.requested_amount is None
    assert performance_bond.credit_case_id == "CR-002"
    assert case.related_credit_case_ids == ("CR-002",)
    assert any(
        evidence.source_type is SourceType.USER_INPUT
        and evidence.record_id == "CR-002"
        and evidence.field == "requested_amount"
        for request in result.planner_result.missing_data_requests
        for evidence in request.evidence_refs
    )
