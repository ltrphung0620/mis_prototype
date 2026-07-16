"""Deterministic Finance narrative used when model composition is unavailable."""

from opc_mis.domain.enums import FinanceMetric, FinanceNarrativeSource
from opc_mis.domain.finance_models import (
    FinanceComposerInput,
    FinanceNarrative,
    FinanceNarrativeComposition,
    FinanceNarrativeStatement,
)
from opc_mis.domain.lineage import deterministic_id


class DeterministicFinanceNarrativeComposer:
    """Compose stable prose using no calculation and no downstream decisions."""

    model_name = "deterministic-template"
    prompt_version = "finance-narrative-v1"

    async def compose(
        self,
        payload: FinanceComposerInput,
        *,
        fallback_reason: str | None = None,
    ) -> FinanceNarrativeComposition:
        by_metric = {fact.metric: fact for fact in payload.facts}
        groups = (
            (
                "Hợp đồng và biên lợi nhuận nguồn đã được ghi nhận từ dữ liệu đầu vào.",
                (FinanceMetric.CONTRACT_VALUE, FinanceMetric.CONTRACT_GROSS_MARGIN_SOURCE),
            ),
            (
                "Kết quả tổng hợp đơn hàng phản ánh đúng các quan hệ đã được Planner chọn.",
                (
                    FinanceMetric.ORDER_REVENUE_TOTAL,
                    FinanceMetric.ORDER_ESTIMATED_COST_TOTAL,
                    FinanceMetric.ORDER_GROSS_MARGIN,
                ),
            ),
            (
                "Tình trạng hóa đơn được tổng hợp theo trạng thái nguồn và không "
                "giả định thời điểm đánh giá.",
                (FinanceMetric.INVOICE_TOTAL, FinanceMetric.OUTSTANDING_ISSUED_RECEIVABLE),
            ),
            (
                "Dòng tiền hiện chỉ phản ánh dự báo chung của OPC và không được quy cho hợp đồng.",
                (FinanceMetric.WORST_RESERVE_GAP, FinanceMetric.NEGATIVE_NET_CASHFLOW_MONTH_COUNT),
            ),
        )
        statements: list[FinanceNarrativeStatement] = []
        for text, metrics in groups:
            fact_ids = tuple(by_metric[metric].fact_id for metric in metrics if metric in by_metric)
            if not fact_ids:
                continue
            statements.append(
                FinanceNarrativeStatement(
                    statement_id=deterministic_id("FNS", text, fact_ids),
                    text=text,
                    fact_ids=fact_ids,
                )
            )
        return FinanceNarrativeComposition(
            narrative=FinanceNarrative(
                headline="Tổng hợp tài chính dựa trên các dữ kiện đã xác minh",
                statements=tuple(statements),
            ),
            source=FinanceNarrativeSource.DETERMINISTIC_FALLBACK,
            model=self.model_name,
            prompt_version=self.prompt_version,
            fallback_reason=fallback_reason,
        )
