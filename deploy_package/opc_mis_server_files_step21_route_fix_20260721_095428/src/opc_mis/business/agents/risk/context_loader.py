"""Load Risk context from exact case artifacts and named TeamPack projections."""

from dataclasses import dataclass

from pydantic import ValidationError

from opc_mis.domain.artifacts import ArtifactEnvelope
from opc_mis.domain.components import ExecutionContext
from opc_mis.domain.dataset import DatasetSnapshot
from opc_mis.domain.enums import ArtifactType, EvaluationScope, ReadinessStatus
from opc_mis.domain.finance_models import FinanceFacts
from opc_mis.domain.operations_models import OperationsFacts
from opc_mis.domain.planner_models import EvaluationCase, PlannerResult
from opc_mis.domain.team_pack import SheetDefinition, SheetRegistry
from opc_mis.ports.artifact_repository import ArtifactRepository
from opc_mis.ports.dataset_port import DatasetNotFoundError, DatasetPort


class RiskContextError(RuntimeError):
    """Raised when Risk cannot safely use its upstream context."""


@dataclass(frozen=True)
class RiskContext:
    """All explicit records and validated facts available to one Risk invocation."""

    dataset: DatasetSnapshot
    evaluation_case_artifact: ArtifactEnvelope
    planner_result_artifact: ArtifactEnvelope
    evaluation_case: EvaluationCase
    planner_result: PlannerResult
    finance_facts_artifact: ArtifactEnvelope | None
    finance_facts: FinanceFacts | None
    operations_facts_artifact: ArtifactEnvelope | None
    operations_facts: OperationsFacts | None

    @property
    def case_entity_ids(self) -> frozenset[str]:
        return frozenset(
            (
                self.evaluation_case.contract_id,
                self.evaluation_case.customer_id,
                *self.evaluation_case.related_order_ids,
                *self.evaluation_case.related_invoice_ids,
                *self.evaluation_case.related_service_ids,
                *self.evaluation_case.related_credit_case_ids,
            )
        )


class RiskContextLoader:
    """Resolve Risk inputs without fuzzy matching or description-based joins."""

    def __init__(self, *, datasets: DatasetPort, artifacts: ArtifactRepository) -> None:
        self._datasets = datasets
        self._artifacts = artifacts

    async def load(self, context: ExecutionContext) -> RiskContext:
        if context.evaluation_case_id is None:
            raise RiskContextError("Risk requires evaluation_case_id.")
        upstream_items: list[ArtifactEnvelope] = []
        for artifact_id in context.input_artifact_ids:
            artifact = await self._artifacts.get(artifact_id)
            if artifact is not None:
                upstream_items.append(artifact)
        upstream = tuple(upstream_items)
        case_artifact = self._one(upstream, ArtifactType.EVALUATION_CASE)
        planner_artifact = self._one(upstream, ArtifactType.PLANNER_RESULT)
        finance_artifact = self._optional_one(upstream, ArtifactType.FINANCE_FACTS)
        operations_artifact = self._optional_one(upstream, ArtifactType.OPERATIONS_FACTS)
        try:
            evaluation_case = EvaluationCase.model_validate(case_artifact.payload)
            planner_result = PlannerResult.model_validate(planner_artifact.payload)
            finance_facts = (
                FinanceFacts.model_validate(finance_artifact.payload)
                if finance_artifact is not None
                else None
            )
            operations_facts = (
                OperationsFacts.model_validate(operations_artifact.payload)
                if operations_artifact is not None
                else None
            )
            dataset = await self._datasets.get_snapshot(context.dataset_id)
        except (ValidationError, DatasetNotFoundError) as exc:
            raise RiskContextError(f"Invalid Risk upstream context: {exc}") from exc
        if evaluation_case.evaluation_case_id != context.evaluation_case_id:
            raise RiskContextError("EvaluationCase ID does not match Risk execution context.")
        if evaluation_case.dataset_id != context.dataset_id:
            raise RiskContextError("EvaluationCase dataset does not match Risk context.")
        if EvaluationScope.RISK not in evaluation_case.evaluation_scope:
            raise RiskContextError("EvaluationCase did not request RISK scope.")
        if planner_result.data_readiness.status is ReadinessStatus.BLOCKED:
            raise RiskContextError("Planner result is blocked and cannot start Risk.")
        if planner_result.evaluation_case != evaluation_case:
            raise RiskContextError("PlannerResult and EvaluationCase artifacts disagree.")
        self._validate_fact_identity(evaluation_case, finance_facts, operations_facts)
        self._require_sheet(dataset, SheetRegistry.RISK_RULES)
        self._require_sheet(dataset, SheetRegistry.ALERTS)
        return RiskContext(
            dataset=dataset,
            evaluation_case_artifact=case_artifact,
            planner_result_artifact=planner_artifact,
            evaluation_case=evaluation_case,
            planner_result=planner_result,
            finance_facts_artifact=finance_artifact,
            finance_facts=finance_facts,
            operations_facts_artifact=operations_artifact,
            operations_facts=operations_facts,
        )

    @staticmethod
    def _validate_fact_identity(
        case: EvaluationCase,
        finance: FinanceFacts | None,
        operations: OperationsFacts | None,
    ) -> None:
        for label, facts in (("Finance", finance), ("Operations", operations)):
            if facts is None:
                continue
            if facts.evaluation_case_id != case.evaluation_case_id:
                raise RiskContextError(f"{label} facts belong to a different case.")
            if facts.dataset_id != case.dataset_id:
                raise RiskContextError(f"{label} facts belong to a different dataset.")
            if facts.contract_id != case.contract_id:
                raise RiskContextError(f"{label} facts belong to a different contract.")

    @staticmethod
    def _require_sheet(dataset: DatasetSnapshot, definition: SheetDefinition) -> None:
        sheet_name = definition.sheet_name
        if sheet_name not in dataset.headers:
            raise RiskContextError(f"Required Risk sheet is unavailable: {sheet_name}.")

    @staticmethod
    def _one(
        artifacts: tuple[ArtifactEnvelope, ...], artifact_type: ArtifactType
    ) -> ArtifactEnvelope:
        matches = tuple(item for item in artifacts if item.artifact_type is artifact_type)
        if len(matches) != 1:
            raise RiskContextError(
                f"Risk requires exactly one {artifact_type.value} upstream artifact."
            )
        return matches[0]

    @staticmethod
    def _optional_one(
        artifacts: tuple[ArtifactEnvelope, ...], artifact_type: ArtifactType
    ) -> ArtifactEnvelope | None:
        matches = tuple(item for item in artifacts if item.artifact_type is artifact_type)
        if len(matches) > 1:
            raise RiskContextError(f"Risk received multiple {artifact_type.value} artifacts.")
        return matches[0] if matches else None
