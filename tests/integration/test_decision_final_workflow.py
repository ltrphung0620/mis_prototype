"""Governed Decision Card and post-decision workflow integration tests."""

from __future__ import annotations

import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from opc_mis.api.application import create_app
from opc_mis.domain.decision_models import (
    AIDecisionComposition,
    AIDecisionProposalDraft,
    AIDecisionReasonDraft,
    AIDecisionRecommendedActionDraft,
    DecisionAnalysisSource,
    DecisionConfidence,
    DecisionRecommendation,
    DecisionScenarioPacket,
    NegotiationConditionDraft,
    decision_packet_input_hash,
)
from opc_mis.infrastructure.openai.decision_fallback import (
    DeterministicDecisionAnalysisComposer,
)

TEAM_PACK = Path(
    "data/input/MISTalent2026_OPC_AgenticAI_TeamPack_v3.xlsx"
).resolve()
TEST_HMAC_KEY = "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="


async def _exact_negotiation(
    _self: DeterministicDecisionAnalysisComposer,
    payload: DecisionScenarioPacket,
    **_kwargs: object,
) -> AIDecisionComposition:
    """Stand in for a valid OpenAI proposal while retaining the real guard."""
    assert DecisionRecommendation.NEGOTIATE_CONDITIONS_TO_ACCEPT in (
        payload.allowed_recommendations
    )
    strategy_by_condition: dict[str, str] = {}
    for strategy in payload.negotiation_strategy_candidates:
        strategy_by_condition.setdefault(
            strategy.condition_code, strategy.strategy_id
        )
    reasons = tuple(
        AIDecisionReasonDraft.model_validate(
            item.model_dump(mode="json", exclude={"candidate_id"})
        )
        for item in payload.reason_candidates
    )
    proposal = AIDecisionProposalDraft(
        recommendation=DecisionRecommendation.NEGOTIATE_CONDITIONS_TO_ACCEPT,
        executive_summary=(
            "Founder should negotiate every unresolved evidence-backed condition "
            "before accepting the opportunity."
        ),
        reasons=reasons,
        recommended_actions=tuple(
            AIDecisionRecommendedActionDraft(
                reason_code=item.code,
                action=(
                    "Founder should address this evidence-backed reason before "
                    "deciding."
                ),
                source_reference_ids=item.source_reference_ids,
                evidence_ids=item.evidence_ids,
            )
            for item in reasons
        ),
        conditions=tuple(
            NegotiationConditionDraft.model_validate(
                item.model_dump(mode="json", exclude={"candidate_id"})
            )
            for item in payload.condition_candidates
        ),
        selected_negotiation_strategy_ids=tuple(
            strategy_by_condition.values()
        ),
        selected_option_ids=(),
        confidence=DecisionConfidence.MEDIUM,
        human_attention_points=(),
        calculations_performed_by_model=False,
    )
    return AIDecisionComposition(
        proposal=proposal,
        source=DecisionAnalysisSource.OPENAI,
        model="integration-openai-double",
        prompt_version="decision-integration-v1",
        input_hash=decision_packet_input_hash(payload),
    )


@pytest.fixture
def decision_client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("OPENAI_ENABLED", "false")
    monkeypatch.setenv("OPC_MIS_MASKING_HMAC_KEY_BASE64", TEST_HMAC_KEY)
    compose_calls: list[str] = []

    async def counting_compose(
        composer: DeterministicDecisionAnalysisComposer,
        payload: DecisionScenarioPacket,
        **kwargs: object,
    ) -> AIDecisionComposition:
        compose_calls.append(payload.packet_id)
        return await _exact_negotiation(composer, payload, **kwargs)

    monkeypatch.setattr(
        DeterministicDecisionAnalysisComposer,
        "compose",
        counting_compose,
    )
    app = create_app(
        workbook_path=TEAM_PACK,
        dataset_id="FINAL_DECISION_WORKFLOW_TEST",
        database_path=":memory:",
    )
    app.state.decision_compose_calls = compose_calls
    with TestClient(app) as client:
        yield client


def _wait_for_pause_or_completion(
    client: TestClient,
    workflow_run_id: str,
    *,
    timeout_seconds: float = 10,
) -> dict[str, object]:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        response = client.get(f"/api/workflows/{workflow_run_id}")
        assert response.status_code == 200
        payload = response.json()
        if payload["status"] not in {"PENDING", "RUNNING"}:
            return payload
        time.sleep(0.02)
    raise AssertionError("Decision workflow did not reach a durable boundary.")


