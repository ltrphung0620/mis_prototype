"""Tests for exact Planner requirement and credit-profile resolution."""

from __future__ import annotations

import pytest

from opc_mis.business.skills.planner.contract_requirement_resolver import (
    ContractRequirementResolver,
)
from opc_mis.domain.dataset import DatasetRecord, DatasetSnapshot
from opc_mis.domain.enums import (
    ContractRequirementType,
    RequirementAmountSemantics,
    RequirementCertainty,
    SourceType,
)
from opc_mis.domain.lineage import LineageFactory
from opc_mis.domain.team_pack import SheetRegistry

CONTRACT_ID = "CON-004"


def _record(
    sheet: str,
    row_number: int,
    record_id: str,
    values: dict[str, object],
) -> DatasetRecord:
    return DatasetRecord(
        sheet=sheet,
        row_number=row_number,
        record_id=record_id,
        values=values,
        display_values=dict(values),
    )


def _contract(
    *, payment_terms: str = "Performance bond required", contract_id: str = CONTRACT_ID
) -> DatasetRecord:
    return _record(
        SheetRegistry.CONTRACTS.sheet_name,
        2,
        contract_id,
        {"contract_id": contract_id, "payment_terms": payment_terms},
    )


def _order(
    order_id: str,
    delivery_note: str,
) -> DatasetRecord:
    return _record(
        SheetRegistry.ORDERS.sheet_name,
        2,
        order_id,
        {
            "order_id": order_id,
            "contract_id": CONTRACT_ID,
            "delivery_note": delivery_note,
        },
    )


def _credit_profile(
    *,
    collateral_or_basis: str = "Contract CON-004",
    company_id: str = "OPC-001",
    request_type: str = "Performance bond",
    requested_amount: object = 420_000_000,
    credit_case_id: str = "CR-002",
) -> DatasetRecord:
    return _record(
        SheetRegistry.CREDIT_PROFILES.sheet_name,
        2,
        credit_case_id,
        {
            "credit_case_id": credit_case_id,
            "company_id": company_id,
            "request_type": request_type,
            "requested_amount": requested_amount,
            "collateral_or_basis": collateral_or_basis,
        },
    )


def _snapshot(
    *,
    selected_contract: DatasetRecord,
    credits: tuple[DatasetRecord, ...] = (),
) -> DatasetSnapshot:
    opc_company = _record(
        SheetRegistry.OPC_PROFILE.sheet_name,
        2,
        "company_id",
        {"field": "company_id", "value": "OPC-001"},
    )
    other_contract = _contract(contract_id="CON-005", payment_terms="Milestone payment")
    records = {
        SheetRegistry.OPC_PROFILE.sheet_name: [opc_company],
        SheetRegistry.CONTRACTS.sheet_name: [selected_contract, other_contract],
        SheetRegistry.CREDIT_PROFILES.sheet_name: list(credits),
    }
    return DatasetSnapshot(
        dataset_id="DATASET-REQUIREMENT-TEST",
        source_locator="memory://requirements",
        source_hash="SOURCE-REQUIREMENT-TEST",
        snapshot_hash="SNAPSHOT-REQUIREMENT-TEST",
        sheets=records,
        headers={
            SheetRegistry.OPC_PROFILE.sheet_name: ("field", "value"),
            SheetRegistry.CONTRACTS.sheet_name: ("contract_id", "payment_terms"),
            SheetRegistry.CREDIT_PROFILES.sheet_name: (
                "credit_case_id",
                "company_id",
                "request_type",
                "requested_amount",
                "collateral_or_basis",
            ),
        },
        indexes={
            sheet: {record.record_id: [record] for record in sheet_records}
            for sheet, sheet_records in records.items()
        },
        duplicate_ids={},
        validation_issues=[],
        missing_sheets=(),
        missing_headers={},
    )


def _resolve(
    *,
    contract: DatasetRecord | None = None,
    orders: tuple[DatasetRecord, ...] = (),
    credits: tuple[DatasetRecord, ...] = (),
):
    selected_contract = contract or _contract()
    snapshot = _snapshot(selected_contract=selected_contract, credits=credits)
    return ContractRequirementResolver().resolve(
        dataset=snapshot,
        contract=selected_contract,
        orders=orders,
        evaluation_case_id="CASE-REQUIREMENT-TEST",
        lineage=LineageFactory(snapshot.dataset_id, snapshot.source_hash),
    )


def test_exact_requirement_and_credit_profile_create_a_traceable_amount() -> None:
    result = _resolve(
        orders=(_order("ORD-005", "Requires performance bond"),),
        credits=(_credit_profile(),),
    )

    assert result.failures == ()
    assert result.warnings == ()
    assert tuple(item.record_id for item in result.credit_profiles) == ("CR-002",)
    assert len(result.requirements) == 1
    requirement = result.requirements[0]
    assert requirement.requirement_type is ContractRequirementType.PERFORMANCE_BOND
    assert requirement.certainty is RequirementCertainty.REQUIRED
    assert requirement.requested_amount == 420_000_000
    assert (
        requirement.amount_semantics
        is RequirementAmountSemantics.CREDIT_PROFILE_REQUESTED_AMOUNT
    )
    assert requirement.credit_case_id == "CR-002"
    assert requirement.source_record_ids == (CONTRACT_ID, "ORD-005")
    assert requirement.source_fields == ("payment_terms", "delivery_note")

    evidence_by_id = {item.evidence_id: item for item in result.evidence_refs}
    relationship = next(
        item
        for item in result.evidence_refs
        if item.field == "contract_requirement_relationship"
    )
    assert relationship.source_type is SourceType.DERIVED
    relationship_sources = {
        evidence_by_id[evidence_id].field
        for evidence_id in relationship.source_evidence_ids
    }
    assert relationship_sources == {"contract_id", "collateral_or_basis"}
    assert set(requirement.evidence_ids).issubset(evidence_by_id)


