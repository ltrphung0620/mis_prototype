"""OpenAI Structured Outputs adapter for evidence-bound Decision proposals."""

import json
from pathlib import Path

from openai import AsyncOpenAI, OpenAIError
from pydantic import BaseModel, ConfigDict, Field, StrictStr, ValidationError

from opc_mis.domain.decision_models import (
    AIDecisionComposition,
    AIDecisionProposalDraft,
    AIDecisionReasonDraft,
    AIDecisionRecommendedActionDraft,
    DecisionAnalysisSource,
    DecisionConditionStatus,
    DecisionConfidence,
    DecisionRecommendation,
    DecisionScenarioPacket,
    NegotiationConditionDraft,
    decision_packet_input_hash,
)
from opc_mis.infrastructure.openai.decision_fallback import (
    DeterministicDecisionAnalysisComposer,
)
from opc_mis.infrastructure.openai.decision_guard import (
    canonicalize_decision_proposal,
    decision_composer_cache_key,
    validate_decision_proposal,
)


class _DecisionActionSelection(BaseModel):
    """Compact model-authored action; deterministic code restores its lineage."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    reason_code: StrictStr = Field(min_length=1)
    action: StrictStr = Field(min_length=1)


class _DecisionProposalSelection(BaseModel):
    """Minimal Structured Output containing only choices OpenAI must make."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    recommendation: DecisionRecommendation
    executive_summary: StrictStr = Field(min_length=1)
    reason_codes: tuple[StrictStr, ...] = Field(min_length=1)
    recommended_actions: tuple[_DecisionActionSelection, ...] = ()
    selected_negotiation_strategy_ids: tuple[StrictStr, ...] = ()
    selected_option_ids: tuple[StrictStr, ...] = ()
    confidence: DecisionConfidence


class OpenAIDecisionAnalysisComposer:
    """Ask OpenAI to select and explain exact deterministic Decision candidates."""

    def __init__(
        self,
        *,
        client: AsyncOpenAI,
        model: str,
        prompt_path: Path,
        prompt_version: str,
    ) -> None:
        self._client = client
        self._model = model
        self._prompt = prompt_path.read_text(encoding="utf-8")
        self._prompt_version = prompt_version

    def cache_key(self, payload: DecisionScenarioPacket) -> str:
        """Return the exact key a workflow cache must use before invoking OpenAI."""

        return decision_composer_cache_key(
            payload,
            model=self._model,
            prompt_version=self._prompt_version,
            prompt=self._prompt,
        )

    async def compose(self, payload: DecisionScenarioPacket) -> AIDecisionComposition:
        try:
            selection = await self._request_selection(payload)
            proposal = self._proposal_from_selection(selection, payload)
            proposal = self._validate_proposal(proposal, payload)
        except (ValidationError, ValueError) as exc:
            selection = await self._request_selection(
                payload,
                repair_instruction=_repair_instruction(exc),
            )
            proposal = self._proposal_from_selection(selection, payload)
            proposal = self._validate_proposal(proposal, payload)
        return AIDecisionComposition(
            proposal=proposal,
            source=DecisionAnalysisSource.OPENAI,
            model=self._model,
            prompt_version=self._prompt_version,
            input_hash=decision_packet_input_hash(payload),
        )

    async def _request_selection(
        self,
        payload: DecisionScenarioPacket,
        *,
        repair_instruction: str | None = None,
    ) -> _DecisionProposalSelection:
        system_content = self._prompt
        if repair_instruction is not None:
            system_content = f"{system_content}\n\n{repair_instruction}"
        response = await self._client.responses.parse(
            model=self._model,
            store=False,
            input=[
                {"role": "system", "content": system_content},
                {
                    "role": "user",
                    "content": json.dumps(
                        payload.model_dump(mode="json"),
                        ensure_ascii=False,
                        sort_keys=True,
                        allow_nan=False,
                    ),
                },
            ],
            text_format=_DecisionProposalSelection,
        )
        selection = response.output_parsed
        if selection is None:
            if _response_contains_refusal(response):
                raise ValueError("OpenAI refused to create a Decision proposal.")
            raise ValueError("OpenAI response did not contain a parsed Decision proposal.")
        return selection

    @staticmethod
    def _proposal_from_selection(
        selection: _DecisionProposalSelection | AIDecisionProposalDraft,
        payload: DecisionScenarioPacket,
    ) -> AIDecisionProposalDraft:
        """Restore exact candidates and lineage without changing the AI choices."""

        if isinstance(selection, AIDecisionProposalDraft):
            return canonicalize_decision_proposal(selection, payload)

        if len(set(selection.reason_codes)) != len(selection.reason_codes):
            raise ValueError("Decision proposal reason codes must be unique.")
        reasons_by_code = {item.code: item for item in payload.reason_candidates}
        unknown_reason_codes = set(selection.reason_codes) - set(reasons_by_code)
        if unknown_reason_codes:
            raise ValueError("Decision proposal selected an unknown reason code.")
        reasons = tuple(
            AIDecisionReasonDraft.model_validate(
                reasons_by_code[code].model_dump(
                    mode="json",
                    exclude={"candidate_id"},
                )
            )
            for code in selection.reason_codes
        )
        canonical_reason_by_code = {item.code: item for item in reasons}
        action_codes = tuple(
            item.reason_code for item in selection.recommended_actions
        )
        if len(set(action_codes)) != len(action_codes):
            raise ValueError(
                "Decision proposal supplied duplicate actions for a selected reason."
            )
        if set(action_codes) - set(canonical_reason_by_code):
            raise ValueError("Decision action references an unselected reason.")
        actions = tuple(
            AIDecisionRecommendedActionDraft(
                reason_code=item.reason_code,
                action=item.action,
                source_reference_ids=canonical_reason_by_code[
                    item.reason_code
                ].source_reference_ids,
                evidence_ids=canonical_reason_by_code[item.reason_code].evidence_ids,
            )
            for item in selection.recommended_actions
        )
        conditions = (
            tuple(
                NegotiationConditionDraft.model_validate(
                    item.model_dump(mode="json", exclude={"candidate_id"})
                )
                for item in payload.condition_candidates
                if item.status
                in {
                    DecisionConditionStatus.OPEN,
                    DecisionConditionStatus.NOT_EVALUABLE,
                }
            )
            if selection.recommendation
            is DecisionRecommendation.NEGOTIATE_CONDITIONS_TO_ACCEPT
            else ()
        )
        return AIDecisionProposalDraft(
            recommendation=selection.recommendation,
            executive_summary=selection.executive_summary,
            reasons=reasons,
            recommended_actions=actions,
            conditions=conditions,
            selected_negotiation_strategy_ids=(
                selection.selected_negotiation_strategy_ids
            ),
            selected_option_ids=selection.selected_option_ids,
            confidence=selection.confidence,
            human_attention_points=(),
            calculations_performed_by_model=False,
        )

    @staticmethod
    def _validate_proposal(
        proposal: AIDecisionProposalDraft,
        payload: DecisionScenarioPacket,
    ) -> AIDecisionProposalDraft:
        proposal = canonicalize_decision_proposal(proposal, payload)
        validate_decision_proposal(proposal, payload)
        return proposal


