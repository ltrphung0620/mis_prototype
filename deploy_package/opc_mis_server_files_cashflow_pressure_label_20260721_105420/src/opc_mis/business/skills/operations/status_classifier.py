"""Neutral classification of exact source order status values."""

from opc_mis.domain.enums import OperationsSourceStatusCategory

STATUS_CATEGORIES = {
    "delivered": OperationsSourceStatusCategory.COMPLETED_SOURCE_STATUS,
    "in progress": OperationsSourceStatusCategory.ACTIVE_SOURCE_STATUS,
    "planned": OperationsSourceStatusCategory.PLANNED_SOURCE_STATUS,
    "pending approval": OperationsSourceStatusCategory.SOURCE_PENDING_STATUS,
    "at risk": OperationsSourceStatusCategory.SOURCE_FLAGGED_STATUS,
}


def classify_source_status(status: str) -> OperationsSourceStatusCategory:
    """Classify a source label without turning it into a Risk Agent finding."""
    return STATUS_CATEGORIES.get(
        " ".join(status.split()).casefold(),
        OperationsSourceStatusCategory.UNCLASSIFIED_SOURCE_STATUS,
    )
