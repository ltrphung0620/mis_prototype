"""Unit tests for generic deterministic Operations calculations."""

from datetime import date

import pytest

from opc_mis.business.skills.operations.date_normalizer import inclusive_days, normalize_date
from opc_mis.business.skills.operations.requirements import validate_operations_records
from opc_mis.business.skills.operations.schedule_engine import calculate_schedule
from opc_mis.business.skills.operations.status_classifier import classify_source_status
from opc_mis.domain.dataset import DatasetRecord
from opc_mis.domain.enums import OperationsSourceStatusCategory
from opc_mis.domain.lineage import LineageFactory


def record(record_id: str, **values: object) -> DatasetRecord:
    return DatasetRecord(
        sheet="TEST",
        row_number=2,
        record_id=record_id,
        values=dict(values),
        display_values=dict(values),
    )


def test_excel_serial_and_iso_dates_are_normalized_deterministically() -> None:
    assert normalize_date(1) == date(1899, 12, 31)
    assert normalize_date("2026-07-16") == date(2026, 7, 16)
    assert inclusive_days(date(2026, 1, 1), date(2026, 1, 1)) == 1


@pytest.mark.parametrize("value", [None, True, 0, -1, "not-a-date", float("nan")])
def test_invalid_dates_fail_explicitly(value: object) -> None:
    with pytest.raises(ValueError):
        normalize_date(value)


def test_source_status_classification_is_exact_not_fuzzy() -> None:
    assert classify_source_status("At risk") is (
        OperationsSourceStatusCategory.SOURCE_FLAGGED_STATUS
    )
    assert classify_source_status("at-risk") is (
        OperationsSourceStatusCategory.UNCLASSIFIED_SOURCE_STATUS
    )


def test_schedule_calculates_gaps_overlap_window_and_explicit_past_due() -> None:
    contract = record("CON-X", start_date="2026-01-01", end_date="2026-01-31")
    orders = (
        record(
            "ORD-A",
            order_date="2026-01-01",
            due_date="2026-01-05",
            status="Delivered",
        ),
        record(
            "ORD-B",
            order_date="2026-01-08",
            due_date="2026-01-12",
            status="In progress",
        ),
        record(
            "ORD-C",
            order_date="2026-01-10",
            due_date="2026-02-02",
            status="Planned",
        ),
    )

    result = calculate_schedule(
        contract=contract,
        orders=orders,
        as_of_date=date(2026, 1, 20),
    )

    assert result.contract_duration_days == 31
    assert result.gap_days == (2,)
    assert result.overlap_days == (3,)
    assert result.outside_contract_count == 1
    assert result.orders[0].past_due_days is None
    assert result.orders[1].past_due_days == 8
    assert result.orders[2].past_due_days == 0


def test_no_as_of_date_does_not_use_the_system_clock() -> None:
    result = calculate_schedule(
        contract=record("CON-X", start_date="2020-01-01", end_date="2030-01-01"),
        orders=(
            record(
                "ORD-X",
                order_date="2020-01-01",
                due_date="2020-01-02",
                status="In progress",
            ),
        ),
        as_of_date=None,
    )

    assert result.orders[0].past_due_days is None


def test_operations_requirements_block_only_required_schedule_inputs() -> None:
    failures = validate_operations_records(
        contract=record("CON-X", start_date="2026-01-02", end_date="2026-01-01"),
        orders=(
            record(
                "ORD-X",
                order_date="2026-01-03",
                due_date="invalid",
                status="",
            ),
        ),
        lineage=LineageFactory("DATASET-X", "SOURCE-HASH"),
    )

    assert {failure.code for failure in failures} == {
        "OPERATIONS_CONTRACT_WINDOW_INVALID",
        "OPERATIONS_ORDER_DUE_DATE_INVALID",
        "OPERATIONS_ORDER_STATUS_MISSING",
    }
    assert all("BANK" not in failure.code for failure in failures)