def test_exact_decision_card_requires_founder_then_routes_to_negotiation(
    decision_client: TestClient,
) -> None:
    created = decision_client.post(
        "/api/cases/run",
        json={
            "contract_id": "CON-005",
            "evaluation_scope": ["FINANCE", "OPERATIONS", "RISK"],
            "as_of_date": "2026-07-19",
        },
    )
    assert created.status_code == 202
    workflow_run_id = created.json()["workflow_run_id"]
    waiting = _wait_for_pause_or_completion(decision_client, workflow_run_id)

    assert waiting["status"] == "WAITING_FOR_APPROVAL"
    assert waiting["current_stage"] == "WAITING_FOR_APPROVAL"
    assert waiting["resume_stage"] == "FINAL_DECISION_APPROVAL"
    assert waiting["blocked_action"] == "CONFIRM_FINAL_CONTRACT_DECISION"
    assert waiting["decision_recommendation"] == (
        "NEGOTIATE_CONDITIONS_TO_ACCEPT"
    )
    assert waiting["decision_condition_ids"]
    case_id = waiting["evaluation_case_id"]

    artifacts = decision_client.get(f"/api/cases/{case_id}/artifacts").json()
    card = next(
        item for item in artifacts if item["artifact_type"] == "DECISION_CARD"
    )
    requests = decision_client.get(
        f"/api/cases/{case_id}/approval-requests"
    ).json()
    assert len(requests) == 1
    request = requests[0]
    assert request["command"]["action_type"] == (
        "CONFIRM_FINAL_CONTRACT_DECISION"
    )
    assert request["subject_artifact_id"] == card["artifact_id"]
    assert request["subject_artifact_version"] == card["version"]
    assert request["subject_input_hash"] == card["input_hash"]
    assert request["command"]["payload"] == {
        "final_decision_confirmation_requested": True,
        "decision_card_id": card["payload"]["decision_card_id"],
        "recommendation": "NEGOTIATE_CONDITIONS_TO_ACCEPT",
        "condition_ids": waiting["decision_condition_ids"],
        "selected_negotiation_strategy_ids": [],
        "selected_option_ids": [],
        "document_release_package": None,
    }

    checkpoint_payload = decision_client.get(
        f"/api/cases/{case_id}/approval-checkpoints"
    ).json()
    triggered = {
        item["checkpoint_id"]: item for item in checkpoint_payload["checkpoints"]
    }
    final_checkpoints = [triggered[item] for item in request["checkpoint_ids"]]
    assert len(final_checkpoints) == 1
    assert final_checkpoints[0]["source_rule_id"] == (
        "OPC_FINAL_DECISION_GOVERNANCE"
    )
    assert final_checkpoints[0]["approver_role"] == "FOUNDER"

    compose_call_count = len(decision_client.app.state.decision_compose_calls)
    approved = decision_client.post(
        f"/api/approval-requests/{request['request_id']}/decision",
        json={
            "decision": "APPROVE",
            "decided_by": "FOUNDER",
            "reason": "HUMAN_REVIEW_COMPLETED",
        },
    )
    assert approved.status_code == 200
    assert approved.json()["action_authorized"] is True

    completed = _wait_for_pause_or_completion(decision_client, workflow_run_id)
    assert len(decision_client.app.state.decision_compose_calls) == compose_call_count
    assert completed["status"] == "COMPLETED"
    assert completed["current_stage"] == "NEGOTIATION_IN_PROGRESS"
    assert completed["post_decision_outcome"] == "NEGOTIATION_AUTHORIZED"
    assert completed["post_decision_update_id"]
    assert completed["external_document_submission_proposal_id"] is None
    assert completed["external_submission_authorized"] is False
    assert completed["ready_for_external_submission"] is False
    assert completed["external_submission_performed"] is False

    artifacts = decision_client.get(f"/api/cases/{case_id}/artifacts").json()
    assert sum(
        item["artifact_type"] == "POST_DECISION_UPDATE" for item in artifacts
    ) == 1
    assert not any(
        item["artifact_type"] == "EXTERNAL_DOCUMENT_SUBMISSION_PROPOSAL"
        for item in artifacts
    )


