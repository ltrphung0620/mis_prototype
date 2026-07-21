"""Convert Operations facts into neutral observations and evidence limitations."""

from dataclasses import dataclass

from opc_mis.business.skills.operations.context_loader import OperationsContext
from opc_mis.domain.enums import (
    OperationsDataScope,
    OperationsMetric,
    OperationsObservationCode,
)
from opc_mis.domain.evidence import EvidenceRef
from opc_mis.domain.lineage import LineageFactory, deterministic_id
from opc_mis.domain.operations_models import (
    OperationsEvidenceLimitation,
    OperationsFact,
    OperationsObservation,
    SourceOrderNote,
)
from opc_mis.domain.team_pack import SheetRegistry


@dataclass(frozen=True)
class OperationsConditions:
    observations: tuple[OperationsObservation, ...]
    limitations: tuple[OperationsEvidenceLimitation, ...]
    evidence_refs: tuple[EvidenceRef, ...]


class OperationsConditionAnalyzer:
    """Report source conditions without risk, severity, approval, or feasibility."""

    def analyze(
        self,
        context: OperationsContext,
        facts: tuple[OperationsFact, ...],
        notes: tuple[SourceOrderNote, ...],
        lineage: LineageFactory,
        *,
        has_as_of_date: bool,
    ) -> OperationsConditions:
        case_id = context.evaluation_case.evaluation_case_id
        by_metric = {fact.metric: fact for fact in facts}
        observations: list[OperationsObservation] = []
        limitations: list[OperationsEvidenceLimitation] = []
        evidence: dict[str, EvidenceRef] = {}

        def observe(
            code: OperationsObservationCode,
            title: str,
            detail: str,
            metrics: tuple[OperationsMetric, ...] = (),
            evidence_ids: tuple[str, ...] = (),
        ) -> None:
            selected = tuple(by_metric[metric] for metric in metrics if metric in by_metric)
            linked_evidence = tuple(
                dict.fromkeys(tuple(item.evidence_id for item in selected) + evidence_ids)
            )
            observations.append(
                OperationsObservation(
                    observation_id=deterministic_id("OOBS", case_id, code, linked_evidence),
                    code=code,
                    title=title,
                    detail=detail,
                    fact_ids=tuple(item.fact_id for item in selected),
                    evidence_ids=linked_evidence,
                )
            )

        def value(metric: OperationsMetric) -> int:
            fact_value = by_metric[metric].value
            return fact_value if isinstance(fact_value, int) else 0

        if value(OperationsMetric.SOURCE_FLAGGED_ORDER_COUNT) > 0:
            observe(
                OperationsObservationCode.SOURCE_FLAGGED_ORDER_STATUS_OBSERVED,
                "A source order has a flagged status",
                "The status is preserved from the TeamPack and is not a risk classification.",
                (OperationsMetric.SOURCE_FLAGGED_ORDER_COUNT,),
            )
        if value(OperationsMetric.SOURCE_PENDING_ORDER_COUNT) > 0:
            observe(
                OperationsObservationCode.SOURCE_PENDING_ORDER_STATUS_OBSERVED,
                "A source order has a pending status",
                "The pending label is reported verbatim; Operations does not make approvals.",
                (OperationsMetric.SOURCE_PENDING_ORDER_COUNT,),
            )
        if value(OperationsMetric.ORDER_OUTSIDE_CONTRACT_WINDOW_COUNT) > 0:
            observe(
                OperationsObservationCode.ORDER_OUTSIDE_CONTRACT_WINDOW,
                "An order schedule extends beyond the contract window",
                "At least one explicit order starts before or ends after the contract dates.",
                (OperationsMetric.ORDER_OUTSIDE_CONTRACT_WINDOW_COUNT,),
            )
        if value(OperationsMetric.OPEN_PAST_DUE_ORDER_COUNT) > 0:
            observe(
                OperationsObservationCode.OPEN_ORDER_PAST_DUE,
                "An open source order is past its due date",
                "Past-due days are measured against the caller-provided as-of date.",
                (
                    OperationsMetric.OPEN_PAST_DUE_ORDER_COUNT,
                    OperationsMetric.MAX_OPEN_PAST_DUE_DAYS,
                ),
            )
        if value(OperationsMetric.ORDER_INTERVAL_GAP_COUNT) > 0:
            observe(
                OperationsObservationCode.ORDER_INTERVAL_GAP_OBSERVED,
                "A gap exists between planned order intervals",
                "This is a calendar observation and does not imply a missing phase.",
                (
                    OperationsMetric.ORDER_INTERVAL_GAP_COUNT,
                    OperationsMetric.MAX_ORDER_INTERVAL_GAP_DAYS,
                ),
            )
        if value(OperationsMetric.ORDER_INTERVAL_OVERLAP_COUNT) > 0:
            observe(
                OperationsObservationCode.ORDER_INTERVAL_OVERLAP_OBSERVED,
                "Planned order intervals overlap",
                "This is a calendar observation and does not imply a resource conflict.",
                (
                    OperationsMetric.ORDER_INTERVAL_OVERLAP_COUNT,
                    OperationsMetric.MAX_ORDER_INTERVAL_OVERLAP_DAYS,
                ),
            )
        if notes:
            observe(
                OperationsObservationCode.UNSTRUCTURED_DELIVERY_NOTE_PRESENT,
                "Unstructured source delivery notes are present",
                "Notes are retained verbatim and are not converted into findings.",
                (OperationsMetric.SOURCE_DELIVERY_NOTE_COUNT,),
                tuple(note.evidence_id for note in notes),
            )
        if value(OperationsMetric.RELATED_ORDER_COUNT) == 0:
            observe(
                OperationsObservationCode.NO_RELATED_ORDERS,
                "No explicitly related orders were selected",
                "Operations does not infer orders from descriptions or similar names.",
                (OperationsMetric.RELATED_ORDER_COUNT,),
            )

        orders_header = self._header_evidence(context, SheetRegistry.ORDERS.sheet_name, lineage)
        products_header = self._header_evidence(context, SheetRegistry.PRODUCTS.sheet_name, lineage)
        for item in (orders_header, products_header):
            evidence[item.evidence_id] = item

        def limit(
            code: str,
            detail: str,
            scope: OperationsDataScope,
            evidence_ids: tuple[str, ...],
        ) -> None:
            limitations.append(
                OperationsEvidenceLimitation(
                    limitation_id=deterministic_id("OLM", case_id, code, evidence_ids),
                    code=code,
                    detail=detail,
                    scope=scope,
                    evidence_ids=evidence_ids,
                )
            )

        if not has_as_of_date:
            limit(
                "AS_OF_DATE_NOT_PROVIDED",
                "No assessment date was provided, so past-due order facts are unavailable.",
                OperationsDataScope.CASE_SPECIFIC,
                (orders_header.evidence_id,),
            )
        for code, detail in (
            (
                "ACTUAL_DELIVERY_DATE_UNAVAILABLE",
                "Orders have planned dates but no structured actual-delivery date.",
            ),
            (
                "CAPACITY_DATA_UNAVAILABLE",
                "No structured resource or capacity fields are available for feasibility analysis.",
            ),
            (
                "CONTRACTOR_DATA_UNAVAILABLE",
                "No structured contractor assignment is available.",
            ),
            (
                "PHASE_DEPENDENCY_UNAVAILABLE",
                "No structured phase or dependency relationship is available.",
            ),
            (
                "ORDER_LOCATION_UNAVAILABLE",
                "No structured order delivery location is available.",
            ),
            (
                "OPERATIONAL_SLA_UNAVAILABLE",
                "No structured order-level operational SLA is available.",
            ),
        ):
            limit(code, detail, OperationsDataScope.NOT_AVAILABLE, (orders_header.evidence_id,))
        limit(
            "SERVICE_OPERATIONAL_PARAMETERS_UNAVAILABLE",
            "Service records do not provide structured duration, SLA, or capacity parameters.",
            OperationsDataScope.NOT_AVAILABLE,
            (products_header.evidence_id,),
        )
        if notes:
            limit(
                "DELIVERY_NOTES_UNSTRUCTURED",
                "Delivery notes are free text and are preserved without semantic inference.",
                OperationsDataScope.CASE_SPECIFIC,
                tuple(note.evidence_id for note in notes),
            )
        if OperationsMetric.OPC_LATE_DELIVERY_PENALTY_RATE in by_metric:
            penalty = by_metric[OperationsMetric.OPC_LATE_DELIVERY_PENALTY_RATE]
            limit(
                "PENALTY_BASIS_UNAVAILABLE",
                (
                    "A global penalty rate exists, but actual lateness and an explicit "
                    "penalty basis do not."
                ),
                OperationsDataScope.NOT_AVAILABLE,
                (penalty.evidence_id, orders_header.evidence_id),
            )
        if value(OperationsMetric.UNCLASSIFIED_ORDER_STATUS_COUNT) > 0:
            limit(
                "UNCLASSIFIED_SOURCE_STATUS",
                (
                    "At least one source order status is outside the exact supported "
                    "status vocabulary."
                ),
                OperationsDataScope.CASE_SPECIFIC,
                (by_metric[OperationsMetric.UNCLASSIFIED_ORDER_STATUS_COUNT].evidence_id,),
            )
        return OperationsConditions(
            observations=tuple(observations),
            limitations=tuple(limitations),
            evidence_refs=tuple(evidence[key] for key in sorted(evidence)),
        )

    @staticmethod
    def _header_evidence(
        context: OperationsContext,
        sheet: str,
        lineage: LineageFactory,
    ) -> EvidenceRef:
        return lineage.sheet_headers(sheet, context.dataset.headers.get(sheet, ()))
