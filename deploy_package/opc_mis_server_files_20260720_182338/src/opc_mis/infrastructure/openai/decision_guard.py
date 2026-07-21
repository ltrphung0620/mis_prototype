"""Deterministic guardrails for untrusted OpenAI Decision proposals."""

from __future__ import annotations

import hashlib
import json

from pydantic import BaseModel

from opc_mis.domain.decision_analysis import validate_decision_proposal_prose
from opc_mis.domain.decision_models import (
    AIDecisionProposalDraft,
    AIDecisionReasonDraft,
    AIDecisionRecommendedActionDraft,
    DecisionConditionStatus,
    DecisionConfidence,
    DecisionRecommendation,
    DecisionReferenceKind,
    DecisionScenarioPacket,
    NegotiationConditionDraft,
    decision_packet_input_hash,
)
from opc_mis.domain.lineage import deterministic_id

_SAFE_EXECUTIVE_SUMMARIES = {
    DecisionRecommendation.ACCEPT: (
        "AI đề xuất chấp nhận hợp đồng dựa trên các lý do được chọn từ hồ sơ."
    ),
    DecisionRecommendation.NEGOTIATE_CONDITIONS_TO_ACCEPT: (
        "AI đề xuất chấp nhận có điều kiện dựa trên các lý do và điều kiện "
        "được chọn từ hồ sơ."
    ),
    DecisionRecommendation.DO_NOT_ACCEPT: (
        "AI đề xuất từ chối hợp đồng dựa trên các lý do được chọn từ hồ sơ."
    ),
    DecisionRecommendation.NOT_EVALUABLE: (
        "AI chưa thể đưa ra đề xuất có đủ cơ sở từ hồ sơ hiện có."
    ),
}
_SAFE_ATTENTION_TEXT = (
    "Founder cần xem xét điểm kiểm soát được tham chiếu trước khi quyết định."
)


def canonicalize_decision_proposal(
    proposal: AIDecisionProposalDraft,
    packet: DecisionScenarioPacket,
) -> AIDecisionProposalDraft:
    """Hydrate model selections from deterministic candidates before validation.

    The model may select candidates by their stable business code without having to
    reproduce every evidence ID and nested target byte-for-byte. Mandatory unresolved
    conditions are always attached by deterministic policy for a negotiation proposal.
    """

    reasons_by_code = {item.code: item for item in packet.reason_candidates}
    if len(reasons_by_code) != len(packet.reason_candidates):
        raise ValueError("Decision packet reason candidate codes must be unique.")
    canonical_reasons = tuple(
        AIDecisionReasonDraft.model_validate(
            reasons_by_code[item.code].model_dump(
                mode="json", exclude={"candidate_id"}
            )
        )
        if item.code in reasons_by_code
        else item
        for item in proposal.reasons
    )
    canonical_reason_by_code = {item.code: item for item in canonical_reasons}
    canonical_actions = tuple(
        AIDecisionRecommendedActionDraft(
            reason_code=item.reason_code,
            action=item.action,
            source_reference_ids=canonical_reason_by_code[item.reason_code].source_reference_ids,
            evidence_ids=canonical_reason_by_code[item.reason_code].evidence_ids,
        )
        if item.reason_code in canonical_reason_by_code
        else item
        for item in proposal.recommended_actions
    )

    conditions_by_code = {item.code: item for item in packet.condition_candidates}
    if len(conditions_by_code) != len(packet.condition_candidates):
        raise ValueError("Decision packet condition candidate codes must be unique.")
    if proposal.recommendation is DecisionRecommendation.NEGOTIATE_CONDITIONS_TO_ACCEPT:
        selected_condition_candidates = tuple(
            item
            for item in packet.condition_candidates
            if item.status
            in {DecisionConditionStatus.OPEN, DecisionConditionStatus.NOT_EVALUABLE}
        )
    else:
        selected_condition_candidates = tuple(
            conditions_by_code.get(item.code, item)
            for item in proposal.conditions
        )
    canonical_conditions = tuple(
        NegotiationConditionDraft.model_validate(
            item.model_dump(mode="json", exclude={"candidate_id"})
        )
        for item in selected_condition_candidates
    )

    selected_strategy_ids = list(proposal.selected_negotiation_strategy_ids)
    if proposal.recommendation is DecisionRecommendation.NEGOTIATE_CONDITIONS_TO_ACCEPT:
        selected_codes = {item.code for item in canonical_conditions}
        for condition_code in selected_codes:
            matching = tuple(
                item
                for item in packet.negotiation_strategy_candidates
                if item.condition_code == condition_code
            )
            already_selected = tuple(
                item
                for item in matching
                if item.strategy_id in selected_strategy_ids
            )
            if not already_selected and len(matching) == 1:
                selected_strategy_ids.append(matching[0].strategy_id)

    return proposal.model_copy(
        update={
            "reasons": canonical_reasons,
            "recommended_actions": canonical_actions,
            "conditions": canonical_conditions,
            "selected_negotiation_strategy_ids": tuple(selected_strategy_ids),
        }
    )