def test_founder_rejection_closes_checkpoint_without_post_decision_update(
    decision_client: TestClient,
) -> None:
    created = decision_client.post(
        "/api/cases/run",
        json={
            "contract_id": "CON-005",
            "evaluation_scope": ["FINANCE", "OPERATIONS", "RISK"],
            "as_of_date": "2026-07-20",
        },
    )
    assert created.status_code == 202
    workflow_run_id = created.json()["workflow_run_id"]
    waiting = _wait_for_pause_or_completion(decision_client, workflow_run_id)
    assert waiting["blocked_action"] == "CONFIRM_FINAL_CONTRACT_DECISION"
    request_id = waiting["pending_approval_ids"][0]

    rejected = decision_client.post(
        f"/api/approval-requests/{request_id}/decision",
        json={
            "decision": "REJECT",
            "decided_by": "FOUNDER",
            "reason": "HUMAN_REVIEW_COMPLETED",
        },
    )
    assert rejected.status_code == 200
    assert rejected.json()["action_authorized"] is False

    completed = _wait_for_pause_or_completion(decision_client, workflow_run_id)
    assert completed["status"] == "COMPLETED"
    assert completed["current_stage"] == "FINAL_DECISION_REJECTED"
    assert completed["post_decision_update_id"] is None
    assert completed["external_submission_performed"] is False
    artifacts = decision_client.get(
        f"/api/cases/{waiting['evaluation_case_id']}/artifacts"
    ).json()
    assert not any(
        item["artifact_type"] == "POST_DECISION_UPDATE" for item in artifacts
    )


