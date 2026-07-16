"""Resolve explicit TeamPack relationships and build an EvaluationCase."""

from __future__ import annotations

from dataclasses import dataclass
from numbers import Real

from opc_mis.business.skills.planner.requirement_registry import RequirementFailure
from opc_mis.domain.dataset import DatasetRecord, DatasetSnapshot
from opc_mis.domain.enums import (
    CashflowScope,
    EvaluationScope,
)
from opc_mis.domain.evidence import EvidenceRef
from opc_mis.domain.lineage import LineageFactory, deterministic_id
from opc_mis.domain.planner_models import EvaluationCase, PlannerRequest, PlannerWarning
from opc_mis.domain.team_pack import SheetRegistry
from opc_mis.domain.validation import valid_identifier


@dataclass(frozen=True)
class CaseBuildOutcome:
    """Internal case resolution result consumed by the requirement registry."""

    request: PlannerRequest
    dataset: DatasetSnapshot
    lineage: LineageFactory
    evaluation_case_id: str
    evaluation_case: EvaluationCase | None
    contract: DatasetRecord | None
    customer: DatasetRecord | None
    orders: tuple[DatasetRecord, ...]
    invoices: tuple[DatasetRecord, ...]
    services: tuple[DatasetRecord, ...]
    credit_profiles: tuple[DatasetRecord, ...]
    selected_records: tuple[DatasetRecord, ...]
    failures: tuple[RequirementFailure, ...]
    warnings: tuple[PlannerWarning, ...]
    evidence_refs: tuple[EvidenceRef, ...]
    validation_notes: tuple[str, ...]


def _unique_evidence(evidence: list[EvidenceRef]) -> tuple[EvidenceRef, ...]:
    by_id = {item.evidence_id: item for item in evidence}
    return tuple(by_id[key] for key in sorted(by_id))


def _is_number(value: object) -> bool:
    return isinstance(value, Real) and not isinstance(value, bool)


