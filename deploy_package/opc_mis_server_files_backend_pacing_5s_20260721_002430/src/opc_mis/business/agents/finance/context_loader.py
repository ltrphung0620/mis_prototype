"""Load Finance context only from explicit Planner artifacts and dataset keys."""

from dataclasses import dataclass

from pydantic import ValidationError

from opc_mis.business.agents.finance.requirements import (
    FinanceRequirementFailure,
    validate_finance_records,
)
from opc_mis.domain.artifacts import ArtifactEnvelope
from opc_mis.domain.components import ExecutionContext
from opc_mis.domain.dataset import DatasetRecord, DatasetSnapshot
from opc_mis.domain.enums import ArtifactType, ReadinessStatus
from opc_mis.domain.planner_models import EvaluationCase, PlannerResult
from opc_mis.domain.team_pack import SheetRegistry
from opc_mis.ports.artifact_repository import ArtifactRepository
from opc_mis.ports.dataset_port import DatasetNotFoundError, DatasetPort


class FinanceContextError(RuntimeError):
    """Raised for invalid invocation or inconsistent upstream artifacts."""


@dataclass(frozen=True)
class FinanceContext:
    """Resolved records with only exact Planner-selected relationships."""

    dataset: DatasetSnapshot
    evaluation_case_artifact: ArtifactEnvelope
    planner_result_artifact: ArtifactEnvelope
    evaluation_case: EvaluationCase
    planner_result: PlannerResult
    contract: DatasetRecord
    orders: tuple[DatasetRecord, ...]
    invoices: tuple[DatasetRecord, ...]
    cashflow: tuple[DatasetRecord, ...]
    failures: tuple[FinanceRequirementFailure, ...]


class FinanceContextLoader:
    """Resolve Finance input without fuzzy names, descriptions, or row positions."""

    def __init__(self, *, datasets: DatasetPort, artifacts: ArtifactRepository) -> None:
        self._datasets = datasets
        self._artifacts = artifacts

    async def load(self, context: ExecutionContext) -> FinanceContext:
        if context.evaluation_case_id is None:
            raise FinanceContextError("Finance requires evaluation_case_id.")
        upstream_items: list[ArtifactEnvelope] = []
        for artifact_id in context.input_artifact_ids:
            artifact = await self._artifacts.get(artifact_id)
            if artifact is not None:
                upstream_items.append(artifact)
        upstream = tuple(upstream_items)
        case_artifact = self._one(upstream, ArtifactType.EVALUATION_CASE)
        planner_artifact = self._one(upstream, ArtifactType.PLANNER_RESULT)
        try:
            evaluation_case = EvaluationCase.model_validate(case_artifact.payload)
            planner_result = PlannerResult.model_validate(planner_artifact.payload)
            dataset = await self._datasets.get_snapshot(context.dataset_id)
        except (ValidationError, DatasetNotFoundError) as exc:
            raise FinanceContextError(f"Invalid Finance upstream context: {exc}") from exc
        if evaluation_case.evaluation_case_id != context.evaluation_case_id:
            raise FinanceContextError("EvaluationCase ID does not match execution context.")
        if evaluation_case.dataset_id != context.dataset_id:
            raise FinanceContextError("EvaluationCase dataset does not match execution context.")
        if planner_result.data_readiness.status is ReadinessStatus.BLOCKED:
            raise FinanceContextError("Planner result is blocked and cannot start Finance.")
        if planner_result.evaluation_case != evaluation_case:
            raise FinanceContextError("PlannerResult and EvaluationCase artifacts disagree.")

        contract = self._exact(dataset, SheetRegistry.CONTRACTS, evaluation_case.contract_id)
        orders = tuple(
            self._exact(dataset, SheetRegistry.ORDERS, order_id)
            for order_id in evaluation_case.related_order_ids
        )
        invoices = tuple(
            self._exact(dataset, SheetRegistry.INVOICES, invoice_id)
            for invoice_id in evaluation_case.related_invoice_ids
        )
        order_ids = {order.record_id for order in orders}
        for order in orders:
            if order.values.get("contract_id") != evaluation_case.contract_id:
                raise FinanceContextError(
                    f"Order {order.record_id} is not explicitly linked to the case contract."
                )
        for invoice in invoices:
            if invoice.values.get("order_id") not in order_ids:
                raise FinanceContextError(
                    f"Invoice {invoice.record_id} is not linked through a selected order."
                )
        failures = validate_finance_records(
            contract=contract,
            orders=orders,
            invoices=invoices,
        )
        return FinanceContext(
            dataset=dataset,
            evaluation_case_artifact=case_artifact,
            planner_result_artifact=planner_artifact,
            evaluation_case=evaluation_case,
            planner_result=planner_result,
            contract=contract,
            orders=orders,
            invoices=invoices,
            cashflow=tuple(dataset.records(SheetRegistry.CASHFLOW)),
            failures=failures,
        )

    @staticmethod
    def _one(
        artifacts: tuple[ArtifactEnvelope, ...], artifact_type: ArtifactType
    ) -> ArtifactEnvelope:
        matches = tuple(item for item in artifacts if item.artifact_type is artifact_type)
        if len(matches) != 1:
            raise FinanceContextError(
                f"Finance requires exactly one {artifact_type.value} upstream artifact."
            )
        return matches[0]

    @staticmethod
    def _exact(dataset: DatasetSnapshot, definition: object, record_id: str) -> DatasetRecord:
        matches = dataset.lookup(definition, record_id)  # type: ignore[arg-type]
        if len(matches) != 1:
            raise FinanceContextError(
                f"Expected exactly one {record_id} in the configured dataset; found {len(matches)}."
            )
        return matches[0]
