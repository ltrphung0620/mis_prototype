"""Deterministic Finance narrative used when model composition is unavailable."""

from opc_mis.domain.enums import FinanceMetric, FinanceNarrativeSource
from opc_mis.domain.finance_models import (
    FinanceComposerInput,
    FinanceNarrative,
    FinanceNarrativeComposition,
    FinanceNarrativeStatement,
)
from opc_mis.domain.lineage import deterministic_id
from opc_mis.infrastructure.openai.narrative_guard import (
    founder_display_value,
    validate_narrative,
)


class DeterministicFinanceNarrativeComposer:
    """Compose stable prose using no calculation and no downstream decisions."""

    model_name = "deterministic-template"
    prompt_version = "finance-narrative-v3"

    async def compose(
        self,
        payload: FinanceComposerInput,
        *,
        fallback_reason: str | None = None,
    ) -> FinanceNarrativeComposition:
        by_metric = {fact.metric: fact for fact in payload.facts}
        statements: list[FinanceNarrativeStatement] = []

        def add(text: str, metrics: tuple[FinanceMetric, ...]) -> None:
            fact_ids = tuple(by_metric[metric].fact_id for metric in metrics)
            statements.append(
                FinanceNarrativeStatement(
                    statement_id=deterministic_id("FNS", text, fact_ids),
                    text=text,
                    fact_ids=fact_ids,
                )
            )

        def display(metric: FinanceMetric) -> str:
            return founder_display_value(by_metric[metric])

        if FinanceMetric.CONTRACT_VALUE in by_metric:
            add(
                f"Giá trị hợp đồng là {display(FinanceMetric.CONTRACT_VALUE)}.",
                (FinanceMetric.CONTRACT_VALUE,),
            )
        coverage_metrics = (
            FinanceMetric.ORDER_REVENUE_TOTAL,
            FinanceMetric.ORDER_COVERAGE_RATIO,
            FinanceMetric.UNCOVERED_CONTRACT_VALUE,
        )
        if all(metric in by_metric for metric in coverage_metrics):
            add(
                "Các đơn hàng liên quan ghi nhận "
                f"{display(FinanceMetric.ORDER_REVENUE_TOTAL)}, tương đương "
                f"{display(FinanceMetric.ORDER_COVERAGE_RATIO)} giá trị hợp đồng; "
                f"{display(FinanceMetric.UNCOVERED_CONTRACT_VALUE)} chưa được bao phủ "
                "bởi các đơn hàng đã liên kết.",
                coverage_metrics,
            )
        margin_metrics = (
            FinanceMetric.ORDER_GROSS_MARGIN,
            FinanceMetric.OPC_TARGET_GROSS_MARGIN,
        )
        if all(metric in by_metric for metric in margin_metrics):
            add(
                f"Biên lợi nhuận tổng hợp từ đơn hàng là "
                f"{display(FinanceMetric.ORDER_GROSS_MARGIN)}, so với mục tiêu OPC "
                f"{display(FinanceMetric.OPC_TARGET_GROSS_MARGIN)}.",
                margin_metrics,
            )
        invoice_metrics = (
            FinanceMetric.INVOICE_TOTAL,
            FinanceMetric.NOT_ISSUED_INVOICE_TOTAL,
            FinanceMetric.OUTSTANDING_ISSUED_RECEIVABLE,
        )
        if all(metric in by_metric for metric in invoice_metrics):
            add(
                f"Hồ sơ có {display(FinanceMetric.INVOICE_TOTAL)} giá trị hóa đơn liên quan; "
                f"{display(FinanceMetric.NOT_ISSUED_INVOICE_TOTAL)} chưa được phát hành và "
                f"khoản phải thu đã phát hành còn tồn đọng là "
                f"{display(FinanceMetric.OUTSTANDING_ISSUED_RECEIVABLE)}.",
                invoice_metrics,
            )
        cash_metrics = (
            FinanceMetric.WORST_RESERVE_GAP,
            FinanceMetric.WORST_RESERVE_GAP_MONTH,
            FinanceMetric.NEGATIVE_NET_CASHFLOW_MONTH_COUNT,
        )
        if all(metric in by_metric for metric in cash_metrics):
            add(
                f"Dự báo chung của OPC ghi nhận mức thiếu hụt dự trữ lớn nhất "
                f"{display(FinanceMetric.WORST_RESERVE_GAP)} tại kỳ "
                f"{display(FinanceMetric.WORST_RESERVE_GAP_MONTH)} và có "
                f"{display(FinanceMetric.NEGATIVE_NET_CASHFLOW_MONTH_COUNT)} kỳ dòng tiền "
                "ròng âm.",
                cash_metrics,
            )
        narrative = FinanceNarrative(
            headline="Tóm tắt điều hành tài chính từ dữ liệu đã xác minh",
            statements=tuple(statements),
        )
        validate_narrative(narrative, payload)
        return FinanceNarrativeComposition(
            narrative=narrative,
            source=FinanceNarrativeSource.DETERMINISTIC_FALLBACK,
            model=self.model_name,
            prompt_version=self.prompt_version,
            fallback_reason=fallback_reason,
        )
