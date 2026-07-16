"""Boundary, fallback, validation, and identity tests for Finance."""

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from opc_mis.business.agents.finance.component import FinanceAgent
from opc_mis.business.agents.finance.requirements import FinanceRequirementFailure
from opc_mis.domain.artifacts import ArtifactDraft
from opc_mis.domain.components import ExecutionContext
from opc_mis.domain.enums import (
    ArtifactType,
    ComponentStatus,
    EvaluationScope,
    FinanceCalculation,
    FinanceDataScope,
    FinanceFactQuality,
    FinanceMetric,
    FinanceNarrativeSource,
    FinanceUnit,
    ValidationStatus,
)
from opc_mis.domain.finance_models import (
    FinanceAssessment,
    FinanceComposerInput,
    FinanceFact,
    FinanceNarrative,
    FinanceNarrativeStatement,
)
from opc_mis.governance.evidence_validator import EvidenceValidator
from opc_mis.infrastructure.openai.fallback import DeterministicFinanceNarrativeComposer
from opc_mis.infrastructure.openai.finance_composer import (
    OpenAIFinanceNarrativeComposer,
    ResilientFinanceNarrativeComposer,
)
from opc_mis.infrastructure.openai.narrative_guard import validate_narrative
from opc_mis.workflow.artifact_factory import artifact_input_hash


def fact() -> FinanceFact:
    return FinanceFact(
        fact_id="FACT-VERIFIED",
        metric=FinanceMetric.CONTRACT_VALUE,
        value=100.0,
        unit=FinanceUnit.VND,
        scope=FinanceDataScope.CASE_SPECIFIC,
        quality=FinanceFactQuality.VERIFIED,
        calculation=FinanceCalculation.SOURCE_VALUE,
        evidence_id="EVD-SOURCE",
        source_evidence_ids=("EVD-SOURCE",),
    )


def composer_input() -> FinanceComposerInput:
    return FinanceComposerInput(facts=(fact(),), observations=(), limitations=())


class InvalidPrimaryComposer:
    async def compose(self, payload: FinanceComposerInput) -> object:
        del payload
        raise ValueError("invalid structured output")


def test_expected_openai_validation_failure_uses_deterministic_fallback() -> None:
    composer = ResilientFinanceNarrativeComposer(
        InvalidPrimaryComposer(),  # type: ignore[arg-type]
        DeterministicFinanceNarrativeComposer(),
    )

    result = asyncio.run(composer.compose(composer_input()))

    assert result.source is FinanceNarrativeSource.DETERMINISTIC_FALLBACK
    assert result.fallback_reason == "ValueError"


def test_openai_adapter_accepts_valid_structured_output_without_live_call() -> None:
    narrative = FinanceNarrative(
        headline="Tổng hợp đã xác minh",
        statements=(
            FinanceNarrativeStatement(
                statement_id="STATEMENT-X",
                text="Dữ kiện hợp đồng đã được ghi nhận.",
                fact_ids=("FACT-VERIFIED",),
            ),
        ),
    )

    class FakeResponses:
        async def parse(self, **kwargs: object) -> object:
            assert kwargs["text_format"] is FinanceNarrative
            return SimpleNamespace(output_parsed=narrative)

    client = SimpleNamespace(responses=FakeResponses())
    composer = OpenAIFinanceNarrativeComposer(
        client=client,  # type: ignore[arg-type]
        model="MODEL-X",
        prompt_path=Path("config/prompts/finance_narrative.md"),
        prompt_version="PROMPT-X",
    )

    result = asyncio.run(composer.compose(composer_input()))

    assert result.source is FinanceNarrativeSource.OPENAI
    assert result.narrative == narrative


def test_narrative_guard_rejects_numeric_and_downstream_claims() -> None:
    narrative = FinanceNarrative(
        headline="Tổng hợp đã xác minh",
        statements=(
            FinanceNarrativeStatement(
                statement_id="STATEMENT-X",
                text="Có rủi ro mức 5.",
                fact_ids=("FACT-VERIFIED",),
            ),
        ),
    )

    with pytest.raises(ValueError):
        validate_narrative(narrative, composer_input())