class ResilientDecisionAnalysisComposer:
    """Use a conservative proposal for expected API, schema, or guard failures."""

    def __init__(
        self,
        primary: OpenAIDecisionAnalysisComposer,
        fallback: DeterministicDecisionAnalysisComposer | None = None,
    ) -> None:
        self._primary = primary
        self._fallback = fallback or DeterministicDecisionAnalysisComposer()

    def cache_key(self, payload: DecisionScenarioPacket) -> str:
        """Expose the primary call identity without invoking either composer."""

        return self._primary.cache_key(payload)

    async def compose(self, payload: DecisionScenarioPacket) -> AIDecisionComposition:
        try:
            return await self._primary.compose(payload)
        except (OpenAIError, ValidationError, ValueError) as exc:
            return await self._fallback.compose(
                payload,
                fallback_reason=_fallback_reason(exc),
            )


def _fallback_reason(exc: OpenAIError | ValidationError | ValueError) -> str:
    """Return a stable, non-sensitive diagnostic code for expected failures."""

    if isinstance(exc, OpenAIError):
        return type(exc).__name__
    if isinstance(exc, ValidationError):
        return "OPENAI_OUTPUT_SCHEMA_INVALID"
    message = str(exc).casefold()
    mappings = (
        ("did not contain a parsed Decision proposal", "OPENAI_OUTPUT_NOT_PARSED"),
        ("refused to create a Decision proposal", "OPENAI_REFUSAL"),
        ("outside the deterministic eligibility set", "RECOMMENDATION_NOT_ELIGIBLE"),
        ("unknown reason code", "UNKNOWN_REASON_CANDIDATE"),
        ("reason outside supplied candidates", "UNKNOWN_REASON_CANDIDATE"),
        ("condition outside supplied candidates", "UNKNOWN_CONDITION_CANDIDATE"),
        ("preserve every unresolved supplied condition", "MANDATORY_CONDITION_MISSING"),
        ("exactly one supplied strategy", "NEGOTIATION_STRATEGY_INVALID"),
        ("numeric prose outside", "NUMERIC_PROSE_OUTSIDE_EVIDENCE"),
        ("claims an approval", "FORBIDDEN_COMPLETION_CLAIM"),
        ("unresolved condition is already met", "FORBIDDEN_COMPLETION_CLAIM"),
        ("recommended action", "RECOMMENDED_ACTION_INVALID"),
        ("action references", "RECOMMENDED_ACTION_INVALID"),
        ("exactly one action", "RECOMMENDED_ACTION_INVALID"),
        ("duplicate actions", "RECOMMENDED_ACTION_INVALID"),
        ("must be unique", "DUPLICATE_SELECTION"),
        ("evaluable confidence", "CONFIDENCE_INVALID"),
        ("NOT_EVALUABLE requires", "CONFIDENCE_INVALID"),
        ("unknown Banking option", "BANKING_OPTION_INVALID"),
    )
    for fragment, code in mappings:
        if fragment.casefold() in message:
            return code
    return "DECISION_PROPOSAL_INVALID"


def _repair_instruction(exc: ValidationError | ValueError) -> str:
    """Ask the model for a fresh, fully AI-authored proposal after guard failure."""

    reason = _fallback_reason(exc)
    return (
        "The previous structured proposal was rejected by the deterministic validator "
        f"with code {reason}. Generate the complete proposal again from the supplied "
        "packet. Select only exact supplied reason codes, strategy IDs, and option IDs. "
        "For every selected reason in an evaluable recommendation, write exactly one "
        "concrete Founder-actionable recommended action with the same reason_code. Avoid "
        "digits and numeric units in all authored prose unless the exact number and its "
        "business unit are grounded in that selected reason. If the recommendation is "
        "NEGOTIATE, select "
        "exactly one supplied strategy for each strategy-backed condition. If it is "
        "NOT_EVALUABLE, return no actions, strategies, or options and use NOT_EVALUABLE "
        "confidence. Follow every recommendation-shape constraint in the main instruction."
    )


def _response_contains_refusal(response: object) -> bool:
    """Detect a Structured Outputs refusal without retaining refusal prose."""

    for output in getattr(response, "output", ()):
        for item in getattr(output, "content", ()):
            if getattr(item, "type", None) == "refusal":
                return True
    return False