def repair_ungrounded_numeric_prose(
    proposal: AIDecisionProposalDraft,
) -> AIDecisionProposalDraft:
    """Replace only unsafe free prose while preserving every AI selection.

    Recommendation, reason candidates, conditions, option IDs, strategy IDs,
    confidence, control references, and evidence lineage remain unchanged. This
    repair never copies, derives, or calculates a numeric value.
    """

    return proposal.model_copy(
        update={
            "executive_summary": _SAFE_EXECUTIVE_SUMMARIES[
                proposal.recommendation
            ],
            "human_attention_points": tuple(
                item.model_copy(update={"text": _SAFE_ATTENTION_TEXT})
                for item in proposal.human_attention_points
            ),
        }
    )


def decision_composer_cache_key(
    packet: DecisionScenarioPacket,
    *,
    model: str,
    prompt_version: str,
    prompt: str,
) -> str:
    """Key persisted-output reuse by exact packet, model, version, and prompt bytes."""

    prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    return deterministic_id(
        "DCC",
        decision_packet_input_hash(packet),
        model,
        prompt_version,
        prompt_hash,
    )


def _validate_references(
    *,
    source_reference_ids: tuple[str, ...],
    evidence_ids: tuple[str, ...],
    packet: DecisionScenarioPacket,
) -> None:
    by_reference = {
        item.reference_id: frozenset(item.evidence_ids)
        for item in packet.reference_evidence
    }
    if not set(source_reference_ids).issubset(by_reference):
        raise ValueError("Decision proposal references an unknown source reference.")
    authorized_evidence = {
        evidence_id
        for reference_id in source_reference_ids
        for evidence_id in by_reference[reference_id]
    }
    if not set(evidence_ids).issubset(authorized_evidence):
        raise ValueError("Decision proposal evidence is not authorized by its source references.")


