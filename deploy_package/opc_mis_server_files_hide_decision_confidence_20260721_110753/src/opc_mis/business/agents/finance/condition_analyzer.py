"""Convert Finance facts into neutral observations and evidence limitations."""

from dataclasses import dataclass

from opc_mis.business.agents.finance.context_loader import FinanceContext
from opc_mis.business.agents.finance.transaction_evidence import (
    has_explicit_case_transaction_link,
)
from opc_mis.domain.enums import FinanceDataScope, FinanceMetric, FinanceObservationCode
from opc_mis.domain.evidence import EvidenceRef
from opc_mis.domain.finance_models import (
    FinanceEvidenceLimitation,
    FinanceFact,
    FinanceObservation,
)
from opc_mis.domain.lineage import LineageFactory, deterministic_id
from opc_mis.domain.team_pack import SheetRegistry


@dataclass(frozen=True)
class FinanceConditions:
    observations: tuple[FinanceObservation, ...]
    limitations: tuple[FinanceEvidenceLimitation, ...]
    evidence_refs: tuple[EvidenceRef, ...]


class FinanceConditionAnalyzer:
    """Report conditions without risk scores, severity, rules, or approvals."""

    def analyze(
        self,
        context: FinanceContext,
        facts: tuple[FinanceFact, ...],
        lineage: LineageFactory,
    ) -> FinanceConditions:
        case_id = context.evaluation_case.evaluation_case_id
        by_metric = {fact.metric: fact for fact in facts}
        observations: list[FinanceObservation] = []
        limitations: list[FinanceEvidenceLimitation] = []
        extra_evidence: list[EvidenceRef] = []

        def observe(
            code: FinanceObservationCode,
            title: str,
            detail: str,
            metrics: tuple[FinanceMetric, ...] = (),
            evidence_ids: tuple[str, ...] = (),
        ) -> None:
            selected = tuple(by_metric[metric] for metric in metrics if metric in by_metric)
            all_evidence = tuple(
                dict.fromkeys(tuple(fact.evidence_id for fact in selected) + evidence_ids)
            )
            observations.append(
                FinanceObservation(
                    observation_id=deterministic_id("FOB", case_id, code, all_evidence),
                    code=code,
                    title=title,
                    detail=detail,
                    fact_ids=tuple(fact.fact_id for fact in selected),
                    evidence_ids=all_evidence,
                )
            )

        contract_margin = by_metric.get(FinanceMetric.CONTRACT_GROSS_MARGIN_SOURCE)
        target_margin = by_metric.get(FinanceMetric.OPC_TARGET_GROSS_MARGIN)
        if (
            contract_margin
            and target_margin
            and isinstance(contract_margin.value, (int, float))
            and isinstance(target_margin.value, (int, float))
            and contract_margin.value < target_margin.value
        ):
            observe(
                FinanceObservationCode.MARGIN_BELOW_OPC_TARGET_OBSERVED,
                "Source margin is below the OPC target",
                "The contract margin field is lower than the OPC profile target.",
                (FinanceMetric.CONTRACT_GROSS_MARGIN_SOURCE, FinanceMetric.OPC_TARGET_GROSS_MARGIN),
            )
        order_coverage = by_metric[FinanceMetric.ORDER_COVERAGE_RATIO]
        if isinstance(order_coverage.value, (int, float)) and order_coverage.value < 1:
            observe(
                FinanceObservationCode.ORDER_COVERAGE_INCOMPLETE,
                "Explicit orders do not cover the full contract value",
                "The total of explicitly related orders is below the contract value.",
                (FinanceMetric.ORDER_COVERAGE_RATIO, FinanceMetric.UNCOVERED_CONTRACT_VALUE),
            )
        outstanding = by_metric[FinanceMetric.OUTSTANDING_ISSUED_RECEIVABLE]
        if isinstance(outstanding.value, (int, float)) and outstanding.value > 0:
            observe(
                FinanceObservationCode.RECEIVABLE_EXPOSURE_OBSERVED,
                "Issued receivable remains outstanding",
                "At least one explicitly related issued invoice is not marked paid.",
                (FinanceMetric.OUTSTANDING_ISSUED_RECEIVABLE,),
            )
        worst_gap = by_metric[FinanceMetric.WORST_RESERVE_GAP]
        if isinstance(worst_gap.value, (int, float)) and worst_gap.value > 0:
            observe(
                FinanceObservationCode.CASH_RESERVE_SHORTFALL_OBSERVED,
                "OPC projection falls below its reserve minimum",
                "The OPC-level cashflow projection contains a reserve shortfall.",
                (FinanceMetric.WORST_RESERVE_GAP, FinanceMetric.WORST_RESERVE_GAP_MONTH),
            )
        negative_months = by_metric[FinanceMetric.NEGATIVE_NET_CASHFLOW_MONTH_COUNT]
        if isinstance(negative_months.value, int) and negative_months.value > 0:
            observe(
                FinanceObservationCode.NEGATIVE_NET_CASH_MOVEMENT_OBSERVED,
                "OPC projection contains negative net-cash months",
                "Expected cash out exceeds expected cash in in part of the OPC projection.",
                (FinanceMetric.NEGATIVE_NET_CASHFLOW_MONTH_COUNT,),
            )

        payment_evidence = lineage.record_field(context.contract, "payment_terms")
        extra_evidence.append(payment_evidence)
        payment_terms = str(context.contract.values.get("payment_terms") or "")
        if "performance bond" in payment_terms.casefold():
            observe(
                FinanceObservationCode.PERFORMANCE_BOND_REQUIREMENT_OBSERVED,
                "Performance bond is explicitly required",
                "The contract payment terms explicitly state a performance-bond requirement.",
                evidence_ids=(payment_evidence.evidence_id,),
            )

        if context.invoices:
            due_date_evidence = tuple(
                lineage.record_field(invoice, "due_date") for invoice in context.invoices
            )
            extra_evidence.extend(due_date_evidence)
            limitations.append(
                FinanceEvidenceLimitation(
                    limitation_id=deterministic_id("FLM", case_id, "AS_OF_DATE_NOT_PROVIDED"),
                    code="AS_OF_DATE_NOT_PROVIDED",
                    detail=(
                        "No assessment date was provided, so Finance does not calculate "
                        "overdue days or aging buckets."
                    ),
                    scope=FinanceDataScope.CASE_SPECIFIC,
                    evidence_ids=tuple(item.evidence_id for item in due_date_evidence),
                )
            )

        if context.cashflow:
            observe(
                FinanceObservationCode.CASHFLOW_ONLY_AVAILABLE_AT_OPC_LEVEL,
                "Cashflow is available only at OPC level",
                "The cashflow sheet has no structured contract identifier.",
                (FinanceMetric.CASHFLOW_MONTH_COUNT,),
            )
            limitations.append(
                FinanceEvidenceLimitation(
                    limitation_id=deterministic_id("FLM", case_id, "CASHFLOW_OPC_GLOBAL"),
                    code="CASHFLOW_OPC_GLOBAL",
                    detail="Cashflow facts cannot be attributed to this contract.",
                    scope=FinanceDataScope.OPC_GLOBAL,
                    evidence_ids=(by_metric[FinanceMetric.CASHFLOW_MONTH_COUNT].evidence_id,),
                )
            )
        if not has_explicit_case_transaction_link(context.dataset):
            headers = context.dataset.headers.get(SheetRegistry.BANK_TRANSACTIONS.sheet_name, ())
            if headers:
                header_evidence = lineage.sheet_headers(
                    SheetRegistry.BANK_TRANSACTIONS.sheet_name, headers
                )
                extra_evidence.append(header_evidence)
                header_ids = (header_evidence.evidence_id,)
            else:
                header_ids = ()
            observe(
                FinanceObservationCode.TRANSACTION_LINKAGE_UNAVAILABLE,
                "No structured case-to-transaction relationship is available",
                "Transaction descriptions are not used to infer contract or invoice links.",
                evidence_ids=header_ids,
            )
            limitations.append(
                FinanceEvidenceLimitation(
                    limitation_id=deterministic_id(
                        "FLM", case_id, "TRANSACTION_LINKAGE_UNAVAILABLE"
                    ),
                    code="TRANSACTION_LINKAGE_UNAVAILABLE",
                    detail=(
                        "Bank transactions have no structured contract_id, order_id, or "
                        "invoice_id; description matching is prohibited."
                    ),
                    scope=FinanceDataScope.NOT_AVAILABLE,
                    evidence_ids=header_ids,
                )
            )
        return FinanceConditions(
            observations=tuple(observations),
            limitations=tuple(limitations),
            evidence_refs=tuple(extra_evidence),
        )
