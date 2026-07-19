"""Verify one Master Workflow owns durable approval pause/resume state."""

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from opc_mis.api.application import create_app

TEAM_PACK = Path("data/input/MISTalent2026_OPC_AgenticAI_TeamPack_v3.xlsx").resolve()
FULL_SCOPE = ["FINANCE", "OPERATIONS", "RISK"]
BANKING_TEST_AMOUNT = 350_000_000
TEST_HMAC_KEY = "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="


def wait_for_status(
    client: TestClient,
    workflow_run_id: str,
    expected: set[str],
    *,
    timeout_seconds: float = 10,
    required_node: str | None = None,
) -> dict[str, object]:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        response = client.get(f"/api/workflows/{workflow_run_id}")
        assert response.status_code == 200
        payload = response.json()
        required_node_is_durable = required_node is None or any(
            item["node"] == required_node for item in payload["nodes"]
        )
        if payload["status"] in expected and required_node_is_durable:
            return payload
        time.sleep(0.02)
    raise AssertionError(f"Workflow did not reach one of {sorted(expected)}.")


def start_completed_workflow(
    client: TestClient,
    contract_id: str,
) -> dict[str, object]:
    created = client.post(
        "/api/cases/run",
        json={
            "contract_id": contract_id,
            "evaluation_scope": FULL_SCOPE,
            "as_of_date": "2026-07-16",
        },
    )
    assert created.status_code == 202
    workflow_run_id = created.json()["workflow_run_id"]
    terminal = wait_for_status(
        client,
        workflow_run_id,
        {"COMPLETED", "WAITING_FOR_INPUT", "WAITING_FOR_APPROVAL"},
    )
    if terminal["status"] == "COMPLETED":
        return terminal
    if terminal["status"] == "WAITING_FOR_INPUT":
        assert terminal["current_stage"] == "DECISION_POST_BANKING_REVIEW"
        pending_request_ids = terminal["pending_missing_data_ids"]
        assert len(pending_request_ids) == 1
        accepted = client.post(
            (
                f"/api/cases/{terminal['evaluation_case_id']}"
                "/banking/input-supplements"
            ),
            json={
                "workflow_run_id": workflow_run_id,
                "missing_request_id": pending_request_ids[0],
                "requested_amount": BANKING_TEST_AMOUNT,
                "requested_amount_currency": "VND",
                "evidence_note": "Amount confirmed before approval persistence test.",
            },
        )
        assert accepted.status_code == 202
        terminal = wait_for_status(
            client,
            workflow_run_id,
            {"COMPLETED", "WAITING_FOR_APPROVAL"},
        )
    if terminal["status"] == "WAITING_FOR_APPROVAL":
        assert terminal["blocked_action"] == "SUBMIT_BANKING_PRECHECK"
        pending_approval_ids = terminal["pending_approval_ids"]
        assert len(pending_approval_ids) == 1
        approved = client.post(
            f"/api/approval-requests/{pending_approval_ids[0]}/decision",
            json={
                "decision": "APPROVE",
                "decided_by": "FOUNDER",
                "reason": "HUMAN_REVIEW_COMPLETED",
            },
        )
        assert approved.status_code == 200
    return wait_for_status(client, workflow_run_id, {"COMPLETED"})


def subject_artifact_id(client: TestClient, case_id: str) -> str:
    artifacts = client.get(f"/api/cases/{case_id}/artifacts").json()
    return next(
        item["artifact_id"]
        for item in artifacts
        if item["artifact_type"] == "EVALUATION_CASE"
    )


def start_precheck_approval_wait(
    client: TestClient,
) -> dict[str, object]:
    """Advance CON-004 to the persisted Banking precheck approval gate."""
    created = client.post(
        "/api/cases/run",
        json={
            "contract_id": "CON-004",
            "evaluation_scope": FULL_SCOPE,
            "as_of_date": "2026-07-16",
        },
    )
    assert created.status_code == 202
    workflow_run_id = str(created.json()["workflow_run_id"])
    amount_wait = wait_for_status(client, workflow_run_id, {"WAITING_FOR_INPUT"})
    assert amount_wait["current_stage"] == "DECISION_POST_BANKING_REVIEW"
    evaluation_case_id = str(amount_wait["evaluation_case_id"])
    amount_response = client.post(
        f"/api/cases/{evaluation_case_id}/banking/input-supplements",
        json={
            "workflow_run_id": workflow_run_id,
            "missing_request_id": amount_wait["pending_missing_data_ids"][0],
            "requested_amount": BANKING_TEST_AMOUNT,
            "requested_amount_currency": "VND",
            "evidence_note": "Amount confirmed before approval persistence test.",
        },
    )
    assert amount_response.status_code == 202
    precheck_wait = wait_for_status(
        client,
        workflow_run_id,
        {"WAITING_FOR_APPROVAL"},
        required_node="APPROVAL_GATE",
    )
    assert precheck_wait["blocked_action"] == "SUBMIT_BANKING_PRECHECK"
    return precheck_wait


