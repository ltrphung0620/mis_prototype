"""OpenAI Structured Outputs adapter for evidence-bound Decision proposals."""

import json
from pathlib import Path

from openai import AsyncOpenAI, OpenAIError
from pydantic import ValidationError

from opc_mis.domain.decision_models import (
    AIDecisionComposition,
    AIDecisionProposalDraft,
    DecisionAnalysisSource,
    DecisionScenarioPacket,
    decision_packet_input_hash,
)
from opc_mis.infrastructure.openai.decision_fallback import (
    DeterministicDecisionAnalysisComposer,
)
from opc_mis.infrastructure.openai.decision_guard import (
    decision_composer_cache_key,
    validate_decision_proposal,
)


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
        response = await self._client.responses.parse(
            model=self._model,
            store=False,
            input=[
                {"role": "system", "content": self._prompt},
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
            text_format=AIDecisionProposalDraft,
        )
        proposal = response.output_parsed
        if proposal is None:
            raise ValueError("OpenAI response did not contain a parsed Decision proposal.")
        validate_decision_proposal(proposal, payload)
        return AIDecisionComposition(
            proposal=proposal,
            source=DecisionAnalysisSource.OPENAI,
            model=self._model,
            prompt_version=self._prompt_version,
            input_hash=decision_packet_input_hash(payload),
        )


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
                fallback_reason=type(exc).__name__,
            )
