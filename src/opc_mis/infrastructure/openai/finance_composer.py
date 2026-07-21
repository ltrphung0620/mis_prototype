"""Bounded OpenAI Structured Outputs adapter for Finance prose only."""

import json
from pathlib import Path

from openai import AsyncOpenAI, OpenAIError
from pydantic import ValidationError

from opc_mis.domain.enums import FinanceNarrativeSource
from opc_mis.domain.finance_models import (
    FinanceComposerInput,
    FinanceNarrative,
    FinanceNarrativeComposition,
)
from opc_mis.infrastructure.openai.fallback import DeterministicFinanceNarrativeComposer
from opc_mis.infrastructure.openai.narrative_guard import (
    founder_display_value,
    validate_narrative,
)


class OpenAIFinanceNarrativeComposer:
    """Ask OpenAI to phrase verified facts without calculating or classifying them."""

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

    async def compose(self, payload: FinanceComposerInput) -> FinanceNarrativeComposition:
        model_payload = payload.model_dump(mode="json")
        for serialized, fact in zip(model_payload["facts"], payload.facts, strict=True):
            serialized["founder_display_value"] = founder_display_value(fact)
        response = await self._client.responses.parse(
            model=self._model,
            input=[
                {"role": "system", "content": self._prompt},
                {
                    "role": "user",
                    "content": json.dumps(
                        model_payload,
                        ensure_ascii=False,
                        sort_keys=True,
                        allow_nan=False,
                    ),
                },
            ],
            text_format=FinanceNarrative,
        )
        narrative = response.output_parsed
        if narrative is None:
            raise ValueError("OpenAI response did not contain a parsed Finance narrative.")
        validate_narrative(narrative, payload)
        return FinanceNarrativeComposition(
            narrative=narrative,
            source=FinanceNarrativeSource.OPENAI,
            model=self._model,
            prompt_version=self._prompt_version,
        )


class ResilientFinanceNarrativeComposer:
    """Use deterministic prose when an expected model or validation error occurs."""

    def __init__(
        self,
        primary: OpenAIFinanceNarrativeComposer,
        fallback: DeterministicFinanceNarrativeComposer | None = None,
    ) -> None:
        self._primary = primary
        self._fallback = fallback or DeterministicFinanceNarrativeComposer()

    async def compose(self, payload: FinanceComposerInput) -> FinanceNarrativeComposition:
        try:
            return await self._primary.compose(payload)
        except (OpenAIError, ValidationError, ValueError) as exc:
            return await self._fallback.compose(
                payload,
                fallback_reason=type(exc).__name__,
            )