def test_evidence_validator_rejects_injected_risk_field() -> None:
    narrative = FinanceNarrative(
        headline="Tổng hợp đã xác minh",
        statements=(
            FinanceNarrativeStatement(
                statement_id="STATEMENT-X",
                text="Dữ kiện hợp đồng đã được ghi nhận.",
                fact_ids=("FACT-VERIFIED",),
            ),
        ),
    )
    assessment = FinanceAssessment(
        evaluation_case_id="CASE-X",
        dataset_id="DATASET-X",
        contract_id="CONTRACT-X",
        assessment_status="COMPLETE",
        facts_input_hash="HASH-X",
        fact_ids=("FACT-VERIFIED",),
        observations=(),
        limitations=(),
        narrative=narrative,
        narrative_source="DETERMINISTIC_FALLBACK",
        composer_model="deterministic-template",
        prompt_version="finance-narrative-v1",
    )
    payload = assessment.model_dump(mode="json")
    payload["risk_level"] = "HIGH"
    draft = ArtifactDraft(
        artifact_type=ArtifactType.FINANCE_ASSESSMENT,
        evaluation_case_id="CASE-X",
        producer="FINANCE_AGENT",
        payload=payload,
    )

    report = asyncio.run(EvidenceValidator().validate(draft))

    assert report.status is ValidationStatus.BLOCKED


def test_assessment_identity_ignores_nondeterministic_wording() -> None:
    context = ExecutionContext(
        evaluation_case_id="CASE-X",
        dataset_id="DATASET-X",
        workflow_run_id="RUN-X",
        input_artifact_ids=("ART-FACTS",),
        requested_scope=(EvaluationScope.FINANCE,),
        component_input={},
        current_node="FINANCE_ASSESSMENT",
    )
    common = {
        "artifact_type": ArtifactType.FINANCE_ASSESSMENT,
        "evaluation_case_id": "CASE-X",
        "producer": "FINANCE_AGENT",
        "identity_inputs": {"facts_input_hash": "FACTS-HASH", "prompt_version": "V-X"},
    }
    first = ArtifactDraft(payload={"narrative": "wording A"}, **common)
    second = ArtifactDraft(payload={"narrative": "wording B"}, **common)

    assert artifact_input_hash(first, context) == artifact_input_hash(second, context)


def test_actual_finance_blocker_pauses_without_artifacts_or_signals() -> None:
    failure = FinanceRequirementFailure(
        code="FINANCE_ORDER_VALUE_INVALID",
        target_record="ORDER-X",
        field="order_revenue",
        expected_type="finite number",
        reason="Required deterministic input is missing.",
    )
    loader = SimpleNamespace(
        load=lambda context: None,
    )

    async def load(context: ExecutionContext) -> object:
        del context
        return SimpleNamespace(
            failures=(failure,),
            evaluation_case=SimpleNamespace(evaluation_case_id="CASE-X"),
        )

    loader.load = load
    agent = FinanceAgent(
        context_loader=loader,  # type: ignore[arg-type]
        narrative_composer=DeterministicFinanceNarrativeComposer(),
    )
    context = ExecutionContext(
        evaluation_case_id="CASE-X",
        dataset_id="DATASET-X",
        workflow_run_id="RUN-X",
        input_artifact_ids=(),
        requested_scope=(EvaluationScope.FINANCE,),
        component_input={},
        current_node="FINANCE_ASSESSMENT",
    )

    result = asyncio.run(agent.execute(context))

    assert result.status is ComponentStatus.WAITING_FOR_INPUT
    assert len(result.missing_data_requests) == 1
    assert result.artifacts == ()
    assert result.approval_signals == ()
    assert result.action_commands == ()
