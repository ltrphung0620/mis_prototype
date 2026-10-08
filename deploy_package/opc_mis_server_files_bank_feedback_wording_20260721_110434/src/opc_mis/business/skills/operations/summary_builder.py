"""Create deterministic Operations summaries from verified fact references."""

from opc_mis.domain.enums import OperationsMetric
from opc_mis.domain.lineage import deterministic_id
from opc_mis.domain.operations_models import OperationsFact, OperationsSummaryStatement


def build_operations_summary(
    case_id: str,
    facts: tuple[OperationsFact, ...],
) -> tuple[OperationsSummaryStatement, ...]:
    """Summarize facts without adding conclusions, severity, or recommendations."""
    by_metric = {fact.metric: fact for fact in facts}

    def statement(text: str, metrics: tuple[OperationsMetric, ...]) -> OperationsSummaryStatement:
        selected = tuple(by_metric[metric] for metric in metrics)
        fact_ids = tuple(item.fact_id for item in selected)
        return OperationsSummaryStatement(
            statement_id=deterministic_id("OSTM", case_id, text, fact_ids),
            text=text,
            fact_ids=fact_ids,
        )

    order_count = by_metric[OperationsMetric.RELATED_ORDER_COUNT].value
    span = by_metric[OperationsMetric.ORDER_SCHEDULE_SPAN_DAYS].value
    schedule_text = (
        f"The case contains {order_count} explicitly related order(s); "
        f"the planned schedule span is {span} day(s)."
        if span is not None
        else (
            f"The case contains {order_count} explicitly related order(s); "
            "no schedule span is available."
        )
    )
    completed = by_metric[OperationsMetric.SOURCE_COMPLETED_ORDER_COUNT].value
    active = by_metric[OperationsMetric.SOURCE_ACTIVE_ORDER_COUNT].value
    planned = by_metric[OperationsMetric.SOURCE_PLANNED_ORDER_COUNT].value
    pending = by_metric[OperationsMetric.SOURCE_PENDING_ORDER_COUNT].value
    flagged = by_metric[OperationsMetric.SOURCE_FLAGGED_ORDER_COUNT].value
    status_text = (
        "Source status counts are: "
        f"completed={completed}, active={active}, planned={planned}, "
        f"pending={pending}, flagged={flagged}."
    )
    return (
        statement(
            schedule_text,
            (
                OperationsMetric.RELATED_ORDER_COUNT,
                OperationsMetric.ORDER_SCHEDULE_SPAN_DAYS,
            ),
        ),
        statement(
            status_text,
            (
                OperationsMetric.SOURCE_COMPLETED_ORDER_COUNT,
                OperationsMetric.SOURCE_ACTIVE_ORDER_COUNT,
                OperationsMetric.SOURCE_PLANNED_ORDER_COUNT,
                OperationsMetric.SOURCE_PENDING_ORDER_COUNT,
                OperationsMetric.SOURCE_FLAGGED_ORDER_COUNT,
            ),
        ),
    )
