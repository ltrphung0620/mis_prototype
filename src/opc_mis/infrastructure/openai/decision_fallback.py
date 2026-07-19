"""Conservative deterministic fallback for unavailable Decision composition."""

from opc_mis.domain.decision_models import (
    AIDecisionComposition,
    AIDecisionProposalDraft,
    AIDecisionReasonDraft,
    DecisionAnalysisSource,
    DecisionConfidence,
    DecisionRecommendation,
    DecisionScenarioPacket,
    decision_packet_input_hash,
)
from opc_mis.infrastructure.openai.decision_guard import validate_decision_proposal


class DeterministicDecisionAnalysisComposer:
    """Return NOT_EVALUABLE while preserving exact deterministic reason candidates."""

    model_name = "deterministic-template"
    prompt_version = "decision-analysis-fallback-v2"

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
        proposal = AIDecisionProposalDraft(
            recommendation=DecisionRecommendation.NOT_EVALUABLE,
            executive_summary=(
                "Chưa thể tạo đề xuất quyết định tự động; Founder cần xem trực tiếp "
                "các dữ kiện và giới hạn bằng chứng đã được xác minh."
            ),
            reasons=reasons,
            conditions=(),
            selected_option_ids=(),
            confidence=DecisionConfidence.NOT_EVALUABLE,
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
