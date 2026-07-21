"""End-to-end tests for checkpoint registration and protected-action pause/resume."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from opc_mis.api.application import create_app

TEAM_PACK = Path("data/input/MISTalent2026_OPC_AgenticAI_TeamPack_v3.xlsx").resolve()


@pytest.fixture(scope="module")
def approval_client() -> Iterator[TestClient]:
    patcher = pytest.MonkeyPatch()
    patcher.setenv("OPENAI_ENABLED", "false")
    try:
        app = create_app(workbook_path=TEAM_PACK, dataset_id="APPROVAL_API_TEST")
        with TestClient(app) as client:
            yield client
    finally:
        patcher.undo()


def create_case(client: TestClient, contract_id: str) -> tuple[str, str]:
    response = client.post(
        "/api/planner/evaluate",
        json={
            "contract_id": contract_id,
            "evaluation_scope": ["FINANCE", "OPERATIONS", "RISK"],
        },
    )
    assert response.status_code == 200
    case_id = response.json()["planner_result"]["evaluation_case"]["evaluation_case_id"]
    artifacts = client.get(f"/api/cases/{case_id}/artifacts").json()
    case_artifact_id = next(
        item["artifact_id"]
        for item in artifacts
        if item["artifact_type"] == "EVALUATION_CASE"
    )
    return case_id, case_artifact_id


def test_document_release_cannot_be_proposed_from_an_arbitrary_case_artifact(
    approval_client: TestClient,
) -> None:
    case_id, artifact_id = create_case(approval_client, "CON-001")
    path = (
        f"/api/cases/{case_id}/protected-actions/"
        "SEND_DOCUMENT_TO_EXTERNAL_PARTNER"
    )
    body = {
        "payload_artifact_id": artifact_id,
        "requested_by": "DOCUMENT_AGENT",
        "payload": {"document_sent_to_partner": True},
    }

    before_scan = approval_client.post(path, json=body)
    assert before_scan.status_code == 409

    scan = approval_client.post(f"/api/cases/{case_id}/initial-risk-assessment")
    assert scan.status_code == 202
    checkpoints = approval_client.get(
        f"/api/cases/{case_id}/approval-checkpoints"
    ).json()["checkpoints"]
    assert {item["source_rule_id"] for item in checkpoints} == {
        "RR-004",
        "RR-005",
    }

    blocked = approval_client.post(path, json=body)
    assert blocked.status_code == 409
    assert "only be proposed automatically" in blocked.json()["detail"]
    requests = approval_client.get(
        f"/api/cases/{case_id}/approval-requests"
    )
    assert requests.status_code == 200
    assert requests.json() == []


def test_amount_checkpoint_does_not_pause_below_threshold_and_requires_input(
    approval_client: TestClient,
) -> None:
    case_id, artifact_id = create_case(approval_client, "CON-002")
    approval_client.post(f"/api/cases/{case_id}/initial-risk-assessment")
    path = (
        f"/api/cases/{case_id}/protected-actions/"
        "COMMIT_LARGE_FINANCIAL_DECISION"
    )
    common = {
        "payload_artifact_id": artifact_id,
        "requested_by": "DECISION_AGENT",
    }

    allowed = approval_client.post(
        path,
        json={**common, "payload": {"requested_amount": 300_000_000}},
    )
    assert allowed.status_code == 200
    assert allowed.json()["gate_status"] == "AUTHORIZED"
    assert allowed.json()["action_authorized"] is True
    machine_authorization = allowed.json()["approval_request"]
    assert machine_authorization["status"] == "AUTHORIZED_WITHOUT_HUMAN"
    assert machine_authorization["command"]["requested_by"] == "PUBLIC_API_CLIENT"
    assert machine_authorization["decision_record"] is None
    assert machine_authorization["policy_artifact_id"]
    assert machine_authorization["policy_artifact_version"] == 1
    assert machine_authorization["policy_input_hash"]

    unsafe_extra = approval_client.post(
        path,
        json={
            **common,
            "payload": {
                "requested_amount": 300_000_000,
                "comment": "access_token=must-not-be-persisted",
            },
        },
    )
    assert unsafe_extra.status_code == 409
    assert "must-not-be-persisted" not in unsafe_extra.text

    missing = approval_client.post(path, json={**common, "payload": {}})
    assert missing.status_code == 409
    assert missing.json()["gate_status"] == "WAITING_FOR_INPUT"
    assert missing.json()["missing_fields"] == ["requested_amount"]
    requests = approval_client.get(
        f"/api/cases/{case_id}/approval-requests"
    ).json()
    assert [item["request_id"] for item in requests] == [
        machine_authorization["request_id"]
    ]


def test_banking_precheck_action_cannot_bypass_the_automatic_proposal(
    approval_client: TestClient,
) -> None:
    case_id, artifact_id = create_case(approval_client, "CON-005")
    approval_client.post(f"/api/cases/{case_id}/initial-risk-assessment")

    response = approval_client.post(
        (
            f"/api/cases/{case_id}/protected-actions/"
            "SUBMIT_BANKING_PRECHECK"
        ),
        json={
            "payload_artifact_id": artifact_id,
            "requested_by": "API_CLIENT",
            "payload": {"precheck_submission_requested": True},
        },
    )

    assert response.status_code == 409
    assert "Master Workflow" in response.json()["detail"]
    assert approval_client.get(
        f"/api/cases/{case_id}/approval-requests"
    ).json() == []


def test_large_amount_pauses_and_rejection_blocks_action(
    approval_client: TestClient,
) -> None:
    case_id, artifact_id = create_case(approval_client, "CON-003")
    approval_client.post(f"/api/cases/{case_id}/initial-risk-assessment")
    paused = approval_client.post(
        (
            f"/api/cases/{case_id}/protected-actions/"
            "COMMIT_LARGE_FINANCIAL_DECISION"
        ),
        json={
            "payload_artifact_id": artifact_id,
            "requested_by": "DECISION_AGENT",
            "payload": {"requested_amount": 300_000_001},
        },
    )
    assert paused.status_code == 202
    request_id = paused.json()["approval_request"]["request_id"]

    unsafe_reason = approval_client.post(
        f"/api/approval-requests/{request_id}/decision",
        json={
            "decision": "REJECT",
            "decided_by": "FOUNDER",
            "reason": "access_token=must-not-be-persisted",
        },
    )
    assert unsafe_reason.status_code == 422
    assert "must-not-be-persisted" not in unsafe_reason.text
    pending = approval_client.get(
        f"/api/cases/{case_id}/approval-requests"
    ).json()
    assert next(item for item in pending if item["request_id"] == request_id)[
        "status"
    ] == "PENDING"

    rejected = approval_client.post(
        f"/api/approval-requests/{request_id}/decision",
        json={
            "decision": "REJECT",
            "decided_by": "FOUNDER",
            "reason": "HUMAN_REVIEW_COMPLETED",
        },
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "BLOCKED"
    assert rejected.json()["gate_status"] == "REJECTED"
    assert rejected.json()["action_authorized"] is False


def test_swagger_exposes_governance_without_duplicate_route_registration(
    approval_client: TestClient,
) -> None:
    openapi = approval_client.get("/openapi.json").json()
    paths = openapi["paths"]

    expected = {
        "/api/cases/{evaluation_case_id}/approval-checkpoints",
        "/api/cases/{evaluation_case_id}/protected-actions/{action_type}",
        "/api/cases/{evaluation_case_id}/approval-requests",
        "/api/approval-requests/{request_id}/decision",
    }
    assert expected.issubset(paths)
    schemas = openapi["components"]["schemas"]
    assert schemas["ApprovalDecisionReasonCode"]["enum"] == [
        "HUMAN_REVIEW_COMPLETED"
    ]
    assert schemas["DocumentEvidenceReasonCode"]["enum"] == [
        "REQUESTED_DOCUMENT_REFERENCE_SUPPLIED"
    ]
    for path in expected:
        assert len(paths[path]) == 1
