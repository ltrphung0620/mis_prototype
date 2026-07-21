"""Build deterministic Operations facts with complete evidence lineage."""

from dataclasses import dataclass
from numbers import Real
from typing import Any

from opc_mis.business.skills.operations.context_loader import OperationsContext
from opc_mis.business.skills.operations.schedule_engine import ScheduleValues, calculate_schedule
from opc_mis.domain.dataset import DatasetRecord
from opc_mis.domain.enums import (
    OperationsCalculation,
    OperationsDataScope,
    OperationsFactQuality,
    OperationsMetric,
    OperationsSourceStatusCategory,
    OperationsUnit,
)
from opc_mis.domain.evidence import EvidenceRef
from opc_mis.domain.lineage import LineageFactory, deterministic_id
from opc_mis.domain.operations_models import OperationsFact, OrderScheduleFact, SourceOrderNote
from opc_mis.domain.team_pack import SheetRegistry


@dataclass(frozen=True)
class OperationsFactBuild:
    facts: tuple[OperationsFact, ...]
    order_schedules: tuple[OrderScheduleFact, ...]
    source_notes: tuple[SourceOrderNote, ...]
    evidence_refs: tuple[EvidenceRef, ...]


class _FactCollector:
    def __init__(self, case_id: str, lineage: LineageFactory) -> None:
        self._case_id = case_id
        self._lineage = lineage
        self.facts: list[OperationsFact] = []
        self.evidence: dict[str, EvidenceRef] = {}

    def source(
        self,
        *,
        metric: OperationsMetric,
        value: Any,
        unit: OperationsUnit,
        scope: OperationsDataScope,
        record: DatasetRecord,
        field: str,
        quality: OperationsFactQuality = OperationsFactQuality.VERIFIED,
        note: str | None = None,
    ) -> OperationsFact:
        evidence = self._lineage.record_field(record, field)
        self.evidence[evidence.evidence_id] = evidence
        return self._append(
            metric=metric,
            value=value,
            unit=unit,
            scope=scope,
            quality=quality,
            calculation=OperationsCalculation.SOURCE_VALUE,
            evidence=evidence,
            source_ids=(evidence.evidence_id,),
            note=note,
        )

    def derived(
        self,
        *,
        metric: OperationsMetric,
        value: Any,
        unit: OperationsUnit,
        calculation: OperationsCalculation,
        sources: tuple[EvidenceRef, ...],
        scope: OperationsDataScope = OperationsDataScope.CASE_SPECIFIC,
        quality: OperationsFactQuality = OperationsFactQuality.VERIFIED,
        note: str | None = None,
    ) -> OperationsFact:
        ordered = tuple({item.evidence_id: item for item in sources}.values())
        ordered = tuple(sorted(ordered, key=lambda item: item.evidence_id))
        for item in ordered:
            self.evidence[item.evidence_id] = item
        evidence = self._lineage.derived(
            sheet="OPERATIONS_FACTS",
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

    def add_evidence(self, evidence: EvidenceRef) -> None:
        self.evidence[evidence.evidence_id] = evidence

    def _append(
        self,
        *,
        metric: OperationsMetric,
        value: Any,
        unit: OperationsUnit,
        scope: OperationsDataScope,
        quality: OperationsFactQuality,
        calculation: OperationsCalculation,
        evidence: EvidenceRef,
        source_ids: tuple[str, ...],
        note: str | None,
    ) -> OperationsFact:
        fact = OperationsFact(
            fact_id=deterministic_id(
                "OFACT",
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


class OperationsFactBuilder:
    """Create schedule facts only from explicit case relationships."""

    def build(
        self,
        context: OperationsContext,
        lineage: LineageFactory,
        *,
        as_of_date: Any = None,
    ) -> OperationsFactBuild:
        case_id = context.evaluation_case.evaluation_case_id
        collector = _FactCollector(case_id, lineage)
        schedule = calculate_schedule(
            contract=context.contract,
            orders=context.orders,
            as_of_date=as_of_date,
        )
        start_evidence = lineage.record_field(context.contract, "start_date")
        end_evidence = lineage.record_field(context.contract, "end_date")
        collector.source(
            metric=OperationsMetric.CONTRACT_START_DATE,
            value=schedule.contract_start.isoformat(),
            unit=OperationsUnit.DATE,
            scope=OperationsDataScope.CASE_SPECIFIC,
            record=context.contract,
            field="start_date",
        )
        collector.source(
            metric=OperationsMetric.CONTRACT_END_DATE,
            value=schedule.contract_end.isoformat(),
            unit=OperationsUnit.DATE,
            scope=OperationsDataScope.CASE_SPECIFIC,
            record=context.contract,
            field="end_date",
        )
        collector.derived(
            metric=OperationsMetric.CONTRACT_DURATION_DAYS,
            value=schedule.contract_duration_days,
            unit=OperationsUnit.DAYS,
            calculation=OperationsCalculation.DATE_DIFFERENCE_INCLUSIVE,
            sources=(start_evidence, end_evidence),
        )

        order_header = lineage.sheet_headers(
            SheetRegistry.ORDERS.sheet_name,
            context.dataset.headers.get(SheetRegistry.ORDERS.sheet_name, ()),
        )
        order_ids = self._field_evidence(context.orders, "order_id", lineage) or (order_header,)
        order_dates = self._field_evidence(context.orders, "order_date", lineage)
        due_dates = self._field_evidence(context.orders, "due_date", lineage)
        statuses = self._field_evidence(context.orders, "status", lineage)
        schedule_sources = order_dates + due_dates
        no_order_quality = (
            OperationsFactQuality.VERIFIED
            if context.orders
            else OperationsFactQuality.NOT_AVAILABLE
        )
        self._derived(
            collector,
            OperationsMetric.RELATED_ORDER_COUNT,
            len(schedule.orders),
            OperationsUnit.COUNT,
            OperationsCalculation.COUNT,
            order_ids,
        )
        self._derived(
            collector,
            OperationsMetric.EARLIEST_ORDER_DATE,
            schedule.earliest_order_date.isoformat() if schedule.earliest_order_date else None,
            OperationsUnit.DATE,
            OperationsCalculation.MIN_DATE,
            order_dates or (order_header,),
            quality=no_order_quality,
        )
        self._derived(
            collector,
            OperationsMetric.LATEST_ORDER_DUE_DATE,
            schedule.latest_order_due_date.isoformat() if schedule.latest_order_due_date else None,
            OperationsUnit.DATE,
            OperationsCalculation.MAX_DATE,
            due_dates or (order_header,),
            quality=no_order_quality,
        )
        self._derived(
            collector,
            OperationsMetric.ORDER_SCHEDULE_SPAN_DAYS,
            schedule.schedule_span_days,
            OperationsUnit.DAYS,
            OperationsCalculation.DATE_DIFFERENCE_INCLUSIVE,
            schedule_sources or (order_header,),
            quality=no_order_quality,
        )
        self._derived(
            collector,
            OperationsMetric.ORDER_OUTSIDE_CONTRACT_WINDOW_COUNT,
            schedule.outside_contract_count,
            OperationsUnit.COUNT,
            OperationsCalculation.COUNT,
            (*schedule_sources, start_evidence, end_evidence),
        )
        self._derived(
            collector,
            OperationsMetric.ORDER_INTERVAL_GAP_COUNT,
            len(schedule.gap_days),
            OperationsUnit.COUNT,
            OperationsCalculation.INTERVAL_GAP,
            schedule_sources or (order_header,),
        )
        self._derived(
            collector,
            OperationsMetric.MAX_ORDER_INTERVAL_GAP_DAYS,
            max(schedule.gap_days, default=0),
            OperationsUnit.DAYS,
            OperationsCalculation.MAX,
            schedule_sources or (order_header,),
        )
        self._derived(
            collector,
            OperationsMetric.ORDER_INTERVAL_OVERLAP_COUNT,
            len(schedule.overlap_days),
            OperationsUnit.COUNT,
            OperationsCalculation.INTERVAL_OVERLAP,
            schedule_sources or (order_header,),
        )
        self._derived(
            collector,
            OperationsMetric.MAX_ORDER_INTERVAL_OVERLAP_DAYS,
            max(schedule.overlap_days, default=0),
            OperationsUnit.DAYS,
            OperationsCalculation.MAX,
            schedule_sources or (order_header,),
        )

        categories = {
            OperationsMetric.SOURCE_COMPLETED_ORDER_COUNT: (
                OperationsSourceStatusCategory.COMPLETED_SOURCE_STATUS
            ),
            OperationsMetric.SOURCE_ACTIVE_ORDER_COUNT: (
                OperationsSourceStatusCategory.ACTIVE_SOURCE_STATUS
            ),
            OperationsMetric.SOURCE_PLANNED_ORDER_COUNT: (
                OperationsSourceStatusCategory.PLANNED_SOURCE_STATUS
            ),
            OperationsMetric.SOURCE_PENDING_ORDER_COUNT: (
                OperationsSourceStatusCategory.SOURCE_PENDING_STATUS
            ),
            OperationsMetric.SOURCE_FLAGGED_ORDER_COUNT: (
                OperationsSourceStatusCategory.SOURCE_FLAGGED_STATUS
            ),
            OperationsMetric.UNCLASSIFIED_ORDER_STATUS_COUNT: (
                OperationsSourceStatusCategory.UNCLASSIFIED_SOURCE_STATUS
            ),
        }
        for metric, category in categories.items():
            self._derived(
                collector,
                metric,
                sum(item.status_category is category for item in schedule.orders),
                OperationsUnit.COUNT,
                OperationsCalculation.COUNT,
                statuses or (order_header,),
            )

        as_of_evidence = None
        if as_of_date is not None:
            as_of_evidence = lineage.user_input(
                record_id=case_id,
                field="as_of_date",
                display=as_of_date.isoformat(),
            )
            collector.add_evidence(as_of_evidence)
        past_due_values = tuple(
            item.past_due_days
            for item in schedule.orders
            if item.past_due_days is not None and item.past_due_days > 0
        )
        past_due_sources = due_dates + statuses
        if as_of_evidence is not None:
            past_due_sources += (as_of_evidence,)
        self._derived(
            collector,
            OperationsMetric.OPEN_PAST_DUE_ORDER_COUNT,
            len(past_due_values) if as_of_date is not None else None,
            OperationsUnit.COUNT,
            OperationsCalculation.COUNT,
            past_due_sources or (order_header,),
            quality=(
                OperationsFactQuality.VERIFIED
                if as_of_date is not None
                else OperationsFactQuality.NOT_AVAILABLE
            ),
        )
        self._derived(
            collector,
            OperationsMetric.MAX_OPEN_PAST_DUE_DAYS,
            max(past_due_values, default=0) if as_of_date is not None else None,
            OperationsUnit.DAYS,
            OperationsCalculation.MAX,
            past_due_sources or (order_header,),
            quality=(
                OperationsFactQuality.VERIFIED
                if as_of_date is not None
                else OperationsFactQuality.NOT_AVAILABLE
            ),
        )

        notes = self._source_notes(schedule, lineage, collector)
        self._derived(
            collector,
            OperationsMetric.SOURCE_DELIVERY_NOTE_COUNT,
            len(notes),
            OperationsUnit.COUNT,
            OperationsCalculation.COUNT,
            tuple(lineage.record_field(item.record, "delivery_note") for item in schedule.orders)
            or (order_header,),
        )
        self._add_penalty_rate(context, collector)
        order_schedules = self._order_schedules(schedule, lineage, collector, as_of_evidence)
        return OperationsFactBuild(
            facts=tuple(collector.facts),
            order_schedules=order_schedules,
            source_notes=notes,
            evidence_refs=tuple(collector.evidence[key] for key in sorted(collector.evidence)),
        )

    @staticmethod
    def _derived(
        collector: _FactCollector,
        metric: OperationsMetric,
        value: Any,
        unit: OperationsUnit,
        calculation: OperationsCalculation,
        sources: tuple[EvidenceRef, ...],
        *,
        quality: OperationsFactQuality = OperationsFactQuality.VERIFIED,
    ) -> None:
        collector.derived(
            metric=metric,
            value=value,
            unit=unit,
            calculation=calculation,
            sources=sources,
            quality=quality,
        )

    @staticmethod
    def _field_evidence(
        records: tuple[DatasetRecord, ...],
        field: str,
        lineage: LineageFactory,
    ) -> tuple[EvidenceRef, ...]:
        return tuple(lineage.record_field(record, field) for record in records)

    @staticmethod
    def _source_notes(
        schedule: ScheduleValues,
        lineage: LineageFactory,
        collector: _FactCollector,
    ) -> tuple[SourceOrderNote, ...]:
        notes: list[SourceOrderNote] = []
        for item in schedule.orders:
            raw = item.record.values.get("delivery_note")
            if raw is None or not str(raw).strip():
                continue
            evidence = lineage.record_field(item.record, "delivery_note")
            collector.add_evidence(evidence)
            notes.append(
                SourceOrderNote(
                    order_id=item.record.record_id,
                    text=str(raw),
                    evidence_id=evidence.evidence_id,
                )
            )
        return tuple(notes)

    @staticmethod
    def _order_schedules(
        schedule: ScheduleValues,
        lineage: LineageFactory,
        collector: _FactCollector,
        as_of_evidence: EvidenceRef | None,
    ) -> tuple[OrderScheduleFact, ...]:
        results: list[OrderScheduleFact] = []
        for item in schedule.orders:
            sources = tuple(
                lineage.record_field(item.record, field)
                for field in ("order_id", "order_date", "due_date", "status")
            )
            if as_of_evidence is not None:
                sources += (as_of_evidence,)
            for source in sources:
                collector.add_evidence(source)
            derived = lineage.derived(
                sheet="OPERATIONS_FACTS",
                record_id=item.record.record_id,
                field="order_schedule",
                display={
                    "order_date": item.order_date.isoformat(),
                    "due_date": item.due_date.isoformat(),
                    "planned_duration_days": item.duration_days,
                    "source_status": item.source_status,
                    "status_category": item.status_category,
                    "outside_contract_window": item.outside_contract_window,
                    "past_due_days": item.past_due_days,
                },
                sources=sources,
            )
            collector.add_evidence(derived)
            results.append(
                OrderScheduleFact(
                    order_id=item.record.record_id,
                    order_date=item.order_date,
                    due_date=item.due_date,
                    planned_duration_days=item.duration_days,
                    source_status=item.source_status,
                    status_category=item.status_category,
                    outside_contract_window=item.outside_contract_window,
                    past_due_days=item.past_due_days,
                    evidence_ids=(
                        *tuple(source.evidence_id for source in sources),
                        derived.evidence_id,
                    ),
                )
            )
        return tuple(results)

    @staticmethod
    def _add_penalty_rate(context: OperationsContext, collector: _FactCollector) -> None:
        records = context.dataset.lookup(SheetRegistry.OPC_PROFILE, "late_delivery_penalty_rate")
        if len(records) != 1:
            return
        value = records[0].values.get("value")
        if isinstance(value, bool) or not isinstance(value, Real):
            return
        collector.source(
            metric=OperationsMetric.OPC_LATE_DELIVERY_PENALTY_RATE,
            value=float(value),
            unit=OperationsUnit.RATIO,
            scope=OperationsDataScope.OPC_GLOBAL,
            record=records[0],
            field="value",
            note="OPC-level reference only; no penalty amount is calculated.",
        )
