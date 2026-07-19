"""Master Workflow integration for governed simulated Banking precheck execution."""

import json
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from opc_mis.api.application import create_app
from opc_mis.infrastructure.banking.simulated_precheck_adapter import (
    SimulatedBankingPrecheckAdapter,
)

TEAM_PACK = Path(
    "data/input/MISTalent2026_OPC_AgenticAI_TeamPack_v3.xlsx"
).resolve()
TEST_HMAC_KEY = "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="


@pytest.fixture(scope="module")
def client() -> Iterator[TestClient]:
    patcher = pytest.MonkeyPatch()
    patcher.setenv("OPENAI_ENABLED", "false")
    patcher.setenv("OPC_MIS_MASKING_HMAC_KEY_BASE64", TEST_HMAC_KEY)
    try:
        app = create_app(
            workbook_path=TEAM_PACK,
            dataset_id="BANKING_PRECHECK_SUBMISSION_WORKFLOW_TEST",
            database_path=":memory:",
        )
        with TestClient(app) as test_client:
            yield test_client
    finally:
        patcher.undo()


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
    raise AssertionError("Workflow did not pause or complete in time.")


def _start(
    client: TestClient,
    *,
    as_of_date: str = "2026-07-16",
) -> dict[str, object]:
    response = client.post(
        "/api/cases/run",
        json={
            "contract_id": "CON-004",
            "evaluation_scope": ["FINANCE", "OPERATIONS", "RISK"],
            "as_of_date": as_of_date,
        },
    )
    assert response.status_code == 202
    return response.json()


