"""Conservative deterministic fallback for unavailable Decision composition."""

from opc_mis.domain.decision_models import (
    AIDecisionComposition,
    AIDecisionProposalDraft,
    AIDecisionReasonDraft,
    DecisionAnalysisSource,
    DecisionConditionStatus,
    DecisionConfidence,
    DecisionRecommendation,
    DecisionScenarioPacket,
    decision_packet_input_hash,
)
from opc_mis.infrastructure.openai.decision_guard import validate_decision_proposal


class DeterministicDecisionAnalysisComposer:
    """Return the strongest proposal that requires no subjective strategy choice."""

    model_name = "deterministic-template"
    prompt_version = "decision-analysis-fallback-v3"

    async def compose(
        self,
        payload: DecisionScenarioPacket,
        *,
        fallback_reason: str = "OPENAI_NOT_CONFIGURED",
    ) -> AIDecisionComposition:
        reasons = tuple(
            AIDecisionReasonDraft.model_validate(
                candidate.model_dump(mode="json", exclude={"candidate_id"})
            )
            for candidate in payload.reason_candidates
        )
        unresolved = tuple(
            item
            for item in payload.condition_candidates
            if item.status
            in {DecisionConditionStatus.OPEN, DecisionConditionStatus.NOT_EVALUABLE}
        )
        selected_strategy_ids: list[str] = []
        strategy_ambiguous = False
        for condition in unresolved:
            matching = tuple(
                item
                for item in payload.negotiation_strategy_candidates
                if item.condition_code == condition.code
            )
            if len(matching) == 1:
                selected_strategy_ids.append(matching[0].strategy_id)
            elif len(matching) > 1:
                strategy_ambiguous = True
        can_negotiate = (
            DecisionRecommendation.NEGOTIATE_CONDITIONS_TO_ACCEPT
            in payload.allowed_recommendations
            and bool(unresolved)
            and not strategy_ambiguous
        )
        recommendation = (
            DecisionRecommendation.NEGOTIATE_CONDITIONS_TO_ACCEPT
            if can_negotiate
            else DecisionRecommendation.NOT_EVALUABLE
        )
        proposal = AIDecisionProposalDraft(
            recommendation=recommendation,
            executive_summary=(
                "Có cơ sở để tiếp tục theo hướng đàm phán có điều kiện; mọi điều kiện "
                "bắt buộc vẫn phải được xác minh trước khi Founder chấp nhận."
                if can_negotiate
                else "Chưa thể tạo đề xuất quyết định tự động; Founder cần xem trực tiếp "
                "các dữ kiện, giới hạn bằng chứng và lựa chọn chiến lược còn chưa xác định."
            ),
            reasons=reasons,
            conditions=tuple(
                item.model_dump(mode="json", exclude={"candidate_id"})
                for item in unresolved
            ) if can_negotiate else (),
            selected_negotiation_strategy_ids=(
                tuple(selected_strategy_ids) if can_negotiate else ()
            ),
            selected_option_ids=(),
            confidence=(
                DecisionConfidence.LOW
                if can_negotiate
                else DecisionConfidence.NOT_EVALUABLE
            ),
            human_attention_points=(),
            calculations_performed_by_model=False,
        )
        validate_decision_proposal(proposal, payload)
        return AIDecisionComposition(
            proposal=proposal,
            source=DecisionAnalysisSource.DETERMINISTIC_FALLBACK,
            model=self.model_name,
            prompt_version=self.prompt_version,
            input_hash=decision_packet_input_hash(payload),
            fallback_reason=fallback_reason,
        )
