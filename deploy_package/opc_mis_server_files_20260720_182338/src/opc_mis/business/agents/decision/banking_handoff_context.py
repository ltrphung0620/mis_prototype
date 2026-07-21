"""Load exact EvaluationCase and Decision route artifacts for Banking handoff."""

from dataclasses import dataclass

from pydantic import ValidationError

from opc_mis.domain.artifacts import ArtifactEnvelope
from opc_mis.domain.components import ExecutionContext
from opc_mis.domain.decision_route_models import DecisionRoutePlan
from opc_mis.domain.enums import (
    ArtifactType,
    BankingNeedType,
    ContractRequirementType,
    DecisionRoutingReasonCode,
    SourceType,
    ValidationStatus,
)
from opc_mis.domain.planner_models import EvaluationCase
from opc_mis.domain.team_pack import SheetRegistry
from opc_mis.ports.artifact_repository import ArtifactRepository


class BankingHandoffContextError(RuntimeError):
    """Raised when an explicit Decision handoff input is invalid."""


class BankingHandoffRouteMissing(RuntimeError):
    """Raised when Decision has not produced a route plan yet."""


@dataclass(frozen=True)
class BankingHandoffContext:
    """Validated case requirement, route plan, and immutable envelopes."""

    evaluation_case_artifact: ArtifactEnvelope
    route_artifact: ArtifactEnvelope
    evaluation_case: EvaluationCase
    route_plan: DecisionRoutePlan