def test_con004_card_carries_one_precomputed_margin_negotiation_strategy(
    decision_client: TestClient,
) -> None:
    created = decision_client.post(
        "/api/cases/run",
        json={
            "contract_id": "CON-004",
            "evaluation_scope": ["FINANCE", "OPERATIONS", "RISK"],
            "as_of_date": "2026-07-19",
        },
    )
    assert created.status_code == 202
    workflow_run_id = created.json()["workflow_run_id"]

    banking_wait = _wait_for_pause_or_completion(
        decision_client, workflow_run_id
    )
    assert banking_wait["blocked_action"] == "SUBMIT_BANKING_PRECHECK"
    banking_approval = decision_client.post(
        "/api/approval-requests/"
        f"{banking_wait['pending_approval_ids'][0]}/decision",
        json={
            "decision": "APPROVE",
            "decided_by": "FOUNDER",
            "reason": "HUMAN_REVIEW_COMPLETED",
        },
    )
    assert banking_approval.status_code == 200

    document_wait = _wait_for_pause_or_completion(
        decision_client, workflow_run_id
    )
    assert document_wait["current_stage"] == "DOCUMENT_PREPARATION"
    supplied = decision_client.post(
        f"/api/cases/{document_wait['evaluation_case_id']}"
        "/documents/evidence-supplements",
        json={
            "workflow_run_id": workflow_run_id,
            "missing_request_id": document_wait["pending_missing_data_ids"][0],
            "document_reference_id": (
                "DOCREF-00000000-0000-4000-8000-000000000077"
            ),
            "content_sha256": "7" * 64,
            "document_type": "PERFORMANCE_BOND_REQUEST_FORM",
            "evidence_note": "REQUESTED_DOCUMENT_REFERENCE_SUPPLIED",
        },
    )
    assert supplied.status_code == 202

    deadline = time.monotonic() + 10
    cashflow_wait: dict[str, object] | None = None
    while time.monotonic() < deadline:
        candidate = decision_client.get(
            f"/api/workflows/{workflow_run_id}"
        ).json()
        if (
            candidate["status"] == "WAITING_FOR_INPUT"
            and candidate["pending_missing_data_ids"]
            and document_wait["pending_missing_data_ids"][0]
            not in candidate["pending_missing_data_ids"]
        ):
            cashflow_wait = candidate
            break
        time.sleep(0.02)
    assert cashflow_wait is not None
    assert cashflow_wait["current_stage"] == "DOCUMENT_PREPARATION"
    cashflow_supplied = decision_client.post(
        f"/api/cases/{cashflow_wait['evaluation_case_id']}"
        "/documents/evidence-supplements",
        json={
            "workflow_run_id": workflow_run_id,
            "missing_request_id": cashflow_wait["pending_missing_data_ids"][0],
            "document_reference_id": (
                "DOCREF-00000000-0000-4000-8000-000000000078"
            ),
            "content_sha256": "8" * 64,
            "document_type": "CASHFLOW_BUFFER_EVIDENCE",
            "evidence_note": "REQUESTED_DOCUMENT_REFERENCE_SUPPLIED",
        },
    )
    assert cashflow_supplied.status_code == 202

    decision_wait = _wait_for_pause_or_completion(
        decision_client, workflow_run_id
    )
    assert decision_wait["blocked_action"] == (
        "CONFIRM_FINAL_CONTRACT_DECISION"
    )
    assert decision_wait["decision_recommendation"] == (
        "NEGOTIATE_CONDITIONS_TO_ACCEPT"
    )
    assert len(decision_wait["decision_selected_negotiation_strategy_ids"]) == 1

    case_id = decision_wait["evaluation_case_id"]
    artifacts = decision_client.get(f"/api/cases/{case_id}/artifacts").json()
    card = next(
        item for item in artifacts if item["artifact_type"] == "DECISION_CARD"
    )
    assert "24%" in card["payload"]["executive_summary"]
    assert "28%" in card["payload"]["executive_summary"]
    assert "172,222,223 VND" in card["payload"]["executive_summary"]
    assert "Điều kiện vẫn OPEN" in card["payload"]["executive_summary"]
    strategy = card["payload"]["selected_negotiation_strategies"][0]
    assert strategy["strategy_type"] == "INCREASE_CUSTOMER_PRICE"
    assert strategy["baseline_revenue"] == 3_100_000_000
    assert strategy["baseline_cost"] == 2_356_000_000
    assert strategy["target_margin"] == 0.28
    assert strategy["required_adjustment_value"] == 172_222_223
    assert strategy["resulting_revenue"] == 3_272_222_223
    assert strategy["resulting_cost"] == 2_356_000_000
    assert "172,222,223 VND" in strategy["founder_instruction"]
    assert "3,272,222,223 VND" in strategy["founder_instruction"]
    assert "EXPLICITLY_LINKED_ORDER_SCOPE_ONLY" in strategy["assumptions"]

    requests = decision_client.get(
        f"/api/cases/{case_id}/approval-requests"
    ).json()
    final_request = next(
        item
        for item in requests
        if item["command"]["action_type"]
        == "CONFIRM_FINAL_CONTRACT_DECISION"
    )
    assert final_request["command"]["payload"][
        "selected_negotiation_strategy_ids"
    ] == decision_wait["decision_selected_negotiation_strategy_ids"]

    approved = decision_client.post(
        f"/api/approval-requests/{final_request['request_id']}/decision",
        json={
            "decision": "APPROVE",
            "decided_by": "FOUNDER",
            "reason": "HUMAN_REVIEW_COMPLETED",
        },
    )
    assert approved.status_code == 200
    negotiation = _wait_for_pause_or_completion(
        decision_client, workflow_run_id
    )
    assert negotiation["current_stage"] == "NEGOTIATION_IN_PROGRESS"
    artifacts = decision_client.get(f"/api/cases/{case_id}/artifacts").json()
    update = next(
        item
        for item in artifacts
        if item["artifact_type"] == "POST_DECISION_UPDATE"
    )
    assert update["payload"]["approved_negotiation_strategy_ids"] == (
        decision_wait["decision_selected_negotiation_strategy_ids"]
    )

    second_created = decision_client.post(
        "/api/cases/run",
        json={
            "contract_id": "CON-004",
            "evaluation_scope": ["FINANCE", "OPERATIONS", "RISK"],
            "as_of_date": "2026-07-20",
        },
    )
    assert second_created.status_code == 202
    second_run_id = second_created.json()["workflow_run_id"]
    second_precheck_wait = _wait_for_pause_or_completion(
        decision_client, second_run_id
    )
    assert second_precheck_wait["blocked_action"] == "SUBMIT_BANKING_PRECHECK"

    second_approval = decision_client.post(
        "/api/approval-requests/"
        f"{second_precheck_wait['pending_approval_ids'][0]}/decision",
        json={
            "decision": "APPROVE",
            "decided_by": "FOUNDER",
            "reason": "HUMAN_REVIEW_COMPLETED",
        },
    )
    assert second_approval.status_code == 200
    assert second_approval.json()["action_authorized"] is True
    assert second_approval.json()["approval_request"]["status"] == "APPROVED"