def test_pending_precheck_approval_resumes_after_restart_without_release_gate(
    tmp_path: Path,
) -> None:
    dataset_id = "APPROVAL_RESTART_TEST"
    database_path = tmp_path / "approval-restart.db"
    patcher = pytest.MonkeyPatch()
    patcher.setenv("OPENAI_ENABLED", "false")
    patcher.setenv("OPC_MIS_MASKING_HMAC_KEY_BASE64", TEST_HMAC_KEY)
    try:
        with TestClient(
            create_app(
                workbook_path=TEAM_PACK,
                dataset_id=dataset_id,
                database_path=database_path,
            )
        ) as client:
            waiting = start_precheck_approval_wait(client)
            workflow_run_id = str(waiting["workflow_run_id"])
            case_id = str(waiting["evaluation_case_id"])
            attempts_before = {
                item["node"]: item["attempt"] for item in waiting["nodes"]
            }
            request_id = str(waiting["pending_approval_ids"][0])
            assert waiting["status"] == "WAITING_FOR_APPROVAL"
            assert waiting["current_stage"] == "WAITING_FOR_APPROVAL"
            assert waiting["resume_stage"] == (
                "BANKING_PRECHECK_SUBMISSION_PROPOSAL"
            )
            assert waiting["blocked_action"] == "SUBMIT_BANKING_PRECHECK"
            assert waiting["pending_approval_ids"] == [request_id]
            proposal_artifacts = client.get(
                f"/api/cases/{case_id}/artifacts"
            ).json()
            proposal_artifact = next(
                item
                for item in proposal_artifacts
                if item["artifact_type"]
                == "BANKING_PRECHECK_SUBMISSION_PROPOSAL"
            )
            precheck_request = next(
                item
                for item in client.get(
                    f"/api/cases/{case_id}/approval-requests"
                ).json()
                if item["request_id"] == request_id
            )
            assert precheck_request["subject_artifact_id"] == proposal_artifact[
                "artifact_id"
            ]
            assert precheck_request["command"]["action_type"] == (
                "SUBMIT_BANKING_PRECHECK"
            )
            approval_node = next(
                item for item in waiting["nodes"] if item["node"] == "APPROVAL_GATE"
            )
            assert approval_node["status"] == "WAITING_FOR_APPROVAL"
            assert approval_node["waiting_for"] == [request_id]

        with TestClient(
            create_app(
                workbook_path=TEAM_PACK,
                dataset_id=dataset_id,
                database_path=database_path,
            )
        ) as restarted:
            waiting = restarted.get(f"/api/workflows/{workflow_run_id}").json()
            assert waiting["status"] == "WAITING_FOR_APPROVAL"
            assert waiting["pending_approval_ids"] == [request_id]

            approved = restarted.post(
                f"/api/approval-requests/{request_id}/decision",
                json={
                    "decision": "APPROVE",
                    "decided_by": "FOUNDER",
                    "reason": "HUMAN_REVIEW_COMPLETED",
                },
            )
            assert approved.status_code == 200
            assert approved.json()["status"] == "PENDING"
            assert approved.json()["gate_status"] == "APPROVED"
            assert approved.json()["workflow_run_id"] == workflow_run_id

            document_wait = wait_for_status(
                restarted, workflow_run_id, {"WAITING_FOR_INPUT"}
            )
            assert document_wait["current_stage"] == "DOCUMENT_PREPARATION"
            assert document_wait["document_pending_codes"] == ["SIGNED_CONTRACT"]
            evidence_response = restarted.post(
                f"/api/cases/{case_id}/documents/evidence-supplements",
                json={
                    "workflow_run_id": workflow_run_id,
                    "missing_request_id": document_wait[
                        "pending_missing_data_ids"
                    ][0],
                    "document_reference_id": (
                        "DOCREF-00000000-0000-4000-8000-000000000001"
                    ),
                    "content_sha256": "c" * 64,
                    "document_type": "SIGNED_CONTRACT",
                    "evidence_note": "REQUESTED_DOCUMENT_REFERENCE_SUPPLIED",
                },
            )
            assert evidence_response.status_code == 202
            resumed = wait_for_status(restarted, workflow_run_id, {"COMPLETED"})
            assert resumed["pending_approval_ids"] == []
            assert resumed["resume_stage"] is None
            assert resumed["blocked_action"] is None
            assert resumed["current_stage"] == "INTERNAL_DECISION_PACKAGE_READY"
            assert len(resumed["document_release_package_ids"]) == 1
            assert resumed["document_release_package_ready"] is True
            assert resumed["internal_decision_package_ready"] is True
            assert resumed["internal_decision_assembly_path"] == (
                "CONDITIONAL_DOCUMENT_READY"
            )
            assert resumed["ready_for_internal_decision"] is True
            assert resumed["document_release_authorized"] is False
            assert resumed["document_external_release_performed"] is False
            attempts_after = {
                item["node"]: item["attempt"] for item in resumed["nodes"]
            }
            assert all(
                attempts_after[node] == attempt
                for node, attempt in attempts_before.items()
            )
            approval_node = next(
                item for item in resumed["nodes"] if item["node"] == "APPROVAL_GATE"
            )
            assert approval_node["status"] == "COMPLETED"
            assert approval_node["attempt"] == attempts_before["APPROVAL_GATE"]
            event_types = [
                item["event_type"]
                for item in restarted.get(
                    f"/api/workflows/{workflow_run_id}/events"
                ).json()
            ]
            assert "APPROVAL_REQUESTED" in event_types
            assert "WORKFLOW_PAUSED" in event_types
            assert "APPROVAL_RESOLVED" in event_types
            assert "PROTECTED_ACTION_ALLOWED" in event_types
            assert "WORKFLOW_RESUME_REQUESTED" in event_types
            assert "DOCUMENT_RELEASE_PACKAGE_READY" in event_types
            assert "INTERNAL_DECISION_PACKAGE_READY" in event_types
            assert "DOCUMENT_EXTERNAL_RELEASE_PROPOSAL" not in event_types
            assert "DOCUMENT_EXTERNAL_RELEASE_AUTHORIZED" not in event_types
            assert "DOCUMENT_EXTERNAL_RELEASE_DECLINED" not in event_types
            requests = restarted.get(
                f"/api/cases/{case_id}/approval-requests"
            ).json()
            assert not any(
                item["command"]["action_type"]
                == "SEND_DOCUMENT_TO_EXTERNAL_PARTNER"
                for item in requests
            )
    finally:
        patcher.undo()


