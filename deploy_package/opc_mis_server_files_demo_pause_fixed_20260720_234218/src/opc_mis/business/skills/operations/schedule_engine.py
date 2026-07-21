"""Pure deterministic schedule calculations for explicitly related orders."""

from dataclasses import dataclass
from datetime import date

from opc_mis.business.skills.operations.date_normalizer import inclusive_days, normalize_date
from opc_mis.business.skills.operations.status_classifier import classify_source_status
from opc_mis.domain.dataset import DatasetRecord
from opc_mis.domain.enums import OperationsSourceStatusCategory


@dataclass(frozen=True)
class OrderScheduleValue:
    record: DatasetRecord
    order_date: date
    due_date: date
    duration_days: int
    source_status: str
    status_category: OperationsSourceStatusCategory
    outside_contract_window: bool
    past_due_days: int | None


@dataclass(frozen=True)
class ScheduleValues:
    contract_start: date
    contract_end: date
    contract_duration_days: int
    orders: tuple[OrderScheduleValue, ...]
    earliest_order_date: date | None
    latest_order_due_date: date | None
    schedule_span_days: int | None
    outside_contract_count: int
    gap_days: tuple[int, ...]
    overlap_days: tuple[int, ...]


def calculate_schedule(
    *,
    contract: DatasetRecord,
    orders: tuple[DatasetRecord, ...],
    as_of_date: date | None,
) -> ScheduleValues:
    """Calculate date facts without inferring dependencies or resource conflicts."""
    contract_start = normalize_date(contract.values.get("start_date"))
    contract_end = normalize_date(contract.values.get("end_date"))
    order_values: list[OrderScheduleValue] = []
    for order in orders:
        start = normalize_date(order.values.get("order_date"))
        due = normalize_date(order.values.get("due_date"))
        status = str(order.values.get("status"))
        category = classify_source_status(status)
        open_categories = {
            OperationsSourceStatusCategory.ACTIVE_SOURCE_STATUS,
            OperationsSourceStatusCategory.PLANNED_SOURCE_STATUS,
            OperationsSourceStatusCategory.SOURCE_PENDING_STATUS,
            OperationsSourceStatusCategory.SOURCE_FLAGGED_STATUS,
        }
        past_due = (
            max((as_of_date - due).days, 0)
            if as_of_date is not None and category in open_categories
            else None
        )
        order_values.append(
            OrderScheduleValue(
                record=order,
                order_date=start,
                due_date=due,
                duration_days=inclusive_days(start, due),
                source_status=status,
                status_category=category,
                outside_contract_window=start < contract_start or due > contract_end,
                past_due_days=past_due,
            )
        )
    ordered = tuple(
        sorted(
            order_values, key=lambda item: (item.order_date, item.due_date, item.record.record_id)
        )
    )
    earliest = ordered[0].order_date if ordered else None
    latest = max((item.due_date for item in ordered), default=None)
    span = inclusive_days(earliest, latest) if earliest is not None and latest is not None else None
    gaps: list[int] = []
    overlaps: list[int] = []
    current_end: date | None = None
    for item in ordered:
        if current_end is not None:
            delta = (item.order_date - current_end).days
            if delta > 1:
                gaps.append(delta - 1)
            elif delta <= 0:
                overlaps.append(1 - delta)
        current_end = max(current_end, item.due_date) if current_end else item.due_date
    return ScheduleValues(
        contract_start=contract_start,
        contract_end=contract_end,
        contract_duration_days=inclusive_days(contract_start, contract_end),
        orders=ordered,
        earliest_order_date=earliest,
        latest_order_due_date=latest,
        schedule_span_days=span,
        outside_contract_count=sum(item.outside_contract_window for item in ordered),
        gap_days=tuple(gaps),
        overlap_days=tuple(overlaps),
    )
