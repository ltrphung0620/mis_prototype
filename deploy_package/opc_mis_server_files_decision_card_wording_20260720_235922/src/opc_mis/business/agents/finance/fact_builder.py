"""Build typed Finance facts and complete deterministic evidence lineage."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from opc_mis.business.agents.finance.cashflow import calculate_cashflow
from opc_mis.business.agents.finance.context_loader import FinanceContext
from opc_mis.business.agents.finance.profitability import calculate_profitability
from opc_mis.business.agents.finance.receivables import calculate_receivables
from opc_mis.business.agents.finance.requirements import numeric_value
from opc_mis.domain.dataset import DatasetRecord
from opc_mis.domain.enums import (
    FinanceCalculation,
    FinanceDataScope,
    FinanceFactQuality,
    FinanceMetric,
    FinanceUnit,
)
from opc_mis.domain.evidence import EvidenceRef
from opc_mis.domain.finance_models import FinanceFact
from opc_mis.domain.lineage import LineageFactory, deterministic_id
from opc_mis.domain.team_pack import SheetRegistry


@dataclass(frozen=True)
class FinanceFactBuild:
    facts: tuple[FinanceFact, ...]
    evidence_refs: tuple[EvidenceRef, ...]


class _FactCollector:
    def __init__(self, case_id: str, lineage: LineageFactory) -> None:
        self._case_id = case_id
        self._lineage = lineage
        self.facts: list[FinanceFact] = []
        self.evidence: dict[str, EvidenceRef] = {}

    def source(
        self,
        *,
        metric: FinanceMetric,
        value: Any,
        unit: FinanceUnit,
        scope: FinanceDataScope,
        record: DatasetRecord,
        field: str,
        quality: FinanceFactQuality = FinanceFactQuality.VERIFIED,
        note: str | None = None,
    ) -> FinanceFact:
        evidence = self._lineage.record_field(record, field)
        self.evidence[evidence.evidence_id] = evidence
        return self._append(
            metric=metric,
            value=value,
            unit=unit,
            scope=scope,
            quality=quality,
            calculation=FinanceCalculation.SOURCE_VALUE,
            evidence=evidence,
            source_ids=(evidence.evidence_id,),
            note=note,
        )

    def derived(
        self,
        *,
        metric: FinanceMetric,
        value: Any,
        unit: FinanceUnit,
        scope: FinanceDataScope,
        calculation: FinanceCalculation,
        sources: tuple[EvidenceRef, ...],
        quality: FinanceFactQuality = FinanceFactQuality.VERIFIED,
        note: str | None = None,
    ) -> FinanceFact:
        unique = {item.evidence_id: item for item in sources}
        ordered = tuple(unique[key] for key in sorted(unique))
        for item in ordered:
            self.evidence[item.evidence_id] = item
        evidence = self._lineage.derived(
            sheet="FINANCE_FACTS",
            record_id=self._case_id,
            field=metric.value,
            display=value,
            sources=ordered,
        )
        self.evidence[evidence.evidence_id] = evidence
        return self._append(
            metric=metric,
            value=value,
            unit=unit,
            scope=scope,
            quality=quality,
            calculation=calculation,
            evidence=evidence,
            source_ids=tuple(item.evidence_id for item in ordered),
            note=note,
        )

    def _append(
        self,
        *,
        metric: FinanceMetric,
        value: Any,
        unit: FinanceUnit,
        scope: FinanceDataScope,
        quality: FinanceFactQuality,
        calculation: FinanceCalculation,
        evidence: EvidenceRef,
        source_ids: tuple[str, ...],
        note: str | None,
    ) -> FinanceFact:
        fact = FinanceFact(
            fact_id=deterministic_id(
                "FACT",
                self._case_id,
                metric,
                value,
                unit,
                scope,
                calculation,
                source_ids,
            ),
            metric=metric,
            value=value,
            unit=unit,
            scope=scope,
            quality=quality,
            calculation=calculation,
            evidence_id=evidence.evidence_id,
            source_evidence_ids=source_ids,
            note=note,
        )
        self.facts.append(fact)
        return fact


class FinanceFactBuilder:
    """Create all authoritative Finance facts from explicit case relationships."""

    def build(self, context: FinanceContext, lineage: LineageFactory) -> FinanceFactBuild:
        case_id = context.evaluation_case.evaluation_case_id
        collector = _FactCollector(case_id, lineage)
        contract = context.contract
        contract_value = numeric_value(contract, "contract_value")
        contract_margin = numeric_value(contract, "gross_margin")
        if contract_value is None or contract_margin is None:
            raise ValueError("Finance record requirements must pass before fact building")
        collector.source(
            metric=FinanceMetric.CONTRACT_VALUE,
            value=contract_value,
            unit=FinanceUnit.VND,
            scope=FinanceDataScope.CASE_SPECIFIC,
            record=contract,
            field="contract_value",
        )
        collector.source(
            metric=FinanceMetric.CONTRACT_GROSS_MARGIN_SOURCE,
            value=contract_margin,
            unit=FinanceUnit.RATIO,
            scope=FinanceDataScope.CASE_SPECIFIC,
            record=contract,
            field="gross_margin",
            note="Source contract field; not recalculated from orders.",
        )
        target_records = context.dataset.lookup(SheetRegistry.OPC_PROFILE, "target_gross_margin")
        if len(target_records) == 1 and numeric_value(target_records[0], "value") is not None:
            collector.source(
                metric=FinanceMetric.OPC_TARGET_GROSS_MARGIN,
                value=numeric_value(target_records[0], "value"),
                unit=FinanceUnit.RATIO,
                scope=FinanceDataScope.OPC_GLOBAL,
                record=target_records[0],
                field="value",
            )

        order_id_sources = self._field_evidence(context.orders, "order_id", lineage)
        revenue_sources = self._field_evidence(context.orders, "order_revenue", lineage)
        cost_sources = self._field_evidence(context.orders, "estimated_cost", lineage)
        contract_value_source = (lineage.record_field(contract, "contract_value"),)
        profitability = calculate_profitability(contract, context.orders)
        collector.derived(
            metric=FinanceMetric.RELATED_ORDER_COUNT,
            value=profitability.order_count,
            unit=FinanceUnit.COUNT,
            scope=FinanceDataScope.CASE_SPECIFIC,
            calculation=FinanceCalculation.COUNT,
            sources=order_id_sources,
        )
        collector.derived(
            metric=FinanceMetric.ORDER_REVENUE_TOTAL,
            value=profitability.revenue_total,
            unit=FinanceUnit.VND,
            scope=FinanceDataScope.CASE_SPECIFIC,
            calculation=FinanceCalculation.SUM,
            sources=revenue_sources,
        )
        collector.derived(
            metric=FinanceMetric.ORDER_ESTIMATED_COST_TOTAL,
            value=profitability.estimated_cost_total,
            unit=FinanceUnit.VND,
            scope=FinanceDataScope.CASE_SPECIFIC,
            calculation=FinanceCalculation.SUM,
            sources=cost_sources,
        )
        collector.derived(
            metric=FinanceMetric.ORDER_GROSS_PROFIT,
            value=profitability.gross_profit,
            unit=FinanceUnit.VND,
            scope=FinanceDataScope.CASE_SPECIFIC,
            calculation=FinanceCalculation.DIFFERENCE,
            sources=revenue_sources + cost_sources,
        )
        collector.derived(
            metric=FinanceMetric.ORDER_GROSS_MARGIN,
            value=profitability.gross_margin,
            unit=FinanceUnit.RATIO,
            scope=FinanceDataScope.CASE_SPECIFIC,
            calculation=FinanceCalculation.SAFE_RATIO,
            sources=revenue_sources + cost_sources,
            quality=(
                FinanceFactQuality.VERIFIED
                if profitability.gross_margin is not None
                else FinanceFactQuality.NOT_AVAILABLE
            ),
        )
        collector.derived(
            metric=FinanceMetric.ORDER_COVERAGE_RATIO,
            value=profitability.order_coverage_ratio,
            unit=FinanceUnit.RATIO,
            scope=FinanceDataScope.CASE_SPECIFIC,
            calculation=FinanceCalculation.SAFE_RATIO,
            sources=revenue_sources + contract_value_source,
        )
        collector.derived(
            metric=FinanceMetric.UNCOVERED_CONTRACT_VALUE,
            value=profitability.uncovered_contract_value,
            unit=FinanceUnit.VND,
            scope=FinanceDataScope.CASE_SPECIFIC,
            calculation=FinanceCalculation.MAX_NON_NEGATIVE_DIFFERENCE,
            sources=revenue_sources + contract_value_source,
        )

        invoice_id_sources = self._field_evidence(context.invoices, "invoice_id", lineage)
        amount_sources = self._field_evidence(context.invoices, "invoice_amount", lineage)
        status_sources = self._field_evidence(context.invoices, "status", lineage)
        receivables = calculate_receivables(contract, context.invoices)
        invoice_specs = (
            (
                FinanceMetric.RELATED_INVOICE_COUNT,
                receivables.invoice_count,
                FinanceUnit.COUNT,
                FinanceCalculation.COUNT,
                invoice_id_sources,
            ),
            (
                FinanceMetric.INVOICE_TOTAL,
                receivables.invoice_total,
                FinanceUnit.VND,
                FinanceCalculation.SUM,
                amount_sources,
            ),
            (
                FinanceMetric.PAID_INVOICE_TOTAL,
                receivables.paid_total,
                FinanceUnit.VND,
                FinanceCalculation.SUM,
                amount_sources + status_sources,
            ),
            (
                FinanceMetric.OPEN_INVOICE_TOTAL,
                receivables.open_total,
                FinanceUnit.VND,
                FinanceCalculation.SUM,
                amount_sources + status_sources,
            ),
            (
                FinanceMetric.NOT_ISSUED_INVOICE_TOTAL,
                receivables.not_issued_total,
                FinanceUnit.VND,
                FinanceCalculation.SUM,
                amount_sources + status_sources,
            ),
            (
                FinanceMetric.OUTSTANDING_ISSUED_RECEIVABLE,
                receivables.outstanding_issued,
                FinanceUnit.VND,
                FinanceCalculation.SUM,
                amount_sources + status_sources,
            ),
            (
                FinanceMetric.INVOICE_COVERAGE_RATIO,
                receivables.invoice_coverage_ratio,
                FinanceUnit.RATIO,
                FinanceCalculation.SAFE_RATIO,
                amount_sources + contract_value_source,
            ),
        )
        for metric, value, unit, calculation, sources in invoice_specs:
            collector.derived(
                metric=metric,
                value=value,
                unit=unit,
                scope=FinanceDataScope.CASE_SPECIFIC,
                calculation=calculation,
                sources=sources,
            )

        cashflow = calculate_cashflow(context.cashflow)
        cash_sources = self._cashflow_evidence(context.cashflow, lineage)
        cash_quality = (
            FinanceFactQuality.VERIFIED
            if cashflow.month_count
            else FinanceFactQuality.NOT_AVAILABLE
        )
        cash_scope = (
            FinanceDataScope.OPC_GLOBAL if cashflow.month_count else FinanceDataScope.NOT_AVAILABLE
        )
        for metric, value, unit, calculation in (
            (
                FinanceMetric.CASHFLOW_MONTH_COUNT,
                cashflow.month_count,
                FinanceUnit.COUNT,
                FinanceCalculation.COUNT,
            ),
            (
                FinanceMetric.WORST_RESERVE_GAP,
                cashflow.worst_reserve_gap,
                FinanceUnit.VND,
                FinanceCalculation.MAX_NON_NEGATIVE_DIFFERENCE,
            ),
            (
                FinanceMetric.WORST_RESERVE_GAP_MONTH,
                cashflow.worst_reserve_gap_month,
                FinanceUnit.TEXT,
                FinanceCalculation.MINIMUM_BY_VALUE,
            ),
            (
                FinanceMetric.NEGATIVE_NET_CASHFLOW_MONTH_COUNT,
                cashflow.negative_net_month_count,
                FinanceUnit.COUNT,
                FinanceCalculation.COUNT,
            ),
        ):
            collector.derived(
                metric=metric,
                value=value,
                unit=unit,
                scope=cash_scope,
                quality=cash_quality,
                calculation=calculation,
                sources=cash_sources,
                note="OPC-level projection; not attributable to this contract.",
            )
        return FinanceFactBuild(
            facts=tuple(collector.facts),
            evidence_refs=tuple(collector.evidence[key] for key in sorted(collector.evidence)),
        )

    @staticmethod
    def _field_evidence(
        records: tuple[DatasetRecord, ...], field: str, lineage: LineageFactory
    ) -> tuple[EvidenceRef, ...]:
        return tuple(lineage.record_field(record, field) for record in records)

    @staticmethod
    def _cashflow_evidence(
        records: tuple[DatasetRecord, ...], lineage: LineageFactory
    ) -> tuple[EvidenceRef, ...]:
        fields = (
            "month",
            "expected_cash_in",
            "expected_cash_out",
            "cash_reserve_minimum",
            "projected_closing_cash",
        )
        return tuple(lineage.record_field(record, field) for record in records for field in fields)