def test_rejected_approval_blocks_the_same_master_workflow(tmp_path: Path) -> None:
    dataset_id = "APPROVAL_REJECTION_TEST"
    database_path = tmp_path / "approval-rejection.db"
    patcher = pytest.MonkeyPatch()
    patcher.setenv("OPENAI_ENABLED", "false")
    patcher.setenv("OPC_MIS_MASKING_HMAC_KEY_BASE64", TEST_HMAC_KEY)
    try:
        with TestClient(
            create_app(
                workbook_path=TEAM_PACK,
                dataset_id=dataset_id,
                database_path=database_path,
            )
        ) as client:
            completed = start_completed_workflow(client, "CON-003")
            workflow_run_id = str(completed["workflow_run_id"])
            case_id = str(completed["evaluation_case_id"])
            paused = client.post(
                (
                    f"/api/cases/{case_id}/protected-actions/"
                    "COMMIT_LARGE_FINANCIAL_DECISION"
                ),
                json={
                    "workflow_run_id": workflow_run_id,
                    "payload_artifact_id": subject_artifact_id(client, case_id),
                    "requested_by": "DECISION_AGENT",
                    "payload": {"requested_amount": 300_000_001},
                },
            )
            assert paused.status_code == 202
            request_id = paused.json()["approval_request"]["request_id"]
            rejected = client.post(
                f"/api/approval-requests/{request_id}/decision",
                json={
                    "decision": "REJECT",
                    "decided_by": "FOUNDER",
                    "reason": "HUMAN_REVIEW_COMPLETED",
                },
            )
            assert rejected.status_code == 200
            assert rejected.json()["status"] == "BLOCKED"
            blocked = client.get(f"/api/workflows/{workflow_run_id}").json()
            assert blocked["status"] == "BLOCKED"
            assert blocked["current_stage"] == "PROTECTED_ACTION_REJECTED"
            assert blocked["blocked_action"] == "COMMIT_LARGE_FINANCIAL_DECISION"
            assert blocked["pending_approval_ids"] == []
            approval_node = next(
                item for item in blocked["nodes"] if item["node"] == "APPROVAL_GATE"
            )
            assert approval_node["status"] == "BLOCKED"
            assert client.post(
                f"/api/workflows/{workflow_run_id}/resume"
            ).status_code == 409
    finally:
        patcher.undo()
