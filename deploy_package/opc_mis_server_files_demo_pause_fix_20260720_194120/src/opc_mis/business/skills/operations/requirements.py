"""Blocking Operations input requirements; risk and capacity inputs are excluded."""

from dataclasses import dataclass

from opc_mis.business.skills.operations.date_normalizer import normalize_date
from opc_mis.domain.dataset import DatasetRecord
from opc_mis.domain.evidence import EvidenceRef
from opc_mis.domain.lineage import LineageFactory


@dataclass(frozen=True)
class OperationsRequirementFailure:
    """One blocker for deterministic operational schedule calculations."""

    code: str
    target_record: str
    field: str
    expected_type: str
    reason: str
    evidence_refs: tuple[EvidenceRef, ...] = ()


def validate_operations_records(
    *,
    contract: DatasetRecord,
    orders: tuple[DatasetRecord, ...],
    lineage: LineageFactory,
) -> tuple[OperationsRequirementFailure, ...]:
    """Validate the exact fields required by Operations schedule engines."""
    failures: list[OperationsRequirementFailure] = []

    def date_value(record: DatasetRecord, field: str, code: str) -> object | None:
        value = record.values.get(field)
        try:
            return normalize_date(value)
        except ValueError:
            failures.append(
                OperationsRequirementFailure(
                    code=code,
                    target_record=record.record_id,
                    field=field,
                    expected_type="date, ISO date text, or positive Excel serial",
                    reason=f"Operations requires a valid {field}.",
                    evidence_refs=(lineage.record_field(record, field),),
                )
            )
            return None

    contract_start = date_value(contract, "start_date", "OPERATIONS_CONTRACT_START_DATE_INVALID")
    contract_end = date_value(contract, "end_date", "OPERATIONS_CONTRACT_END_DATE_INVALID")
    if contract_start is not None and contract_end is not None and contract_end < contract_start:
        failures.append(
            OperationsRequirementFailure(
                code="OPERATIONS_CONTRACT_WINDOW_INVALID",
                target_record=contract.record_id,
                field="end_date",
                expected_type="date on or after contract start_date",
                reason="Contract end_date is before start_date.",
                evidence_refs=(
                    lineage.record_field(contract, "start_date"),
                    lineage.record_field(contract, "end_date"),
                ),
            )
        )
    for order in orders:
        order_start = date_value(order, "order_date", "OPERATIONS_ORDER_DATE_INVALID")
        order_due = date_value(order, "due_date", "OPERATIONS_ORDER_DUE_DATE_INVALID")
        if order_start is not None and order_due is not None and order_due < order_start:
            failures.append(
                OperationsRequirementFailure(
                    code="OPERATIONS_ORDER_WINDOW_INVALID",
                    target_record=order.record_id,
                    field="due_date",
                    expected_type="date on or after order_date",
                    reason="Order due_date is before order_date.",
                    evidence_refs=(
                        lineage.record_field(order, "order_date"),
                        lineage.record_field(order, "due_date"),
                    ),
                )
            )
        status = order.values.get("status")
        if not isinstance(status, str) or not status.strip():
            failures.append(
                OperationsRequirementFailure(
                    code="OPERATIONS_ORDER_STATUS_MISSING",
                    target_record=order.record_id,
                    field="status",
                    expected_type="non-empty source status text",
                    reason="Operations requires the source status for each selected order.",
                    evidence_refs=(lineage.record_field(order, "status"),),
                )
            )
    unique = {(item.code, item.target_record, item.field): item for item in failures}
    return tuple(unique[key] for key in sorted(unique))