def test_proposal_pauses_for_human_then_persists_non_binding_results(
    client: TestClient,
) -> None:
    created = _start(client)
    workflow_run_id = str(created["workflow_run_id"])
    approval_wait = _wait_for_pause_or_completion(client, workflow_run_id)
    assert approval_wait["status"] == "WAITING_FOR_APPROVAL"
    assert approval_wait["current_stage"] == "WAITING_FOR_APPROVAL"

    evaluation_case_id = str(approval_wait["evaluation_case_id"])
    assert approval_wait["pending_missing_data_ids"] == []
    override_attempt = client.post(
        f"/api/cases/{evaluation_case_id}/banking/input-supplements",
        json={
            "workflow_run_id": workflow_run_id,
            "missing_request_id": "MDR-NOT-OPEN",
            "requested_amount": 350_000_000,
            "requested_amount_currency": "VND",
            "evidence_note": "Attempted amount override must be rejected.",
        },
    )
    assert override_attempt.status_code == 409
    assert (
        approval_wait["resume_stage"]
        == "BANKING_PRECHECK_SUBMISSION_PROPOSAL"
    )
    assert approval_wait["blocked_action"] == "SUBMIT_BANKING_PRECHECK"
    assert approval_wait["approval_checkpoint_count"] == 4
    assert len(approval_wait["pending_approval_ids"]) == 1
    assert approval_wait["banking_precheck_submission_proposal_id"]
    assert approval_wait["banking_precheck_submission_candidate_ids"] == (
        approval_wait["precheck_ready_option_ids"]
    )

    artifacts = client.get(
        f"/api/cases/{evaluation_case_id}/artifacts"
    ).json()
    proposals = [
        item
        for item in artifacts
        if item["artifact_type"] == "BANKING_PRECHECK_SUBMISSION_PROPOSAL"
    ]
    assert len(proposals) == 1
    proposal_artifact = proposals[0]
    proposal = proposal_artifact["payload"]
    assert proposal["proposal_id"] == approval_wait[
        "banking_precheck_submission_proposal_id"
    ]
    assert proposal["proposed_action"] == "SUBMIT_BANKING_PRECHECK"
    assert "approval_required" not in proposal
    assert proposal["precheck_executed"] is False
    assert proposal["submission_executed"] is False
    assert proposal["candidate_option_ids"]
    assert [item["option_id"] for item in proposal["candidates"]] == proposal[
        "candidate_option_ids"
    ]

    requests = client.get(
        f"/api/cases/{evaluation_case_id}/approval-requests"
    ).json()
    assert len(requests) == 1
    approval_request = requests[0]
    assert approval_request["status"] == "PENDING"
    assert approval_request["subject_artifact_id"] == proposal_artifact[
        "artifact_id"
    ]
    assert approval_request["command"]["action_type"] == (
        "SUBMIT_BANKING_PRECHECK"
    )
    assert approval_request["command"]["payload"] == {
        "precheck_submission_requested": True,
        "api_ids": ["API-002"],
        "requested_amount": 420_000_000,
        "requested_amount_currency": "VND",
    }
    checkpoint_payload = client.get(
        f"/api/cases/{evaluation_case_id}/approval-checkpoints"
    ).json()
    checkpoints = checkpoint_payload["checkpoints"]
    submission_checkpoints = [
        item
        for item in checkpoints
        if item["protected_action"] == "SUBMIT_BANKING_PRECHECK"
    ]
    assert {item["source_rule_id"] for item in submission_checkpoints} == {
        "API-002",
        "RR-005",
    }
    assert approval_request["checkpoint_ids"] == [
        item["checkpoint_id"] for item in submission_checkpoints
    ]
    assert approval_request["policy_artifact_id"]
    assert approval_request["policy_artifact_version"] == 2
    assert approval_request["policy_input_hash"]
    assert len(approval_request["policy_coverage_ids"]) == 1
    coverages = checkpoint_payload["policy_coverages"]
    assert [item["api_ids"] for item in coverages] == [["API-002"]]
    assert coverages[0]["requires_human_approval"] is True
    assert not any(
        item["artifact_type"] == "BANKING_INPUT_SUPPLEMENT"
        for item in artifacts
    )

    duplicate_wait = _start(client)
    assert duplicate_wait["workflow_run_id"] == workflow_run_id
    assert duplicate_wait["status"] == "WAITING_FOR_APPROVAL"
    assert len(
        client.get(
            f"/api/cases/{evaluation_case_id}/approval-requests"
        ).json()
    ) == 1

    approved = client.post(
        f"/api/approval-requests/{approval_request['request_id']}/decision",
        json={
            "decision": "APPROVE",
            "decided_by": "FOUNDER",
            "reason": "HUMAN_REVIEW_COMPLETED",
        },
    )
    assert approved.status_code == 200
    assert approved.json()["action_authorized"] is True

    document_wait = _wait_for_pause_or_completion(client, workflow_run_id)
    assert document_wait["status"] == "WAITING_FOR_INPUT"
    assert document_wait["current_stage"] == "DOCUMENT_PREPARATION"
    assert document_wait["pending_approval_ids"] == []
    assert len(document_wait["pending_missing_data_ids"]) == 1
    assert document_wait["banking_precheck_result_set_id"]
    assert document_wait["banking_precheck_normalized_result_ids"]
    assert document_wait["banking_precheck_outcomes"] == [
        "CONDITIONAL_PRECHECK"
    ]
    assert document_wait["banking_precheck_eligibility_statuses"] == [
        "ELIGIBLE"
    ]
    assert document_wait["banking_precheck_guarantee_decisions"] == [
        "CONDITIONAL"
    ]
    assert document_wait["banking_precheck_supported_amounts"] == [
        420_000_000
    ]
    assert document_wait["banking_precheck_currencies"] == ["VND"]
    assert document_wait["banking_precheck_required_document_codes"] == [[
        "SIGNED_CONTRACT",
        "COMPANY_PROFILE",
        "PERFORMANCE_BOND_REQUEST_FORM",
        "CASHFLOW_BUFFER_EVIDENCE",
    ]]
    assert document_wait["banking_precheck_approval_condition_codes"] == [[
        "CONTRACT_SIGNED",
        "CASHFLOW_BUFFER_CONFIRMED",
    ]]
    assert document_wait["banking_precheck_execution_mode"] == "SIMULATED"
    assert (
        document_wait["banking_precheck_result_authority"]
        == "SIMULATED_NON_BINDING"
    )
    assert document_wait["banking_precheck_external_bank_submission"] is False
    assert document_wait["banking_precheck_bank_approval_obtained"] is False
    assert document_wait["decision_post_precheck_review_id"]
    assert document_wait["decision_post_precheck_outcome"] == (
        "CONDITIONAL_OPTIONS_AVAILABLE"
    )
    assert document_wait["decision_post_precheck_candidate_product_ids"] == [
        "BANKPROD-002"
    ]
    assert document_wait["decision_post_precheck_conditional_option_ids"] == (
        document_wait["decision_post_precheck_candidate_option_ids"]
    )
    assert len(document_wait["document_preparation_request_ids"]) == 1
    assert len(document_wait["document_checklist_ids"]) == 1
    assert len(document_wait["document_package_draft_ids"]) == 1
    assert document_wait["document_package_readinesses"] == [
        "WAITING_FOR_INPUT"
    ]
    assert document_wait["document_pending_codes"] == ["SIGNED_CONTRACT"]
    assert document_wait["document_release_package_ids"] == []
    proposal_node = next(
        item
        for item in document_wait["nodes"]
        if item["node"] == "BANKING_PRECHECK_SUBMISSION_PROPOSAL"
    )
    assert proposal_node["status"] == "COMPLETED"
    assert proposal_node["attempt"] == 1
    execution_node = next(
        item
        for item in document_wait["nodes"]
        if item["node"] == "BANKING_PRECHECK_EXECUTION"
    )
    assert execution_node["status"] == "COMPLETED_WITH_WARNINGS"
    assert execution_node["attempt"] == 1
    review_node = next(
        item
        for item in document_wait["nodes"]
        if item["node"] == "DECISION_POST_PRECHECK_REVIEW"
    )
    assert review_node["status"] == "COMPLETED"
    assert review_node["attempt"] == 1

    completed_artifacts = client.get(
        f"/api/cases/{evaluation_case_id}/artifacts"
    ).json()
    result_artifacts = [
        item
        for item in completed_artifacts
        if item["artifact_type"] == "BANKING_PRECHECK_RESULT_SET"
    ]
    assert len(result_artifacts) == 1
    result_set = result_artifacts[0]["payload"]
    assert result_set["result_set_id"] == document_wait[
        "banking_precheck_result_set_id"
    ]
    assert result_set["candidate_option_ids"] == proposal["candidate_option_ids"]
    assert result_set["adapter_invoked"] is True
    assert result_set["external_bank_submission"] is False
    assert result_set["bank_approval_obtained"] is False
    assert result_set["selection_performed"] is False
    assert result_set["ranking_performed"] is False
    assert result_set["documents_prepared"] is False
    result = result_set["results"][0]
    assert result["outcome"] == "CONDITIONAL_PRECHECK"
    assert result["supported_amount"] == 420_000_000
    assert result["currency"] == "VND"
    assert result["eligibility_status"] == "ELIGIBLE"
    assert result["guarantee_decision"] == "CONDITIONAL"
    assert result["required_documents"] == [
        "SIGNED_CONTRACT",
        "COMPANY_PROFILE",
        "PERFORMANCE_BOND_REQUEST_FORM",
        "CASHFLOW_BUFFER_EVIDENCE",
    ]
    assert result["approval_conditions"] == [
        "CONTRACT_SIGNED",
        "CASHFLOW_BUFFER_CONFIRMED",
    ]
    assert result_set["results"][0]["non_binding"] is True
    review_artifacts = [
        item
        for item in completed_artifacts
        if item["artifact_type"] == "DECISION_POST_PRECHECK_REVIEW"
    ]
    assert len(review_artifacts) == 1
    review = review_artifacts[0]["payload"]
    assert review["review_id"] == document_wait[
        "decision_post_precheck_review_id"
    ]
    assert review["outcome"] == "CONDITIONAL_OPTIONS_AVAILABLE"
    assert review["candidate_option_ids"] == result_set[
        "candidate_option_ids"
    ]
    assert review["candidate_bank_product_ids"] == ["BANKPROD-002"]
    assert review["option_reviews"][0]["bank_product_id"] == (
        result_set["results"][0]["bank_product_id"]
    )
    assert review["selection_performed"] is False
    assert review["ranking_performed"] is False
    assert review["documents_prepared"] is False
    inspected = client.post(
        f"/api/cases/{evaluation_case_id}/decision/post-precheck-review"
    )
    assert inspected.status_code == 200
    inspected_payload = inspected.json()
    assert inspected_payload["review"] == review
    assert inspected_payload["artifact_refs"][0]["artifact_id"] == (
        review_artifacts[0]["artifact_id"]
    )
    serialized_result = json.dumps(result_set, ensure_ascii=False, sort_keys=True)
    assert "company_profile" not in serialized_result
    assert "request_body" not in serialized_result
    assert "request_payload" not in serialized_result

    retry = _start(client)
    assert retry["status"] == "WAITING_FOR_INPUT"
    after = client.get(f"/api/workflows/{workflow_run_id}").json()
    assert after["current_stage"] == "DOCUMENT_PREPARATION"
    after_proposal_node = next(
        item
        for item in after["nodes"]
        if item["node"] == "BANKING_PRECHECK_SUBMISSION_PROPOSAL"
    )
    assert after_proposal_node["attempt"] == 1
    after_execution_node = next(
        item
        for item in after["nodes"]
        if item["node"] == "BANKING_PRECHECK_EXECUTION"
    )
    assert after_execution_node["attempt"] == 1
    after_review_node = next(
        item
        for item in after["nodes"]
        if item["node"] == "DECISION_POST_PRECHECK_REVIEW"
    )
    assert after_review_node["attempt"] == 1
    after_document_node = next(
        item
        for item in after["nodes"]
        if item["node"] == "DOCUMENT_PREPARATION"
    )
    assert after_document_node["attempt"] == 1
    after_artifacts = client.get(
        f"/api/cases/{evaluation_case_id}/artifacts"
    ).json()
    assert sum(
        item["artifact_type"] == "BANKING_PRECHECK_SUBMISSION_PROPOSAL"
        for item in after_artifacts
    ) == 1
    assert sum(
        item["artifact_type"] == "BANKING_PRECHECK_RESULT_SET"
        for item in after_artifacts
    ) == 1
    assert sum(
        item["artifact_type"] == "DECISION_POST_PRECHECK_REVIEW"
        for item in after_artifacts
    ) == 1
    assert sum(
        item["artifact_type"] == "DOCUMENT_PREPARATION_REQUEST"
        for item in after_artifacts
    ) == 1
    assert sum(
        item["artifact_type"] == "DOCUMENT_CHECKLIST"
        for item in after_artifacts
    ) == 1
    assert sum(
        item["artifact_type"] == "DOCUMENT_PACKAGE_DRAFT"
        for item in after_artifacts
    ) == 1
    assert not any(
        item["artifact_type"] == "DOCUMENT_RELEASE_PACKAGE"
        for item in after_artifacts
    )
    events = client.get(f"/api/workflows/{workflow_run_id}/events").json()
    assert [item["event_type"] for item in events].count(
        "APPROVAL_REQUESTED"
    ) == 1
    assert [item["event_type"] for item in events].count(
        "PROTECTED_ACTION_ALLOWED"
    ) == 1
    assert [item["event_type"] for item in events].count(
        "BANKING_PRECHECK_SUBMISSION_AUTHORIZED"
    ) == 1
    assert [item["event_type"] for item in events].count(
        "BANKING_PRECHECK_RESULTS_READY"
    ) == 1


