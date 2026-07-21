"""Boundary and fallback tests for optional Banking option advice."""

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from opc_mis.domain.banking_models import (
    BankingAdvisorInput,
    BankingAdvisorOption,
    BankingOptionAdviceDraft,
    BankingOptionSuggestionDraft,
)
from opc_mis.domain.enums import (
    BankingAdviceSource,
    BankingDataGapCode,
    BankingNeedType,
)
from opc_mis.infrastructure.openai.banking_advice_guard import validate_banking_advice
from opc_mis.infrastructure.openai.banking_fallback import (
    DeterministicBankingOptionAdvisor,
)
from opc_mis.infrastructure.openai.banking_option_advisor import (
    OpenAIBankingOptionAdvisor,
    ResilientBankingOptionAdvisor,
)


def advisor_option(option_id: str) -> BankingAdvisorOption:
    return BankingAdvisorOption(
        option_id=option_id,
        need_type=BankingNeedType.PERFORMANCE_BOND,
        provider="Ngân hàng mẫu",
        product_name="Bảo lãnh thực hiện hợp đồng",
        criterion_statuses=("NOT_EVALUABLE",),
        limitation_codes=(BankingDataGapCode.REQUESTED_AMOUNT_UNAVAILABLE,),
    )


def advisor_input(*, option_count: int = 2, allow_pair: bool = True) -> BankingAdvisorInput:
    options = tuple(advisor_option(f"BOPT-{index:03d}") for index in range(1, option_count + 1))
    combinations = (("BOPT-001", "BOPT-002"),) if option_count >= 2 and allow_pair else ()
    return BankingAdvisorInput(
        matrix_id="MATRIX-X",
        options=options,
        allowed_option_combinations=combinations,
    )


def valid_advice(*, option_ids: tuple[str, ...] = ("BOPT-001",)) -> BankingOptionAdviceDraft:
    return BankingOptionAdviceDraft(
        overview="Các phương án cần được đọc cùng các giới hạn dữ liệu trong ma trận.",
        suggestions=(
            BankingOptionSuggestionDraft(
                option_ids=option_ids,
                rationale="Phương án này có mô tả phù hợp với nhu cầu đã cấu hình.",
            ),
        ),
    )


def test_openai_adapter_accepts_valid_structured_advice_without_live_call() -> None:
    advice = valid_advice(option_ids=("BOPT-002", "BOPT-001"))

    class FakeResponses:
        async def parse(self, **kwargs: object) -> object:
            assert kwargs["text_format"] is BankingOptionAdviceDraft
            request_input = kwargs["input"]
            user_payload = json.loads(request_input[1]["content"])  # type: ignore[index]
            assert [item["option_id"] for item in user_payload["options"]] == [
                "BOPT-001",
                "BOPT-002",
            ]
            return SimpleNamespace(output_parsed=advice)

    composer = OpenAIBankingOptionAdvisor(
        client=SimpleNamespace(responses=FakeResponses()),  # type: ignore[arg-type]
        model="MODEL-X",
        prompt_path=Path("config/prompts/banking_option_advisor.md"),
        prompt_version="PROMPT-X",
    )

    result = asyncio.run(composer.compose(advisor_input()))

    assert result.source is BankingAdviceSource.OPENAI
    assert result.advice == advice
    assert result.model == "MODEL-X"
    assert result.prompt_version == "PROMPT-X"


@pytest.mark.parametrize("option_count", [0, 1])
def test_openai_adapter_never_calls_model_for_fewer_than_two_options(
    option_count: int,
) -> None:
    class ForbiddenResponses:
        async def parse(self, **kwargs: object) -> object:
            del kwargs
            raise AssertionError("OpenAI must not be called for zero or one option")

    composer = OpenAIBankingOptionAdvisor(
        client=SimpleNamespace(responses=ForbiddenResponses()),  # type: ignore[arg-type]
        model="MODEL-X",
        prompt_path=Path("config/prompts/banking_option_advisor.md"),
        prompt_version="PROMPT-X",
    )

    result = asyncio.run(composer.compose(advisor_input(option_count=option_count)))

    assert result.source is BankingAdviceSource.NOT_INVOKED
    assert result.advice.suggestions == ()


class InvalidPrimaryAdvisor:
    async def compose(self, payload: BankingAdvisorInput) -> object:
        del payload
        raise ValueError("invalid structured or guarded output")


class UnexpectedFailureAdvisor:
    async def compose(self, payload: BankingAdvisorInput) -> object:
        del payload
        raise RuntimeError("programming defect")


def test_expected_schema_or_guard_failure_uses_safe_fallback() -> None:
    composer = ResilientBankingOptionAdvisor(
        InvalidPrimaryAdvisor(),  # type: ignore[arg-type]
        DeterministicBankingOptionAdvisor(),
    )

    result = asyncio.run(composer.compose(advisor_input()))

    assert result.source is BankingAdviceSource.DETERMINISTIC_FALLBACK
    assert result.fallback_reason == "ValueError"
    assert result.advice.suggestions == ()


def test_unexpected_programming_error_is_not_swallowed() -> None:
    composer = ResilientBankingOptionAdvisor(
        UnexpectedFailureAdvisor(),  # type: ignore[arg-type]
        DeterministicBankingOptionAdvisor(),
    )

    with pytest.raises(RuntimeError, match="programming defect"):
        asyncio.run(composer.compose(advisor_input()))


def test_guard_rejects_unknown_option_id() -> None:
    with pytest.raises(ValueError, match="unknown option ID"):
        validate_banking_advice(valid_advice(option_ids=("BOPT-999",)), advisor_input())


def test_guard_rejects_unconfigured_multi_option_set() -> None:
    with pytest.raises(ValueError, match="unconfigured option combination"):
        validate_banking_advice(
            valid_advice(option_ids=("BOPT-001", "BOPT-002")),
            advisor_input(allow_pair=False),
        )


def test_guard_accepts_exact_allowed_set_independent_of_order() -> None:
    validate_banking_advice(
        valid_advice(option_ids=("BOPT-002", "BOPT-001")),
        advisor_input(),
    )


def test_guard_rejects_numeric_prose_outside_known_option_ids() -> None:
    advice = valid_advice().model_copy(
        update={
            "suggestions": (
                valid_advice().suggestions[0].model_copy(
                    update={"rationale": "Chi phí được mô tả là 12 phần trăm."}
                ),
            )
        }
    )

    with pytest.raises(ValueError, match="numeric prose"):
        validate_banking_advice(advice, advisor_input())


@pytest.mark.parametrize(
    "prohibited_claim",
    [
        "Phương án BOPT-001 đã được phê duyệt.",
        "Hồ sơ đã được gửi ngân hàng.",
        "Precheck passed cho BOPT-001.",
        "Đã quyết định dùng BOPT-001.",
    ],
)
def test_guard_rejects_decision_approval_submission_and_precheck_success_claims(
    prohibited_claim: str,
) -> None:
    advice = valid_advice().model_copy(update={"overview": prohibited_claim})

    with pytest.raises(ValueError, match="boundary"):
        validate_banking_advice(advice, advisor_input())
