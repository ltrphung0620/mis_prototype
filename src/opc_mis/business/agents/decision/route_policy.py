"""Pure deterministic policy for Decision Initial Route classification."""

from dataclasses import dataclass

from opc_mis.business.agents.decision.context_loader import (
    DecisionInitialRouteContext,
)
from opc_mis.domain.decision_route_models import DecisionRoutingReason
from opc_mis.domain.enums import (
    BankingNeedType,
    ContractRequirementType,
    CurrencyCode,
    DecisionCapability,
    DecisionRouteOutcome,
    DecisionRoutingReasonCode,
    RequirementAmountSemantics,
    RequirementCertainty,
    SourceType,
)
from opc_mis.domain.lineage import deterministic_id
from opc_mis.domain.team_pack import SheetRegistry


class InitialRoutePolicyError(ValueError):
    """Raised when a required Banking route lacks an unambiguous amount binding."""


@dataclass(frozen=True)
class InitialRoutePolicyResult:
    """Business outcome returned without selecting a workflow node."""

    outcome: DecisionRouteOutcome
    required_capabilities: tuple[DecisionCapability, ...]
    banking_need_types: tuple[BankingNeedType, ...]
    reasons: tuple[DecisionRoutingReason, ...]


class InitialRoutePolicy:
    """Map typed Planner contract requirements to supported route capabilities."""

    def evaluate(self, context: DecisionInitialRouteContext) -> InitialRoutePolicyResult:
        requirements = tuple(
            requirement
            for requirement in context.evaluation_case.contract_requirements
            if requirement.requirement_type
            is ContractRequirementType.PERFORMANCE_BOND
            and requirement.certainty is RequirementCertainty.REQUIRED
        )
        if len(requirements) > 1:
            raise InitialRoutePolicyError(
                "Decision requires one unambiguous REQUIRED performance-bond requirement."
            )
        if requirements:
            requirement = requirements[0]
            if (
                requirement.requested_amount is None
                or requirement.credit_case_id is None
                or requirement.amount_semantics
                is not RequirementAmountSemantics.CREDIT_PROFILE_REQUESTED_AMOUNT
                or requirement.requested_amount_currency is not CurrencyCode.VND
            ):
                raise InitialRoutePolicyError(
                    "A REQUIRED performance bond must carry one explicit credit-profile "
                    "requested amount in VND."
                )
            evidence_by_id = {
                item.evidence_id: item
                for item in context.evaluation_case_artifact.evidence_refs
            }
            if not set(requirement.evidence_ids).issubset(evidence_by_id):
                raise InitialRoutePolicyError(
                    "The performance-bond requirement evidence is absent from "
                    "EvaluationCase."
                )
            amount_evidence_ids = tuple(
                evidence_id
                for evidence_id in requirement.evidence_ids
                if (
                    (evidence := evidence_by_id[evidence_id]).source_type
                    is SourceType.TEAM_PACK
                    and evidence.sheet == SheetRegistry.CREDIT_PROFILES.sheet_name
                    and evidence.record_id == requirement.credit_case_id
                    and evidence.field == "requested_amount"
                    and evidence.display_value == requirement.requested_amount
                )
            )
            if len(amount_evidence_ids) != 1:
                raise InitialRoutePolicyError(
                    "The performance-bond amount must have one exact TeamPack credit-profile "
                    "evidence reference."
                )
            reason = DecisionRoutingReason(
                reason_id=deterministic_id(
                    "DRR",
                    context.evaluation_case.evaluation_case_id,
                    DecisionRoutingReasonCode.PERFORMANCE_BOND_REQUIREMENT,
                    requirement.requirement_id,
                    requirement.credit_case_id,
                    requirement.requested_amount,
                    requirement.requested_amount_currency,
                    requirement.amount_semantics,
                    requirement.evidence_ids,
                ),
                code=DecisionRoutingReasonCode.PERFORMANCE_BOND_REQUIREMENT,
                banking_need_type=BankingNeedType.PERFORMANCE_BOND,
                requirement_id=requirement.requirement_id,
                requirement_certainty=requirement.certainty,
                credit_case_id=requirement.credit_case_id,
                requested_amount=requirement.requested_amount,
                requested_amount_currency=requirement.requested_amount_currency,
                amount_semantics=requirement.amount_semantics,
                amount_evidence_ids=amount_evidence_ids,
                source_artifact_id=context.evaluation_case_artifact.artifact_id,
                source_reference_ids=(requirement.requirement_id,),
                evidence_ids=requirement.evidence_ids,
            )
            return InitialRoutePolicyResult(
                outcome=DecisionRouteOutcome.BANKING_DISCOVERY_REQUIRED,
                required_capabilities=(DecisionCapability.BANKING_INTERNAL_DISCOVERY,),
                banking_need_types=(BankingNeedType.PERFORMANCE_BOND,),
                reasons=(reason,),
            )
        return InitialRoutePolicyResult(
            outcome=DecisionRouteOutcome.DIRECT_INTERNAL_DECISION,
            required_capabilities=(DecisionCapability.INTERNAL_DECISION_PACKAGE,),
            banking_need_types=(),
            reasons=(),
        )
