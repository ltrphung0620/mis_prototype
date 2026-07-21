"""Unit tests for safe Risk parsing, exact linkage, and severity policy."""

import asyncio
from pathlib import Path

from opc_mis.business.agents.risk.component import RiskAgent
from opc_mis.business.agents.risk.rule_engine import parse_condition
from opc_mis.business.agents.risk.severity_policy import aggregate_case_severity
from opc_mis.business.agents.risk.source_scanner import parse_related_record
from opc_mis.domain.components import ExecutionContext
from opc_mis.domain.enums import (
    ComponentStatus,
    EvaluationScope,
    RiskLevel,
    RiskSeverity,
    RuleOperator,
)


def test_rule_parser_accepts_only_one_whitelisted_comparison() -> None:
    parsed = parse_condition("gross_margin < 0.28")

    assert parsed is not None
    assert parsed.field == "gross_margin"
    assert parsed.operator is RuleOperator.LESS_THAN
    assert parsed.threshold == 0.28
    assert parse_condition("__import__('os').system('whoami')") is None
    assert parse_condition("gross_margin < 0.28 and requested_amount > 0") is None


def test_rule_parser_preserves_field_to_field_condition_without_aliasing() -> None:
    parsed = parse_condition("closing_cash < cash_reserve_minimum")

    assert parsed is not None
    assert parsed.field == "closing_cash"
    assert parsed.threshold == "cash_reserve_minimum"


def test_related_record_uses_exact_comma_delimited_tokens() -> None:
    tokens = parse_related_record("TXN-006, TXN-007")

    assert tokens == ("TXN-006", "TXN-007")
    assert "TXN-00" not in tokens
    assert "TXN-006" not in parse_related_record("TXN-006-OTHER")


def test_overall_level_is_maximum_case_severity_without_numeric_score() -> None:
    assert aggregate_case_severity(()) is RiskLevel.NO_CASE_SIGNAL
    assert aggregate_case_severity(
        (RiskSeverity.MEDIUM, RiskSeverity.HIGH)
    ) is RiskLevel.HIGH


def test_risk_business_code_does_not_execute_source_rule_text() -> None:
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in Path("src/opc_mis/business/agents/risk").glob("*.py")
    )

    assert "eval(" not in source
    assert "import pandas" not in source
    assert "import openpyxl" not in source
    assert "import fastapi" not in source
    assert "opc_mis.infrastructure" not in source


def test_risk_component_requires_workflow_to_select_an_explicit_phase() -> None:
    class LoaderMustNotRun:
        async def load(self, context: ExecutionContext) -> None:
            raise AssertionError(f"Unexpected Risk context load for {context.current_node}")

    result = asyncio.run(
        RiskAgent(context_loader=LoaderMustNotRun()).execute(  # type: ignore[arg-type]
            ExecutionContext(
                dataset_id="DATASET",
                workflow_run_id="RUN",
                requested_scope=(EvaluationScope.RISK,),
                current_node="INITIAL_RISK_PRE_SCAN",
            )
        )
    )

    assert result.status is ComponentStatus.FAILED_SAFE
    assert result.artifacts == ()
    assert result.runtime_events[0].event_type == "RISK_FAILED_SAFE"


def test_risk_narrative_prompt_preserves_approval_and_confirmation_boundaries() -> None:
    prompt = Path("config/prompts/risk_narrative.md").read_text(encoding="utf-8")
    normalized = " ".join(prompt.split())

    for required in (
        "Do not activate, deactivate, or reinterpret a rule.",
        "Only items present in `approval_signals`",
        "They are not automatically approvals for this contract.",
        "They are not approval requests.",
        "Never attribute an `OPC_GLOBAL` signal to the current contract.",
        "Produce no prose outside that schema.",
    ):
        assert required in normalized
