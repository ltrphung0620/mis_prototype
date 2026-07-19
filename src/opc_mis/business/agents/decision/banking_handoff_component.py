"""Side-effect-free Decision handoff to the internal Banking discovery skill."""

from opc_mis.business.agents.decision.banking_handoff_context import (
    BankingHandoffContextError,
    BankingHandoffContextLoader,
    BankingHandoffRouteMissing,
)
from opc_mis.domain.artifacts import ArtifactDraft
from opc_mis.domain.banking_models import (
    BankingDiscoveryHandoffComponentResult,
    BankingDiscoveryRequest,
)
from opc_mis.domain.components import ExecutionContext
from opc_mis.domain.enums import (
    ArtifactType,
    BankingDiscoveryHandoffStatus,
    ComponentStatus,
    CurrencyCode,
    DecisionCapability,
    DecisionHandoffMode,
    DecisionRouteOutcome,
)
from opc_mis.domain.events import RuntimeEvent
from opc_mis.domain.evidence import EvidenceRef
from opc_mis.domain.lineage import deterministic_id
from opc_mis.domain.missing_data import MissingDataRequest


class DecisionBankingHandoff:
    """Create an internal request; never invoke Banking or an external adapter."""

    component_id = "DECISION_BANKING_HANDOFF"

    def __init__(self, *, context_loader: BankingHandoffContextLoader) -> None:
        self._context_loader = context_loader

    async def execute(
        self, context: ExecutionContext
    ) -> BankingDiscoveryHandoffComponentResult:
        try:
            mode = DecisionHandoffMode(context.component_input["execution_mode"])
        except (KeyError, ValueError):
            return self._failed_safe(
                "Decision Banking handoff requires explicit BANKING_DISCOVERY mode."
            )
        if mode is not DecisionHandoffMode.BANKING_DISCOVERY:  # pragma: no cover
            return self._failed_safe("Unsupported Decision Banking handoff mode.")
        try:
            handoff_context = await self._context_loader.load(context)
        except BankingHandoffRouteMissing as exc:
            missing = MissingDataRequest(
                request_id=deterministic_id(
                    "MDR",
                    context.evaluation_case_id,
                    self.component_id,
                    ArtifactType.DECISION_ROUTE_PLAN,
                ),
                evaluation_case_id=context.evaluation_case_id or "UNKNOWN",
                raised_by=self.component_id,
                requirement_code="DECISION_ROUTE_PLAN_REQUIRED",
                target_record=context.evaluation_case_id or "UNKNOWN",
                field=ArtifactType.DECISION_ROUTE_PLAN.value,
                expected_type="validated artifact envelope",
                reason=str(exc),
            )
            return BankingDiscoveryHandoffComponentResult(
                status=ComponentStatus.WAITING_FOR_INPUT,
                handoff_status=BankingDiscoveryHandoffStatus.WAITING_FOR_ROUTE,
                missing_data_requests=(missing,),
                runtime_events=(
                    RuntimeEvent(
                        event_type="DECISION_BANKING_HANDOFF_WAITING_FOR_ROUTE",
                        message=str(exc),
                    ),
                ),
            )
        except BankingHandoffContextError as exc:
            return self._failed_safe(str(exc))

        plan = handoff_context.route_plan
        if plan.route_outcome is DecisionRouteOutcome.DIRECT_INTERNAL_DECISION:
            return BankingDiscoveryHandoffComponentResult(
                status=ComponentStatus.COMPLETED,
                handoff_status=BankingDiscoveryHandoffStatus.NOT_APPLICABLE,
                runtime_events=(
                    RuntimeEvent(
                        event_type="DECISION_BANKING_HANDOFF_NOT_APPLICABLE",
                        message=(
                            "The Decision route does not request Banking discovery; "
                            "no Banking request was created."
                        ),
                    ),
                ),
            )
        if (
            plan.route_outcome is not DecisionRouteOutcome.BANKING_DISCOVERY_REQUIRED
            or plan.required_capabilities
            != (DecisionCapability.BANKING_INTERNAL_DISCOVERY,)
            or not plan.banking_need_types
            or not plan.routing_reasons
            or {item.banking_need_type for item in plan.routing_reasons}
            != set(plan.banking_need_types)
            or any(
                item.source_artifact_id not in plan.source_artifact_ids
                for item in plan.routing_reasons
            )
        ):
            return self._failed_safe(
                "The Decision route is inconsistent with Banking discovery handoff."
            )

        evidence_ids = tuple(
            sorted(
                {
                    evidence_id
                    for reason in plan.routing_reasons
                    for evidence_id in reason.evidence_ids
                }
            )
        )
        evidence_refs = self._evidence_closure(
            handoff_context.route_artifact.evidence_refs,
            evidence_ids,
        )
        source_artifact_ids = tuple(
            dict.fromkeys(
                (
                    handoff_context.route_artifact.artifact_id,
                    *plan.source_artifact_ids,
                )
            )
        )
        request = BankingDiscoveryRequest(
            request_id=deterministic_id(
                "BDR",
                plan.evaluation_case_id,
                plan.route_plan_id,
                plan.banking_need_types,
                evidence_ids,
                source_artifact_ids,
            ),
            evaluation_case_id=plan.evaluation_case_id,
            dataset_id=plan.dataset_id,
            contract_id=plan.contract_id,
            execution_mode=mode,
            requested_capability=DecisionCapability.BANKING_INTERNAL_DISCOVERY,
            need_types=plan.banking_need_types,
            requested_amount=None,
            requested_amount_currency=CurrencyCode.VND,
            constraints=(),
            source_route_artifact_id=handoff_context.route_artifact.artifact_id,
            source_route_plan_id=plan.route_plan_id,
            source_artifact_ids=source_artifact_ids,
            evidence_ids=evidence_ids,
        )
        draft = ArtifactDraft(
            artifact_type=ArtifactType.BANKING_DISCOVERY_REQUEST,
            evaluation_case_id=request.evaluation_case_id,
            producer=self.component_id,
            payload=request.model_dump(mode="json"),
            evidence_refs=evidence_refs,
            identity_inputs={
                "source_route_artifact_id": request.source_route_artifact_id,
                "source_route_plan_id": request.source_route_plan_id,
                "requested_capability": request.requested_capability,
                "need_types": request.need_types,
                "requested_amount_currency": request.requested_amount_currency,
                "evidence_ids": request.evidence_ids,
            },
        )
        return BankingDiscoveryHandoffComponentResult(
            status=ComponentStatus.COMPLETED,
            handoff_status=BankingDiscoveryHandoffStatus.REQUEST_CREATED,
            banking_discovery_request=request,
            artifacts=(draft,),
            runtime_events=(
                RuntimeEvent(
                    event_type="BANKING_DISCOVERY_REQUEST_CREATED",
                    message=(
                        "Decision created an internal evidence-backed request for "
                        "Banking discovery."
                    ),
                    metadata={"request_id": request.request_id},
                ),
            ),
        )

    @staticmethod
    def _evidence_closure(
        available: tuple[EvidenceRef, ...],
        selected_ids: tuple[str, ...],
    ) -> tuple[EvidenceRef, ...]:
        by_id = {item.evidence_id: item for item in available}
        pending = list(selected_ids)
        included: set[str] = set()
        while pending:
            evidence_id = pending.pop()
            evidence = by_id.get(evidence_id)
            if evidence is None:
                continue
            if evidence_id in included:
                continue
            included.add(evidence_id)
            pending.extend(evidence.source_evidence_ids)
        return tuple(by_id[evidence_id] for evidence_id in sorted(included))

    @staticmethod
    def _failed_safe(message: str) -> BankingDiscoveryHandoffComponentResult:
        return BankingDiscoveryHandoffComponentResult(
            status=ComponentStatus.FAILED_SAFE,
            handoff_status=BankingDiscoveryHandoffStatus.FAILED_SAFE,
            runtime_events=(
                RuntimeEvent(
                    event_type="DECISION_BANKING_HANDOFF_FAILED_SAFE",
                    message=message,
                ),
            ),
        )