class CaseBuilder:
    """Build a case using exact ID relationships; never read the workbook directly."""

    def build(
        self,
        request: PlannerRequest,
        dataset: DatasetSnapshot,
        lineage: LineageFactory,
    ) -> CaseBuildOutcome:
        """Resolve the requested contract and every explicitly linked Planner entity."""
        case_id = deterministic_id(
            "CASE",
            request.dataset_id,
            dataset.snapshot_hash,
            request.contract_id,
            tuple(scope.value for scope in request.evaluation_scope),
        )
        failures: list[RequirementFailure] = []
        warnings: list[PlannerWarning] = []
        evidence: list[EvidenceRef] = []
        validation_notes: list[str] = []

        contract_matches = dataset.lookup(SheetRegistry.CONTRACTS, request.contract_id)
        if not contract_matches:
            failures.append(
                RequirementFailure(
                    code="CONTRACT_NOT_FOUND",
                    target_record=request.contract_id,
                    field="contract_id",
                    expected_type="existing contract_id",
                    reason="The requested contract does not exist in 04_CONTRACTS.",
                )
            )
            return self._outcome(
                request,
                dataset,
                lineage,
                case_id,
                None,
                None,
                (),
                (),
                (),
                (),
                failures,
                warnings,
                evidence,
                validation_notes,
            )
        if len(contract_matches) > 1:
            failures.append(
                RequirementFailure(
                    code="DUPLICATE_CONTRACT_ID",
                    target_record=request.contract_id,
                    field="contract_id",
                    expected_type="unique contract_id",
                    reason="The requested contract_id resolves to multiple rows.",
                )
            )
            return self._outcome(
                request,
                dataset,
                lineage,
                case_id,
                None,
                None,
                (),
                (),
                (),
                (),
                failures,
                warnings,
                evidence,
                validation_notes,
            )

        contract = contract_matches[0]
        evidence.append(lineage.record_field(contract, "contract_id"))
        customer_id = contract.values.get("customer_id")
        customer: DatasetRecord | None = None
        if not valid_identifier(customer_id):
            failures.append(
                RequirementFailure(
                    code="BROKEN_CONTRACT_CUSTOMER_REFERENCE",
                    target_record=contract.record_id,
                    field="customer_id",
                    expected_type="existing customer_id",
                    reason="The selected contract has no valid customer reference.",
                    evidence_refs=(lineage.record_field(contract, "customer_id"),),
                )
            )
        else:
            customer_matches = dataset.lookup(SheetRegistry.CUSTOMERS, customer_id)
            if len(customer_matches) != 1:
                failures.append(
                    RequirementFailure(
                        code="BROKEN_CONTRACT_CUSTOMER_REFERENCE",
                        target_record=contract.record_id,
                        field="customer_id",
                        expected_type="one existing customer_id",
                        reason=(
                            "The contract customer_id does not resolve uniquely in 03_CUSTOMERS."
                        ),
                        evidence_refs=(lineage.record_field(contract, "customer_id"),),
                    )
                )
            else:
                customer = customer_matches[0]
                evidence.append(lineage.record_field(customer, "customer_id"))

        orders = tuple(
            record
            for record in dataset.records(SheetRegistry.ORDERS)
            if record.values.get("contract_id") == contract.record_id
        )
        for order in orders:
            evidence.append(lineage.record_field(order, "order_id"))
            if customer is not None and order.values.get("customer_id") != customer.record_id:
                failures.append(
                    RequirementFailure(
                        code="BROKEN_ORDER_CUSTOMER_REFERENCE",
                        target_record=order.record_id,
                        field="customer_id",
                        expected_type=customer.record_id,
                        reason="Order customer_id conflicts with the selected contract customer.",
                        evidence_refs=(
                            lineage.record_field(order, "customer_id"),
                            lineage.record_field(customer, "customer_id"),
                        ),
                    )
                )
        order_ids = {order.record_id for order in orders}
        invoices = tuple(
            record
            for record in dataset.records(SheetRegistry.INVOICES)
            if record.values.get("order_id") in order_ids
        )
        for invoice in invoices:
            evidence.append(lineage.record_field(invoice, "invoice_id"))
            if customer is not None and invoice.values.get("customer_id") != customer.record_id:
                failures.append(
                    RequirementFailure(
                        code="BROKEN_INVOICE_CUSTOMER_REFERENCE",
                        target_record=invoice.record_id,
                        field="customer_id",
                        expected_type=customer.record_id,
                        reason="Invoice customer_id conflicts with its selected order/customer.",
                        evidence_refs=(lineage.record_field(invoice, "customer_id"),),
                    )
                )

        service_ids = {
            value for order in orders if valid_identifier(value := order.values.get("service_id"))
        }
        services_list: list[DatasetRecord] = []
        for service_id in sorted(service_ids):
            matches = dataset.lookup(SheetRegistry.PRODUCTS, service_id)
            if len(matches) == 1:
                services_list.append(matches[0])
                evidence.append(lineage.record_field(matches[0], "service_id"))
            elif not matches:
                sources = tuple(
                    lineage.record_field(order, "service_id")
                    for order in orders
                    if order.values.get("service_id") == service_id
                )
                warnings.append(
                    PlannerWarning(
                        warning_code="SERVICE_REFERENCE_UNAVAILABLE",
                        target_record=service_id,
                        field="service_id",
                        reason="An explicit order service_id does not resolve uniquely.",
                        evidence_refs=sources,
                    )
                )
            else:
                failures.append(
                    RequirementFailure(
                        code="DUPLICATE_SERVICE_ID",
                        target_record=service_id,
                        field="service_id",
                        expected_type="unique service_id",
                        reason="A related service_id resolves to multiple product rows.",
                        evidence_refs=tuple(
                            lineage.record_field(match, "service_id") for match in matches
                        ),
                    )
                )
        services = tuple(services_list)

        credit_profiles = self._explicit_credit_profiles(
            dataset, contract.record_id, lineage, evidence
        )
        self._append_warnings(
            request,
            dataset,
            lineage,
            contract,
            orders,
            invoices,
            warnings,
        )

        alerts = tuple(
            record
            for record in dataset.records(SheetRegistry.ALERTS)
            if record.values.get("related_record") == contract.record_id
        )
        for alert in alerts:
            evidence.append(lineage.record_field(alert, "alert_id"))
        if alerts:
            validation_notes.append(
                "Exact contract-level alert references were preserved for downstream "
                "Initial Risk Scan; "
                "Planner did not evaluate or trigger them."
            )

        cashflow_scope = self._cashflow_scope(dataset, contract.record_id)
        selected_records = (
            (contract,)
            + ((customer,) if customer is not None else ())
            + orders
            + invoices
            + services
            + credit_profiles
            + alerts
        )
        for record in selected_records:
            evidence.extend(record.patched_evidence.values())
        for warning in warnings:
            evidence.extend(warning.evidence_refs)
        case_evidence = _unique_evidence(evidence)
        evaluation_case = None
        if customer is not None:
            evaluation_case = EvaluationCase(
                evaluation_case_id=case_id,
                dataset_id=request.dataset_id,
                contract_id=contract.record_id,
                customer_id=customer.record_id,
                related_order_ids=tuple(order.record_id for order in orders),
                related_invoice_ids=tuple(invoice.record_id for invoice in invoices),
                related_service_ids=tuple(service.record_id for service in services),
                related_credit_case_ids=tuple(profile.record_id for profile in credit_profiles),
                evaluation_scope=request.evaluation_scope,
                cashflow_scope=cashflow_scope,
                warnings=tuple(warnings),
                evidence_refs=case_evidence,
            )

        return CaseBuildOutcome(
            request=request,
            dataset=dataset,
            lineage=lineage,
            evaluation_case_id=case_id,
            evaluation_case=evaluation_case,
            contract=contract,
            customer=customer,
            orders=orders,
            invoices=invoices,
            services=services,
            credit_profiles=credit_profiles,
            selected_records=selected_records,
            failures=tuple(failures),
            warnings=tuple(warnings),
            evidence_refs=case_evidence,
            validation_notes=tuple(validation_notes),
        )

    def _outcome(
        self,
        request: PlannerRequest,
        dataset: DatasetSnapshot,
        lineage: LineageFactory,
        case_id: str,
        contract: DatasetRecord | None,
        customer: DatasetRecord | None,
        orders: tuple[DatasetRecord, ...],
        invoices: tuple[DatasetRecord, ...],
        services: tuple[DatasetRecord, ...],
        credit_profiles: tuple[DatasetRecord, ...],
        failures: list[RequirementFailure],
        warnings: list[PlannerWarning],
        evidence: list[EvidenceRef],
        validation_notes: list[str],
    ) -> CaseBuildOutcome:
        selected = tuple(
            record
            for record in (contract, customer, *orders, *invoices, *services, *credit_profiles)
            if record is not None
        )
        return CaseBuildOutcome(
            request=request,
            dataset=dataset,
            lineage=lineage,
            evaluation_case_id=case_id,
            evaluation_case=None,
            contract=contract,
            customer=customer,
            orders=orders,
            invoices=invoices,
            services=services,
            credit_profiles=credit_profiles,
            selected_records=selected,
            failures=tuple(failures),
            warnings=tuple(warnings),
            evidence_refs=_unique_evidence(evidence),
            validation_notes=tuple(validation_notes),
        )

    def _explicit_credit_profiles(
        self,
        dataset: DatasetSnapshot,
        contract_id: str,
        lineage: LineageFactory,
        evidence: list[EvidenceRef],
    ) -> tuple[DatasetRecord, ...]:
        headers = dataset.headers.get(SheetRegistry.CREDIT_PROFILES.sheet_name, ())
        if "contract_id" not in headers:
            return ()
        matches = tuple(
            record
            for record in dataset.records(SheetRegistry.CREDIT_PROFILES)
            if record.values.get("contract_id") == contract_id
        )
        for match in matches:
            evidence.append(lineage.record_field(match, "credit_case_id"))
        return matches

    def _append_warnings(
        self,
        request: PlannerRequest,
        dataset: DatasetSnapshot,
        lineage: LineageFactory,
        contract: DatasetRecord,
        orders: tuple[DatasetRecord, ...],
        invoices: tuple[DatasetRecord, ...],
        warnings: list[PlannerWarning],
    ) -> None:
        contract_id_evidence = lineage.record_field(contract, "contract_id")
        if not orders:
            warnings.append(
                PlannerWarning(
                    warning_code="NO_RELATED_ORDERS",
                    target_record=contract.record_id,
                    field="order_id",
                    reason="No orders are explicitly related through order.contract_id.",
                    evidence_refs=(contract_id_evidence,),
                )
            )

        contract_value = contract.values.get("contract_value")
        revenues = [order.values.get("order_revenue") for order in orders]
        if orders and _is_number(contract_value) and all(_is_number(value) for value in revenues):
            source_evidence = (
                lineage.record_field(contract, "contract_value"),
                *(lineage.record_field(order, "order_revenue") for order in orders),
            )
            unmapped = contract_value - sum(revenues)
            if unmapped != 0:
                derived = lineage.derived(
                    sheet=SheetRegistry.CONTRACTS.sheet_name,
                    record_id=contract.record_id,
                    field="unmapped_contract_value",
                    display=unmapped,
                    sources=source_evidence,
                )
                warnings.append(
                    PlannerWarning(
                        warning_code="ORDER_COVERAGE_GAP",
                        target_record=contract.record_id,
                        field="contract_value",
                        reason=(
                            "Contract value is not fully covered by explicitly related "
                            "order revenue; "
                            "Planner does not assume what the difference represents."
                        ),
                        evidence_refs=(*source_evidence, derived),
                        details={"unmapped_contract_value": unmapped},
                    )
                )

        if orders and not invoices:
            order_evidence = tuple(lineage.record_field(order, "order_id") for order in orders)
            warnings.append(
                PlannerWarning(
                    warning_code="RELATED_INVOICES_UNAVAILABLE",
                    target_record=contract.record_id,
                    field="invoice_id",
                    reason="No invoices are explicitly related through the selected order IDs.",
                    evidence_refs=order_evidence,
                )
            )

        if EvaluationScope.OPERATIONS in request.evaluation_scope:
            headers = dataset.headers.get(SheetRegistry.ORDERS.sheet_name, ())
            expected_evidence = {"contractor_need", "phase_id", "capacity"}
            if expected_evidence.isdisjoint(headers):
                header_evidence = lineage.sheet_headers(SheetRegistry.ORDERS.sheet_name, headers)
                derived = lineage.derived(
                    sheet=SheetRegistry.ORDERS.sheet_name,
                    record_id=contract.record_id,
                    field="operations_evidence",
                    display="No contractor, phase, or capacity fields in baseline order schema",
                    sources=(header_evidence,),
                )
                warnings.append(
                    PlannerWarning(
                        warning_code="OPERATIONS_EVIDENCE_INCOMPLETE",
                        target_record=contract.record_id,
                        field="operations_evidence",
                        reason=(
                            "Baseline orders do not contain contractor, phase, or capacity "
                            "evidence. "
                            "Operations Assessment may proceed with this limitation."
                        ),
                        evidence_refs=(header_evidence, derived),
                    )
                )

        cashflow_headers = dataset.headers.get(SheetRegistry.CASHFLOW.sheet_name, ())
        cashflow_records = dataset.records(SheetRegistry.CASHFLOW)
        if cashflow_records and "contract_id" not in cashflow_headers:
            header_evidence = lineage.sheet_headers(
                SheetRegistry.CASHFLOW.sheet_name, cashflow_headers
            )
            derived = lineage.derived(
                sheet=SheetRegistry.CASHFLOW.sheet_name,
                record_id=contract.record_id,
                field="cashflow_scope",
                display="OPC_GLOBAL",
                sources=(header_evidence,),
            )
            warnings.append(
                PlannerWarning(
                    warning_code="CASHFLOW_OPC_GLOBAL",
                    target_record=contract.record_id,
                    field="cashflow_scope",
                    reason=(
                        "Cashflow data has no explicit contract relationship and is labeled "
                        "OPC_GLOBAL."
                    ),
                    evidence_refs=(header_evidence, derived),
                )
            )

        credit_headers = dataset.headers.get(SheetRegistry.CREDIT_PROFILES.sheet_name, ())
        if (
            EvaluationScope.FINANCE in request.evaluation_scope
            and dataset.records(SheetRegistry.CREDIT_PROFILES)
            and "contract_id" not in credit_headers
        ):
            header_evidence = lineage.sheet_headers(
                SheetRegistry.CREDIT_PROFILES.sheet_name, credit_headers
            )
            derived = lineage.derived(
                sheet=SheetRegistry.CREDIT_PROFILES.sheet_name,
                record_id=contract.record_id,
                field="credit_profile_relationship",
                display="NOT_EXPLICIT",
                sources=(header_evidence,),
            )
            warnings.append(
                PlannerWarning(
                    warning_code="CREDIT_RELATIONSHIP_NOT_EXPLICIT",
                    target_record=contract.record_id,
                    field="related_credit_case_ids",
                    reason=(
                        "Credit profiles have no structured contract_id; Planner did not infer a "
                        "relationship from descriptive text."
                    ),
                    evidence_refs=(header_evidence, derived),
                )
            )

    @staticmethod
    def _cashflow_scope(dataset: DatasetSnapshot, contract_id: str) -> CashflowScope:
        records = dataset.records(SheetRegistry.CASHFLOW)
        if not records:
            return CashflowScope.NOT_AVAILABLE
        headers = dataset.headers.get(SheetRegistry.CASHFLOW.sheet_name, ())
        if "contract_id" in headers and any(
            record.values.get("contract_id") == contract_id for record in records
        ):
            return CashflowScope.CASE_SPECIFIC
        return CashflowScope.OPC_GLOBAL