def _validate_candidate_selections(
    proposal: AIDecisionProposalDraft,
    packet: DecisionScenarioPacket,
) -> None:
    if proposal.recommendation not in packet.allowed_recommendations:
        raise ValueError("Decision recommendation is outside the deterministic eligibility set.")

    def candidate_key(item: BaseModel) -> str:
        return json.dumps(
            item.model_dump(mode="json", exclude={"candidate_id"}),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )

    reason_candidates = {candidate_key(item) for item in packet.reason_candidates}
    if any(candidate_key(reason) not in reason_candidates for reason in proposal.reasons):
        raise ValueError("Decision proposal contains a reason outside supplied candidates.")
    condition_candidates = {
        candidate_key(item) for item in packet.condition_candidates
    }
    if any(
        candidate_key(condition) not in condition_candidates
        for condition in proposal.conditions
    ):
        raise ValueError("Decision proposal contains a condition outside supplied candidates.")

    collections = (
        ("reason codes", tuple(item.code for item in proposal.reasons)),
        ("condition codes", tuple(item.code for item in proposal.conditions)),
        (
            "human-attention codes",
            tuple(item.code for item in proposal.human_attention_points),
        ),
        (
            "recommended-action reason codes",
            tuple(item.reason_code for item in proposal.recommended_actions),
        ),
        (
            "negotiation strategy IDs",
            proposal.selected_negotiation_strategy_ids,
        ),
        ("selected option IDs", proposal.selected_option_ids),
    )
    for label, values in collections:
        if len(set(values)) != len(values):
            raise ValueError(f"Decision proposal {label} must be unique.")

    selected_reason_codes = {item.code for item in proposal.reasons}
    action_reason_codes = {item.reason_code for item in proposal.recommended_actions}
    if proposal.recommendation is DecisionRecommendation.NOT_EVALUABLE:
        if proposal.recommended_actions:
            raise ValueError("NOT_EVALUABLE cannot carry recommended actions.")
    elif action_reason_codes != selected_reason_codes:
        raise ValueError(
            "Each selected Decision reason requires exactly one recommended action."
        )

    known_options = {option.option_id for option in packet.banking_options}
    if not set(proposal.selected_option_ids).issubset(known_options):
        raise ValueError("Decision proposal selects an unknown Banking option.")
    if len(proposal.selected_option_ids) > 1:
        selected = tuple(sorted(proposal.selected_option_ids))
        allowed = {
            tuple(sorted(combination))
            for combination in packet.allowed_option_combinations
        }
        if selected not in allowed:
            raise ValueError("Decision proposal selects an unconfigured option combination.")
    strategies_by_id = {
        item.strategy_id: item for item in packet.negotiation_strategy_candidates
    }
    if not set(proposal.selected_negotiation_strategy_ids).issubset(
        strategies_by_id
    ):
        raise ValueError("Decision proposal selects an unknown negotiation strategy.")
    selected_condition_codes = {item.code for item in proposal.conditions}
    if any(
        strategies_by_id[strategy_id].condition_code not in selected_condition_codes
        for strategy_id in proposal.selected_negotiation_strategy_ids
    ):
        raise ValueError(
            "Decision proposal selects a strategy for an unselected condition."
        )


def _validate_recommendation_shape(
    proposal: AIDecisionProposalDraft,
    packet: DecisionScenarioPacket,
) -> None:
    open_candidate_codes = {
        candidate.code
        for candidate in packet.condition_candidates
        if candidate.status
        in {DecisionConditionStatus.OPEN, DecisionConditionStatus.NOT_EVALUABLE}
    }
    selected_condition_codes = {condition.code for condition in proposal.conditions}

    if (
        proposal.recommendation is not DecisionRecommendation.NOT_EVALUABLE
        and proposal.confidence is DecisionConfidence.NOT_EVALUABLE
    ):
        raise ValueError("A proposed recommendation requires an evaluable confidence.")

    if proposal.recommendation is DecisionRecommendation.ACCEPT:
        if open_candidate_codes:
            raise ValueError(
                "ACCEPT is invalid while a supplied mandatory condition is unresolved."
            )
        if proposal.conditions:
            raise ValueError("ACCEPT cannot carry negotiation conditions.")
        if proposal.selected_negotiation_strategy_ids:
            raise ValueError("ACCEPT cannot carry a negotiation strategy.")
    elif proposal.recommendation is DecisionRecommendation.NEGOTIATE_CONDITIONS_TO_ACCEPT:
        if not open_candidate_codes:
            raise ValueError("NEGOTIATE requires at least one unresolved supplied condition.")
        if not open_candidate_codes.issubset(selected_condition_codes):
            raise ValueError("NEGOTIATE must preserve every unresolved supplied condition.")
        strategies_by_id = {
            item.strategy_id: item for item in packet.negotiation_strategy_candidates
        }
        strategy_condition_codes = {
            item.condition_code for item in packet.negotiation_strategy_candidates
        }
        for condition_code in selected_condition_codes & strategy_condition_codes:
            selected_for_condition = tuple(
                strategy_id
                for strategy_id in proposal.selected_negotiation_strategy_ids
                if strategies_by_id[strategy_id].condition_code == condition_code
            )
            if len(selected_for_condition) != 1:
                raise ValueError(
                    "NEGOTIATE must select exactly one supplied strategy for each "
                    "strategy-backed condition."
                )
    elif proposal.recommendation in {
        DecisionRecommendation.DO_NOT_ACCEPT,
        DecisionRecommendation.NOT_EVALUABLE,
    }:
        if proposal.selected_option_ids:
            raise ValueError("A non-proceeding recommendation cannot select a Banking option.")
        if proposal.selected_negotiation_strategy_ids:
            raise ValueError(
                "A non-proceeding recommendation cannot select a negotiation strategy."
            )
        if proposal.conditions:
            raise ValueError(
                "A non-proceeding recommendation cannot select negotiation conditions."
            )
        if (
            proposal.recommendation is DecisionRecommendation.NOT_EVALUABLE
            and proposal.confidence is not DecisionConfidence.NOT_EVALUABLE
        ):
            raise ValueError("NOT_EVALUABLE requires NOT_EVALUABLE confidence.")


