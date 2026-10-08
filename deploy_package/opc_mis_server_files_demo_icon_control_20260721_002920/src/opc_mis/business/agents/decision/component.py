"""Side-effect-free deterministic Decision Initial Route component."""

from opc_mis.business.agents.decision.context_loader import (
    DecisionRouteContextError,
    DecisionRouteContextLoader,
    DecisionRouteMissingArtifacts,
)
from opc_mis.business.agents.decision.route_policy import (
    InitialRoutePolicy,
    InitialRoutePolicyError,
)
from opc_mis.domain.artifacts import ArtifactDraft
from opc_mis.domain.components import ExecutionContext
from opc_mis.domain.decision_route_models import (
    DecisionRouteComponentResult,
    DecisionRoutePlan,
)
from opc_mis.domain.enums import (
    ArtifactType,
    ComponentStatus,
    DecisionRouteMode,
)
from opc_mis.domain.events import RuntimeEvent
from opc_mis.domain.lineage import deterministic_id
from opc_mis.domain.missing_data import MissingDataRequest


class DecisionInitialRoutePlanner:
    """Classify the first downstream capability without executing it."""

    component_id = "DECISION_INITIAL_ROUTE"

    def __init__(
        self,
        *,
        context_loader: DecisionRouteContextLoader,
        policy: InitialRoutePolicy | None = None,
    ) -> None:
        self._context_loader = context_loader
        self._policy = policy or InitialRoutePolicy()

    async def execute(self, context: ExecutionContext) -> DecisionRouteComponentResult:
        try:
            mode = DecisionRouteMode(context.component_input["execution_mode"])
        except (KeyError, ValueError):
            return self._failed_safe(
                "Decision Route Planning requires explicit INITIAL_ROUTE mode."
            )
        if mode is not DecisionRouteMode.INITIAL_ROUTE:  # pragma: no cover - enum guard
            return self._failed_safe("Unsupported Decision Route Planning mode.")
        try:
            route_context = await self._context_loader.load(context)
        except DecisionRouteMissingArtifacts as exc:
            requests = tuple(
                MissingDataRequest(
                    request_id=deterministic_id(
                        "MDR",
                        context.evaluation_case_id,
                        self.component_id,
                        artifact_type,
                    ),
                    evaluation_case_id=context.evaluation_case_id or "UNKNOWN",
                    raised_by=self.component_id,
                    requirement_code=f"{artifact_type.value}_REQUIRED",
                    target_record=context.evaluation_case_id or "UNKNOWN",
                    field=artifact_type.value,
                    expected_type="validated artifact envelope",
                    reason=(
                        f"Decision Initial Route requires {artifact_type.value} "
                        "from the completed Initial Assessment."
                    ),
                )
                for artifact_type in exc.missing
            )
            return DecisionRouteComponentResult(
                status=ComponentStatus.WAITING_FOR_INPUT,
                missing_data_requests=requests,
                runtime_events=(
                    RuntimeEvent(
                        event_type="DECISION_INITIAL_ROUTE_WAITING_FOR_INPUT",
                        message=str(exc),
                    ),
                ),
            )
        except DecisionRouteContextError as exc:
            return self._failed_safe(str(exc))
        try:
            policy_result = self._policy.evaluate(route_context)
        except InitialRoutePolicyError as exc:
            return self._failed_safe(str(exc))
        checkpoint_ids = tuple(
            item.checkpoint_id
            for item in route_context.approval_checkpoints.checkpoints
        )
        plan = DecisionRoutePlan(
            route_plan_id=deterministic_id(
                "DRP",
                route_context.evaluation_case.evaluation_case_id,
                mode,
                policy_result.outcome,
                policy_result.required_capabilities,
                tuple(item.reason_id for item in policy_result.reasons),
                checkpoint_ids,
                route_context.source_artifact_ids,
            ),
            evaluation_case_id=route_context.evaluation_case.evaluation_case_id,
            dataset_id=route_context.evaluation_case.dataset_id,
            contract_id=route_context.evaluation_case.contract_id,
            execution_mode=mode,
            route_outcome=policy_result.outcome,
            required_capabilities=policy_result.required_capabilities,
            banking_need_types=policy_result.banking_need_types,
            routing_reasons=policy_result.reasons,
            conditional_approval_checkpoint_ids=checkpoint_ids,
            source_artifact_ids=route_context.source_artifact_ids,
        )
        referenced_evidence_ids = {
            evidence_id
            for reason in plan.routing_reasons
            for evidence_id in reason.evidence_ids
        }
        evidence_by_id = {
            item.evidence_id: item
            for artifact in (
                route_context.evaluation_case_artifact,
                route_context.finance_facts_artifact,
                route_context.approval_checkpoints_artifact,
            )
            for item in artifact.evidence_refs
        }
        evidence_refs = tuple(
            evidence_by_id[evidence_id]
            for evidence_id in sorted(
                referenced_evidence_ids
                | {
                    item.evidence_id
                    for item in route_context.approval_checkpoints_artifact.evidence_refs
                }
            )
        )
        draft = ArtifactDraft(
            artifact_type=ArtifactType.DECISION_ROUTE_PLAN,
            evaluation_case_id=plan.evaluation_case_id,
            producer=self.component_id,
            payload=plan.model_dump(mode="json"),
            evidence_refs=evidence_refs,
            identity_inputs={
                "execution_mode": mode,
                "route_outcome": plan.route_outcome,
                "required_capabilities": plan.required_capabilities,
                "routing_reason_ids": tuple(
                    item.reason_id for item in plan.routing_reasons
                ),
                "routing_requirement_ids": tuple(
                    item.requirement_id for item in plan.routing_reasons
                ),
                "conditional_approval_checkpoint_ids": checkpoint_ids,
                "source_artifact_ids": plan.source_artifact_ids,
            },
        )
        return DecisionRouteComponentResult(
            status=ComponentStatus.COMPLETED,
            artifacts=(draft,),
            route_plan=plan,
            runtime_events=(
                RuntimeEvent(
                    event_type="DECISION_INITIAL_ROUTE_COMPLETED",
                    message=(
                        "Decision Initial Route classified the next required "
                        f"business capability as {plan.route_outcome.value}."
                    ),
                    metadata={"route_plan_id": plan.route_plan_id},
                ),
            ),
        )

    @staticmethod
    def _failed_safe(message: str) -> DecisionRouteComponentResult:
        return DecisionRouteComponentResult(
            status=ComponentStatus.FAILED_SAFE,
            runtime_events=(
                RuntimeEvent(
                    event_type="DECISION_INITIAL_ROUTE_FAILED_SAFE",
                    message=message,
                ),
            ),
        )