class BankingHandoffContextLoader:
    """Resolve validated case and route artifacts without reading source data."""

    def __init__(self, *, artifacts: ArtifactRepository) -> None:
        self._artifacts = artifacts

    async def load(self, context: ExecutionContext) -> BankingHandoffContext:
        if context.evaluation_case_id is None:
            raise BankingHandoffContextError(
                "Decision Banking handoff requires evaluation_case_id."
            )
        upstream: list[ArtifactEnvelope] = []
        for artifact_id in context.input_artifact_ids:
            artifact = await self._artifacts.get(artifact_id)
            if artifact is None:
                raise BankingHandoffContextError(
                    f"Decision received an unknown handoff artifact: {artifact_id}."
                )
            if artifact.validation_status not in {
                ValidationStatus.VALID,
                ValidationStatus.VALID_WITH_WARNINGS,
            }:
                raise BankingHandoffContextError(
                    f"Decision received an unvalidated handoff artifact: {artifact_id}."
                )
            upstream.append(artifact)
        routes = tuple(
            item for item in upstream if item.artifact_type is ArtifactType.DECISION_ROUTE_PLAN
        )
        unexpected = tuple(
            item.artifact_type
            for item in upstream
            if item.artifact_type
            not in {ArtifactType.EVALUATION_CASE, ArtifactType.DECISION_ROUTE_PLAN}
        )
        if unexpected:
            raise BankingHandoffContextError(
                "Decision Banking handoff received unexpected artifacts: "
                + ", ".join(item.value for item in unexpected)
            )
        if not routes:
            raise BankingHandoffRouteMissing(
                "Decision Banking handoff is waiting for DECISION_ROUTE_PLAN."
            )
        if len(routes) > 1:
            raise BankingHandoffContextError(
                "Decision Banking handoff received duplicate route artifacts."
            )
        case_artifacts = tuple(
            item for item in upstream if item.artifact_type is ArtifactType.EVALUATION_CASE
        )
        if len(case_artifacts) != 1:
            raise BankingHandoffContextError(
                "Decision Banking handoff requires exactly one EvaluationCase artifact."
            )
        evaluation_case_artifact = case_artifacts[0]
        route_artifact = routes[0]
        if any(
            item.evaluation_case_id != context.evaluation_case_id
            for item in (evaluation_case_artifact, route_artifact)
        ):
            raise BankingHandoffContextError(
                "Decision handoff envelopes do not match the Banking handoff case."
            )
        expected_order = (
            evaluation_case_artifact.artifact_id,
            route_artifact.artifact_id,
        )
        if context.input_artifact_ids != expected_order:
            raise BankingHandoffContextError(
                "Decision Banking handoff artifacts must use stable case/route order."
            )
        try:
            evaluation_case = EvaluationCase.model_validate(
                evaluation_case_artifact.payload
            )
            route_plan = DecisionRoutePlan.model_validate(route_artifact.payload)
        except ValidationError as exc:
            raise BankingHandoffContextError(
                f"Invalid Decision route input schema: {exc}"
            ) from exc
        expected = (
            context.evaluation_case_id,
            context.dataset_id,
            evaluation_case.contract_id,
        )
        if (
            route_plan.evaluation_case_id,
            route_plan.dataset_id,
            route_plan.contract_id,
        ) != expected:
            raise BankingHandoffContextError(
                "Decision route identity does not match the Banking handoff context."
            )
        if (
            evaluation_case.evaluation_case_id,
            evaluation_case.dataset_id,
            evaluation_case.contract_id,
        ) != expected:
            raise BankingHandoffContextError(
                "EvaluationCase identity does not match the Banking handoff context."
            )
        if evaluation_case_artifact.artifact_id not in route_plan.source_artifact_ids:
            raise BankingHandoffContextError(
                "Decision route is missing exact EvaluationCase artifact lineage."
            )
        self._validate_requirement_bindings(
            evaluation_case=evaluation_case,
            evaluation_case_artifact=evaluation_case_artifact,
            route_plan=route_plan,
            route_artifact=route_artifact,
        )
        return BankingHandoffContext(
            evaluation_case_artifact=evaluation_case_artifact,
            route_artifact=route_artifact,
            evaluation_case=evaluation_case,
            route_plan=route_plan,
        )

    @staticmethod
    def _validate_requirement_bindings(
        *,
        evaluation_case: EvaluationCase,
        evaluation_case_artifact: ArtifactEnvelope,
        route_plan: DecisionRoutePlan,
        route_artifact: ArtifactEnvelope,
    ) -> None:
        """Reject route reasons that drift from the Planner requirement artifact."""
        requirements = {
            item.requirement_id: item
            for item in evaluation_case.contract_requirements
        }
        case_evidence = {
            item.evidence_id: item for item in evaluation_case_artifact.evidence_refs
        }
        route_evidence_ids = {
            item.evidence_id for item in route_artifact.evidence_refs
        }
        for reason in route_plan.routing_reasons:
            requirement = requirements.get(reason.requirement_id)
            if requirement is None:
                raise BankingHandoffContextError(
                    "Decision route references an unknown contract requirement."
                )
            if (
                reason.code
                is not DecisionRoutingReasonCode.PERFORMANCE_BOND_REQUIREMENT
                or reason.banking_need_type is not BankingNeedType.PERFORMANCE_BOND
                or requirement.requirement_type
                is not ContractRequirementType.PERFORMANCE_BOND
                or reason.source_artifact_id
                != evaluation_case_artifact.artifact_id
                or reason.source_reference_ids != (requirement.requirement_id,)
                or reason.requirement_certainty is not requirement.certainty
                or reason.credit_case_id != requirement.credit_case_id
                or reason.requested_amount != requirement.requested_amount
                or reason.requested_amount_currency
                is not requirement.requested_amount_currency
                or reason.amount_semantics is not requirement.amount_semantics
                or reason.evidence_ids != requirement.evidence_ids
            ):
                raise BankingHandoffContextError(
                    "Decision route requirement binding does not match EvaluationCase."
                )
            if not set(reason.evidence_ids).issubset(case_evidence):
                raise BankingHandoffContextError(
                    "EvaluationCase requirement evidence is incomplete."
                )
            if not set(reason.evidence_ids).issubset(route_evidence_ids):
                raise BankingHandoffContextError(
                    "Decision route artifact omitted requirement evidence."
                )
            amount_evidence_ids = tuple(
                evidence_id
                for evidence_id in reason.evidence_ids
                if (
                    (evidence := case_evidence[evidence_id]).source_type
                    is SourceType.TEAM_PACK
                    and evidence.sheet == SheetRegistry.CREDIT_PROFILES.sheet_name
                    and evidence.record_id == reason.credit_case_id
                    and evidence.field == "requested_amount"
                    and evidence.display_value == reason.requested_amount
                )
            )
            if amount_evidence_ids != reason.amount_evidence_ids:
                raise BankingHandoffContextError(
                    "Decision route amount evidence does not match EvaluationCase."
                )