@pytest.mark.parametrize(
    ("credit", "failure_code", "expected_credit_ids", "expected_credit_case_id"),
    (
        (
            _credit_profile(collateral_or_basis="Contract CON-004-X"),
            "PERFORMANCE_BOND_CREDIT_PROFILE_REQUIRED",
            (),
            None,
        ),
        (
            _credit_profile(collateral_or_basis="CON-004 and CON-005"),
            "PERFORMANCE_BOND_CREDIT_PROFILE_REQUIRED",
            (),
            None,
        ),
        (
            _credit_profile(company_id="OPC-OTHER"),
            "PERFORMANCE_BOND_CREDIT_PROFILE_REQUIRED",
            (),
            None,
        ),
        (
            _credit_profile(request_type="Performance bond facility"),
            "PERFORMANCE_BOND_CREDIT_PROFILE_REQUIRED",
            (),
            None,
        ),
        (
            _credit_profile(requested_amount=420_000_000.5),
            "PERFORMANCE_BOND_REQUESTED_AMOUNT_REQUIRED",
            ("CR-002",),
            "CR-002",
        ),
    ),
)
def test_required_performance_bond_blocks_when_exact_amount_link_is_not_valid(
    credit: DatasetRecord,
    failure_code: str,
    expected_credit_ids: tuple[str, ...],
    expected_credit_case_id: str | None,
) -> None:
    result = _resolve(credits=(credit,))

    assert tuple(item.record_id for item in result.credit_profiles) == expected_credit_ids
    assert result.requirements[0].requested_amount is None
    assert result.requirements[0].credit_case_id == expected_credit_case_id
    assert tuple(item.code for item in result.failures) == (failure_code,)
    assert result.warnings == ()


def test_multiple_exact_profiles_are_not_selected() -> None:
    result = _resolve(
        credits=(
            _credit_profile(credit_case_id="CR-002"),
            _credit_profile(credit_case_id="CR-ALT", requested_amount=430_000_000),
        )
    )

    assert tuple(item.record_id for item in result.credit_profiles) == (
        "CR-002",
        "CR-ALT",
    )
    assert tuple(item.code for item in result.failures) == (
        "PERFORMANCE_BOND_CREDIT_PROFILE_AMBIGUOUS",
    )


def test_unlinked_working_capital_is_a_warning_not_a_planner_blocker() -> None:
    result = _resolve(
        contract=_contract(payment_terms="Monthly payment"),
        orders=(_order("ORD-006", "Requires working capital"),),
    )

    assert result.failures == ()
    assert result.requirements[0].requirement_type is ContractRequirementType.WORKING_CAPITAL
    assert result.requirements[0].requested_amount is None
    assert tuple(item.warning_code for item in result.warnings) == (
        "CONTRACT_REQUIREMENT_CREDIT_PROFILE_UNLINKED",
    )


def test_possible_trade_finance_requirement_keeps_its_source_certainty() -> None:
    result = _resolve(
        contract=_contract(payment_terms="Possible LC/trade finance"),
        orders=(_order("ORD-007", "May require LC support"),),
        credits=(
            _credit_profile(
                credit_case_id="CR-003",
                request_type="Trade finance/LC support",
                requested_amount=650_000_000,
                collateral_or_basis="CON-004 documentation",
            ),
        ),
    )

    assert result.failures == ()
    assert result.warnings == ()
    requirement = result.requirements[0]
    assert requirement.requirement_type is ContractRequirementType.TRADE_FINANCE_LC
    assert requirement.certainty is RequirementCertainty.POSSIBLE
    assert requirement.requested_amount == 650_000_000
    assert requirement.credit_case_id == "CR-003"
    assert requirement.source_record_ids == (CONTRACT_ID, "ORD-007")


def test_noncanonical_free_text_does_not_create_a_requirement() -> None:
    result = _resolve(
        contract=_contract(payment_terms="Customer asks for a performance bond"),
        orders=(_order("ORD-OTHER", "Working capital may be useful"),),
        credits=(_credit_profile(),),
    )

    assert result.requirements == ()
    assert result.credit_profiles == ()
    assert result.failures == ()
    assert result.warnings == ()


def test_exact_relationship_does_not_assume_a_contract_id_prefix() -> None:
    contract_id = "DEAL_ALPHA"
    result = _resolve(
        contract=_contract(contract_id=contract_id),
        credits=(
            _credit_profile(collateral_or_basis=f"Contract {contract_id}"),
        ),
    )

    assert result.failures == ()
    assert result.requirements[0].requested_amount == 420_000_000
    assert result.requirements[0].credit_case_id == "CR-002"
