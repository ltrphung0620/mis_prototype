"""Pure deterministic policy for Decision Initial Route classification."""

from dataclasses import dataclass

from opc_mis.business.agents.decision.context_loader import (
    DecisionInitialRouteContext,
)
from opc_mis.domain.decision_route_models import DecisionRoutingReason
from opc_mis.domain.enums import (
    BankingNeedType,
    DecisionCapability,
    DecisionRouteOutcome,
    DecisionRoutingReasonCode,
    FinanceObservationCode,
)
from opc_mis.domain.lineage import deterministic_id


@dataclass(frozen=True)
class InitialRoutePolicyResult:
    """Business outcome returned without selecting a workflow node."""

    outcome: DecisionRouteOutcome
    required_capabilities: tuple[DecisionCapability, ...]
    banking_need_types: tuple[BankingNeedType, ...]
    reasons: tuple[DecisionRoutingReason, ...]


class InitialRoutePolicy:
    """Map only typed upstream observations to supported route capabilities."""

    def evaluate(self, context: DecisionInitialRouteContext) -> InitialRoutePolicyResult:
        reasons: list[DecisionRoutingReason] = []
        for observation in context.finance_facts.observations:
            if (
                observation.code
                is not FinanceObservationCode.PERFORMANCE_BOND_REQUIREMENT_OBSERVED
            ):
                continue
            reasons.append(
                DecisionRoutingReason(
                    reason_id=deterministic_id(
                        "DRR",
                        context.evaluation_case.evaluation_case_id,
                        DecisionRoutingReasonCode.PERFORMANCE_BOND_REQUIREMENT,
                        observation.observation_id,
                        observation.evidence_ids,
                    ),
                    code=DecisionRoutingReasonCode.PERFORMANCE_BOND_REQUIREMENT,
                    banking_need_type=BankingNeedType.PERFORMANCE_BOND,
                    source_artifact_id=context.finance_facts_artifact.artifact_id,
                    source_reference_ids=(observation.observation_id,),
                    evidence_ids=observation.evidence_ids,
                )
            )
        if reasons:
            return InitialRoutePolicyResult(
                outcome=DecisionRouteOutcome.BANKING_DISCOVERY_REQUIRED,
                required_capabilities=(DecisionCapability.BANKING_INTERNAL_DISCOVERY,),
                banking_need_types=(BankingNeedType.PERFORMANCE_BOND,),
                reasons=tuple(reasons),
            )
        return InitialRoutePolicyResult(
            outcome=DecisionRouteOutcome.DIRECT_INTERNAL_DECISION,
            required_capabilities=(DecisionCapability.INTERNAL_DECISION_PACKAGE,),
            banking_need_types=(),
            reasons=(),
        )
