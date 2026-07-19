"""Load the explicit Decision route artifact for Banking discovery handoff."""

from dataclasses import dataclass

from pydantic import ValidationError

from opc_mis.domain.artifacts import ArtifactEnvelope
from opc_mis.domain.components import ExecutionContext
from opc_mis.domain.decision_route_models import DecisionRoutePlan
from opc_mis.domain.enums import ArtifactType, ValidationStatus
from opc_mis.ports.artifact_repository import ArtifactRepository


class BankingHandoffContextError(RuntimeError):
    """Raised when an explicit Decision handoff input is invalid."""


class BankingHandoffRouteMissing(RuntimeError):
    """Raised when Decision has not produced a route plan yet."""


@dataclass(frozen=True)
class BankingHandoffContext:
    """Validated route plan and its immutable artifact envelope."""

    route_artifact: ArtifactEnvelope
    route_plan: DecisionRoutePlan


class BankingHandoffContextLoader:
    """Resolve one validated route artifact without reading source data."""

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
                    f"Decision received an unknown route artifact: {artifact_id}."
                )
            if artifact.validation_status not in {
                ValidationStatus.VALID,
                ValidationStatus.VALID_WITH_WARNINGS,
            }:
                raise BankingHandoffContextError(
                    f"Decision received an unvalidated route artifact: {artifact_id}."
                )
            upstream.append(artifact)
        routes = tuple(
            item
            for item in upstream
            if item.artifact_type is ArtifactType.DECISION_ROUTE_PLAN
        )
        unexpected = tuple(
            item.artifact_type
            for item in upstream
            if item.artifact_type is not ArtifactType.DECISION_ROUTE_PLAN
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
        route_artifact = routes[0]
        if route_artifact.evaluation_case_id != context.evaluation_case_id:
            raise BankingHandoffContextError(
                "Decision route envelope does not match the Banking handoff case."
            )
        try:
            route_plan = DecisionRoutePlan.model_validate(route_artifact.payload)
        except ValidationError as exc:
            raise BankingHandoffContextError(
                f"Invalid Decision route input schema: {exc}"
            ) from exc
        expected = (
            context.evaluation_case_id,
            context.dataset_id,
        )
        if (
            route_plan.evaluation_case_id,
            route_plan.dataset_id,
        ) != expected:
            raise BankingHandoffContextError(
                "Decision route identity does not match the Banking handoff context."
            )
        return BankingHandoffContext(
            route_artifact=route_artifact,
            route_plan=route_plan,
        )