def test_api_policy_approval_can_be_rejected_without_blocking_the_case() -> None:
    app = create_app(
        workbook_path=TEAM_PACK,
        dataset_id="BANKING_PRECHECK_SUBMISSION_REJECTION_TEST",
        database_path=":memory:",
    )
    with TestClient(app) as client:
        created = _start(client, as_of_date="2026-07-17")
        workflow_run_id = str(created["workflow_run_id"])
        approval_wait = _wait_for_pause_or_completion(client, workflow_run_id)
        assert approval_wait["status"] == "WAITING_FOR_APPROVAL"
        evaluation_case_id = str(approval_wait["evaluation_case_id"])

        requests = client.get(
            f"/api/cases/{evaluation_case_id}/approval-requests"
        ).json()
        assert len(requests) == 1
        checkpoint_payload = client.get(
            f"/api/cases/{evaluation_case_id}/approval-checkpoints"
        ).json()
        triggered = set(requests[0]["checkpoint_ids"])
        api_checkpoint = next(
            item
            for item in checkpoint_payload["checkpoints"]
            if item["protected_action"] == "SUBMIT_BANKING_PRECHECK"
            and item["source_rule_id"] == "API-002"
        )
        amount_checkpoint = next(
            item
            for item in checkpoint_payload["checkpoints"]
            if item["protected_action"] == "SUBMIT_BANKING_PRECHECK"
            and item["source_rule_id"] == "RR-005"
        )
        assert triggered == {
            api_checkpoint["checkpoint_id"],
            amount_checkpoint["checkpoint_id"],
        }
        rejected = client.post(
            f"/api/approval-requests/{requests[0]['request_id']}/decision",
            json={
                "decision": "REJECT",
                "decided_by": "FOUNDER",
                "reason": "HUMAN_REVIEW_COMPLETED",
            },
        )
        assert rejected.status_code == 200
        assert rejected.json()["gate_status"] == "REJECTED"
        continued = _wait_for_pause_or_completion(client, workflow_run_id)
        assert continued["status"] == "COMPLETED"
        assert continued["current_stage"] == "DECISION_CARD_READY"
        assert continued["decision_recommendation"] == "NOT_EVALUABLE"
        assert continued["pending_approval_ids"] == []
        assert continued["internal_decision_package_ready"] is True
        assert continued["internal_decision_assembly_path"] == (
            "BANKING_PRECHECK_DECLINED"
        )
        assert continued["internal_decision_governance_reference_ids"] == [
            requests[0]["request_id"]
        ]
        assert continued["blocked_action"] is None
        assert continued["banking_precheck_result_set_id"] is None

        artifacts = client.get(
            f"/api/cases/{evaluation_case_id}/artifacts"
        ).json()
        proposal = next(
            item["payload"]
            for item in artifacts
            if item["artifact_type"]
            == "BANKING_PRECHECK_SUBMISSION_PROPOSAL"
        )
        assert proposal["requested_amount"] == 420_000_000
        assert "approval_required" not in proposal
        assert proposal["precheck_executed"] is False
        assert proposal["submission_executed"] is False