def validate_decision_proposal(
    proposal: AIDecisionProposalDraft,
    packet: DecisionScenarioPacket,
) -> None:
    """Reject invented candidates, evidence, numbers, and protected-action claims."""

    if proposal.calculations_performed_by_model:
        raise ValueError("OpenAI cannot perform Decision calculations.")
    _validate_candidate_selections(proposal, packet)
    _validate_recommendation_shape(proposal, packet)

    for reason in proposal.reasons:
        _validate_references(
            source_reference_ids=reason.source_reference_ids,
            evidence_ids=reason.evidence_ids,
            packet=packet,
        )
    reasons_by_code = {item.code: item for item in proposal.reasons}
    for action in proposal.recommended_actions:
        reason = reasons_by_code.get(action.reason_code)
        if reason is None:
            raise ValueError("Decision action references an unselected reason.")
        if (
            action.source_reference_ids != reason.source_reference_ids
            or action.evidence_ids != reason.evidence_ids
        ):
            raise ValueError(
                "Decision action lineage must exactly match its selected reason."
            )
        _validate_references(
            source_reference_ids=action.source_reference_ids,
            evidence_ids=action.evidence_ids,
            packet=packet,
        )
    for condition in proposal.conditions:
        _validate_references(
            source_reference_ids=condition.source_reference_ids,
            evidence_ids=condition.evidence_ids,
            packet=packet,
        )
        if condition.target is not None:
            _validate_references(
                source_reference_ids=condition.target.source_reference_ids,
                evidence_ids=condition.target.evidence_ids,
                packet=packet,
            )
    for point in proposal.human_attention_points:
        reference_kinds = {
            item.reference_id: item.kind for item in packet.reference_evidence
        }
        if any(
            reference_kinds.get(reference_id)
            is not DecisionReferenceKind.REQUIRED_CONTROL
            for reference_id in point.source_reference_ids
        ):
            raise ValueError(
                "Decision attention points must reference supplied required controls."
            )
        _validate_references(
            source_reference_ids=point.source_reference_ids,
            evidence_ids=point.evidence_ids,
            packet=packet,
        )
    strategies_by_id = {
        item.strategy_id: item for item in packet.negotiation_strategy_candidates
    }
    for strategy_id in proposal.selected_negotiation_strategy_ids:
        strategy = strategies_by_id[strategy_id]
        _validate_references(
            source_reference_ids=strategy.source_reference_ids,
            evidence_ids=strategy.evidence_ids,
            packet=packet,
        )

    validate_decision_proposal_prose(proposal=proposal, packet=packet)
