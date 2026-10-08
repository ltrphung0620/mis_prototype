"""Load Operations context only from explicit Planner artifacts and exact keys."""

from dataclasses import dataclass

from pydantic import ValidationError

from opc_mis.business.skills.operations.requirements import (
    OperationsRequirementFailure,
    validate_operations_records,
)
from opc_mis.domain.artifacts import ArtifactEnvelope
from opc_mis.domain.components import ExecutionContext
from opc_mis.domain.dataset import DatasetRecord, DatasetSnapshot
from opc_mis.domain.enums import ArtifactType, EvaluationScope, ReadinessStatus
from opc_mis.domain.lineage import LineageFactory
from opc_mis.domain.planner_models import EvaluationCase, PlannerResult
from opc_mis.domain.team_pack import SheetDefinition, SheetRegistry
from opc_mis.ports.artifact_repository import ArtifactRepository
from opc_mis.ports.dataset_port import DatasetNotFoundError, DatasetPort


class OperationsContextError(RuntimeError):
    """Raised for invalid invocation or inconsistent upstream artifacts."""


@dataclass(frozen=True)
class OperationsContext:
    """Resolved records with only exact Planner-selected relationships."""

    dataset: DatasetSnapshot
    evaluation_case_artifact: ArtifactEnvelope
    planner_result_artifact: ArtifactEnvelope
    evaluation_case: EvaluationCase
    planner_result: PlannerResult
    contract: DatasetRecord
    orders: tuple[DatasetRecord, ...]
    services: tuple[DatasetRecord, ...]
    failures: tuple[OperationsRequirementFailure, ...]


class OperationsContextLoader:
    """Resolve Operations input without fuzzy descriptions or row positions."""

    def __init__(self, *, datasets: DatasetPort, artifacts: ArtifactRepository) -> None:
        self._datasets = datasets
        self._artifacts = artifacts

    async def load(self, context: ExecutionContext) -> OperationsContext:
        if context.evaluation_case_id is None:
            raise OperationsContextError("Operations requires evaluation_case_id.")
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
            raise OperationsContextError(f"Invalid Operations upstream context: {exc}") from exc
        if evaluation_case.evaluation_case_id != context.evaluation_case_id:
            raise OperationsContextError("EvaluationCase ID does not match execution context.")
        if evaluation_case.dataset_id != context.dataset_id:
            raise OperationsContextError("EvaluationCase dataset does not match context.")
        if EvaluationScope.OPERATIONS not in evaluation_case.evaluation_scope:
            raise OperationsContextError("EvaluationCase did not request OPERATIONS scope.")
        if planner_result.data_readiness.status is ReadinessStatus.BLOCKED:
            raise OperationsContextError("Planner result is blocked and cannot start Operations.")
        if planner_result.evaluation_case != evaluation_case:
            raise OperationsContextError("PlannerResult and EvaluationCase artifacts disagree.")

        contract = self._exact(dataset, SheetRegistry.CONTRACTS, evaluation_case.contract_id)
        orders = tuple(
            self._exact(dataset, SheetRegistry.ORDERS, order_id)
            for order_id in evaluation_case.related_order_ids
        )
        services = tuple(
            self._exact(dataset, SheetRegistry.PRODUCTS, service_id)
            for service_id in evaluation_case.related_service_ids
        )
        selected_service_ids = {service.record_id for service in services}
        for order in orders:
            if order.values.get("contract_id") != evaluation_case.contract_id:
                raise OperationsContextError(
                    f"Order {order.record_id} is not explicitly linked to the case contract."
                )
            if order.values.get("service_id") not in selected_service_ids:
                raise OperationsContextError(
                    f"Order {order.record_id} has an unresolved selected service reference."
                )
        lineage = LineageFactory(context.dataset_id, dataset.source_hash)
        failures = validate_operations_records(
            contract=contract,
            orders=orders,
            lineage=lineage,
        )
        return OperationsContext(
            dataset=dataset,
            evaluation_case_artifact=case_artifact,
            planner_result_artifact=planner_artifact,
            evaluation_case=evaluation_case,
            planner_result=planner_result,
            contract=contract,
            orders=orders,
            services=services,
            failures=failures,
        )

    @staticmethod
    def _one(
        artifacts: tuple[ArtifactEnvelope, ...], artifact_type: ArtifactType
    ) -> ArtifactEnvelope:
        matches = tuple(item for item in artifacts if item.artifact_type is artifact_type)
        if len(matches) != 1:
            raise OperationsContextError(
                f"Operations requires exactly one {artifact_type.value} upstream artifact."
            )
        return matches[0]

    @staticmethod
    def _exact(
        dataset: DatasetSnapshot,
        definition: SheetDefinition,
        record_id: str,
    ) -> DatasetRecord:
        matches = dataset.lookup(definition, record_id)
        if len(matches) != 1:
            raise OperationsContextError(
                f"Expected exactly one {record_id} in the dataset; found {len(matches)}."
            )
        return matches[0]
