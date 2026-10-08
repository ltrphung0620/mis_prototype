"""Bounded OpenAI Structured Outputs adapter for Banking option prose only."""

import json
from pathlib import Path

from openai import AsyncOpenAI, OpenAIError
from pydantic import ValidationError

from opc_mis.domain.banking_models import (
    BankingAdviceComposition,
    BankingAdvisorInput,
    BankingOptionAdviceDraft,
)
from opc_mis.domain.enums import BankingAdviceSource
from opc_mis.infrastructure.openai.banking_advice_guard import validate_banking_advice
from opc_mis.infrastructure.openai.banking_fallback import (
    DeterministicBankingOptionAdvisor,
)


class OpenAIBankingOptionAdvisor:
    """Ask OpenAI to explain configured options without deciding or executing."""

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
        self._not_invoked = DeterministicBankingOptionAdvisor()

    async def compose(self, payload: BankingAdvisorInput) -> BankingAdviceComposition:
        if len(payload.options) < 2:
            return await self._not_invoked.compose(payload)

        response = await self._client.responses.parse(
            model=self._model,
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
            text_format=BankingOptionAdviceDraft,
        )
        advice = response.output_parsed
        if advice is None:
            raise ValueError("OpenAI response did not contain parsed Banking option advice.")
        validate_banking_advice(advice, payload)
        return BankingAdviceComposition(
            advice=advice,
            source=BankingAdviceSource.OPENAI,
            model=self._model,
            prompt_version=self._prompt_version,
        )


class ResilientBankingOptionAdvisor:
    """Fall back safely for expected model, schema, and deterministic guard failures."""

    def __init__(
        self,
        primary: OpenAIBankingOptionAdvisor,
        fallback: DeterministicBankingOptionAdvisor | None = None,
    ) -> None:
        self._primary = primary
        self._fallback = fallback or DeterministicBankingOptionAdvisor()

    async def compose(self, payload: BankingAdvisorInput) -> BankingAdviceComposition:
        if len(payload.options) < 2:
            return await self._fallback.compose(payload)
        try:
            return await self._primary.compose(payload)
        except (OpenAIError, ValidationError, ValueError) as exc:
            return await self._fallback.compose(
                payload,
                fallback_reason=type(exc).__name__,
            )