def test_explicit_precheck_evidence_gap_persists_result_then_pauses(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy_path = tmp_path / "precheck-missing-evidence.json"
    policy_path.write_text(
        json.dumps(
            {
                "configuration_id": "POST_PRECHECK_MISSING_EVIDENCE_TEST",
                "configuration_version": "1",
                "scenarios": [
                    {
                        "scenario_id": "API-002-MISSING-EVIDENCE",
                        "api_id": "API-002",
                        "api_provider": "VietinBank",
                        "outcome": "MISSING_EVIDENCE",
                        "message": (
                            "Simulated non-binding result requires one explicit "
                            "follow-up field."
                        ),
                        "reason_codes": ["SIMULATED_MISSING_EVIDENCE"],
                        "required_follow_up_fields": [
                            "supporting_document_reference"
                        ],
                        "non_binding": True,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("OPENAI_ENABLED", "false")
    monkeypatch.setenv(
        "BANKING_PRECHECK_SIMULATION_POLICY_PATH", str(policy_path)
    )
    app = create_app(
        workbook_path=TEAM_PACK,
        dataset_id="BANKING_POST_PRECHECK_MISSING_EVIDENCE_TEST",
        database_path=":memory:",
    )
    with TestClient(app) as client:
        created = _start(client, as_of_date="2026-07-19")
        workflow_run_id = str(created["workflow_run_id"])
        approval_wait = _wait_for_pause_or_completion(client, workflow_run_id)
        evaluation_case_id = str(approval_wait["evaluation_case_id"])
        approval_id = approval_wait["pending_approval_ids"][0]
        approved = client.post(
            f"/api/approval-requests/{approval_id}/decision",
            json={
                "decision": "APPROVE",
                "decided_by": "FOUNDER",
                "reason": "HUMAN_REVIEW_COMPLETED",
            },
        )
        assert approved.status_code == 200

        paused = _wait_for_pause_or_completion(client, workflow_run_id)

        assert paused["status"] == "WAITING_FOR_INPUT"
        assert paused["current_stage"] == "DECISION_POST_PRECHECK_REVIEW"
        assert paused["resume_stage"] == "DECISION_POST_PRECHECK_REVIEW"
        assert paused["banking_precheck_outcomes"] == ["MISSING_EVIDENCE"]
        assert paused["decision_post_precheck_outcome"] == (
            "FOLLOW_UP_EVIDENCE_REQUIRED"
        )
        assert len(paused["pending_missing_data_ids"]) == 1
        assert paused["pending_approval_ids"] == []
        artifacts = client.get(
            f"/api/cases/{evaluation_case_id}/artifacts"
        ).json()
        assert sum(
            item["artifact_type"] == "BANKING_PRECHECK_RESULT_SET"
            for item in artifacts
        ) == 1
        reviews = [
            item
            for item in artifacts
            if item["artifact_type"] == "DECISION_POST_PRECHECK_REVIEW"
        ]
        assert len(reviews) == 1
        review = reviews[0]["payload"]
        assert review["required_input_fields"] == [
            "supporting_document_reference"
        ]
        assert review["missing_data_requests"][0]["request_id"] == (
            paused["pending_missing_data_ids"][0]
        )
        assert review["selection_performed"] is False
        assert review["ranking_performed"] is False
        duplicate = _start(client, as_of_date="2026-07-19")
        assert duplicate["workflow_run_id"] == workflow_run_id
        assert duplicate["status"] == "WAITING_FOR_INPUT"
        after = client.get(f"/api/workflows/{workflow_run_id}").json()
        execution_node = next(
            item
            for item in after["nodes"]
            if item["node"] == "BANKING_PRECHECK_EXECUTION"
        )
        review_node = next(
            item
            for item in after["nodes"]
            if item["node"] == "DECISION_POST_PRECHECK_REVIEW"
        )
        assert execution_node["attempt"] == 1
        assert review_node["attempt"] == 1

        missing_request_id = paused["pending_missing_data_ids"][0]
        evidence_payload = {
            "workflow_run_id": workflow_run_id,
            "missing_request_id": missing_request_id,
            "evidence_reference_id": "DOC-REF-POST-PRECHECK-001",
            "evidence_note": "Authorized staff linked the requested support document.",
        }
        supplied = client.post(
            f"/api/cases/{evaluation_case_id}/banking/"
            "precheck-evidence-supplements",
            json=evidence_payload,
        )
        assert supplied.status_code == 202
        supplied_body = supplied.json()
        supplement = supplied_body["supplement"]
        assert supplement["missing_request_id"] == missing_request_id
        assert supplement["provided_by"] == "AUTHORIZED_STAFF"
        assert supplement["input_handoff_resolved"] is True
        assert supplement["fresh_governed_precheck_required"] is True
        assert supplement["source_precheck_result_unchanged"] is True
        assert supplement["bank_approval_obtained"] is False
        assert supplement["protected_action_authorized"] is False
        assert supplied_body["workflow"]["status"] == "WAITING_FOR_DEPENDENCIES"

        handoff = client.get(f"/api/workflows/{workflow_run_id}").json()
        assert handoff["status"] == "WAITING_FOR_DEPENDENCIES"
        assert handoff["current_stage"] == "BANKING_PRECHECK_RETRY_REQUIRED"
        assert handoff["pending_missing_data_ids"] == []
        artifacts_after = client.get(
            f"/api/cases/{evaluation_case_id}/artifacts"
        ).json()
        evidence_supplements = [
            item
            for item in artifacts_after
            if item["artifact_type"]
            == "BANKING_PRECHECK_EVIDENCE_SUPPLEMENT"
        ]
        assert len(evidence_supplements) == 1
        assert sum(
            item["artifact_type"] == "BANKING_PRECHECK_RESULT_SET"
            for item in artifacts_after
        ) == 1

        retried = client.post(
            f"/api/cases/{evaluation_case_id}/banking/"
            "precheck-evidence-supplements",
            json=evidence_payload,
        )
        assert retried.status_code == 202
        assert retried.json()["supplement"]["supplement_id"] == supplement[
            "supplement_id"
        ]
        assert len(
            [
                item
                for item in client.get(
                    f"/api/cases/{evaluation_case_id}/artifacts"
                ).json()
                if item["artifact_type"]
                == "BANKING_PRECHECK_EVIDENCE_SUPPLEMENT"
            ]
        ) == 1


def test_changed_opc_profile_fails_before_adapter_invocation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter_calls: list[str] = []

    async def spy_submit(
        self: SimulatedBankingPrecheckAdapter,
        request: object,
        authorization: object,
    ) -> object:
        del self, authorization
        adapter_calls.append(str(getattr(request, "request_id", "UNKNOWN")))
        raise AssertionError("Adapter must not run for stale approved profile evidence.")

    monkeypatch.setattr(SimulatedBankingPrecheckAdapter, "submit", spy_submit)
    app = create_app(
        workbook_path=TEAM_PACK,
        dataset_id="BANKING_PRECHECK_STALE_PROFILE_TEST",
        database_path=":memory:",
    )
    with TestClient(app) as client:
        created = _start(client, as_of_date="2026-07-18")
        workflow_run_id = str(created["workflow_run_id"])
        approval_wait = _wait_for_pause_or_completion(client, workflow_run_id)
        assert approval_wait["status"] == "WAITING_FOR_APPROVAL"
        evaluation_case_id = str(approval_wait["evaluation_case_id"])

        artifacts = client.get(
            f"/api/cases/{evaluation_case_id}/artifacts"
        ).json()
        proposal = next(
            item["payload"]
            for item in artifacts
            if item["artifact_type"] == "BANKING_PRECHECK_SUBMISSION_PROPOSAL"
        )
        profile_binding = next(
            binding
            for binding in proposal["candidates"][0]["field_bindings"]
            if binding["required_field"] == "company_profile"
        )
        profile_record_id = profile_binding["source_record_ids"][0]
        runtime = app.state.planner_runtime
        snapshot = runtime._datasets._snapshots[runtime.dataset_id]
        profile_record = next(
            record
            for record in snapshot.sheets["02_OPC_PROFILE"]
            if record.record_id == profile_record_id
        )
        original = profile_record.values["value"]
        profile_record.values["value"] = (
            f"{original}-CHANGED"
            if isinstance(original, str)
            else original + 1
            if isinstance(original, (int, float)) and not isinstance(original, bool)
            else not original
            if isinstance(original, bool)
            else "CHANGED"
        )

        approval_request = client.get(
            f"/api/cases/{evaluation_case_id}/approval-requests"
        ).json()[0]
        approved = client.post(
            f"/api/approval-requests/{approval_request['request_id']}/decision",
            json={
                "decision": "APPROVE",
                "decided_by": "FOUNDER",
                "reason": "HUMAN_REVIEW_COMPLETED",
            },
        )
        assert approved.status_code == 200
        failed = _wait_for_pause_or_completion(client, workflow_run_id)
        assert failed["status"] == "FAILED_SAFE"
        assert failed["current_stage"] == "BANKING_PRECHECK_EXECUTION"
        assert adapter_calls == []

        final_artifacts = client.get(
            f"/api/cases/{evaluation_case_id}/artifacts"
        ).json()
        assert not any(
            item["artifact_type"] == "BANKING_PRECHECK_RESULT_SET"
            for item in final_artifacts
        )
