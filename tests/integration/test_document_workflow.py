"""End-to-end Decision-to-Document preparation and release governance tests."""

import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from opc_mis.api.application import create_app

TEAM_PACK = Path(
    "data/input/MISTalent2026_OPC_AgenticAI_TeamPack_v3.xlsx"
).resolve()
TEST_HMAC_KEY = "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("OPENAI_ENABLED", "false")
    monkeypatch.setenv("OPC_MIS_MASKING_HMAC_KEY_BASE64", TEST_HMAC_KEY)
    app = create_app(
        workbook_path=TEAM_PACK,
        dataset_id="DOCUMENT_WORKFLOW_TEST",
        database_path=":memory:",
    )
    with TestClient(app) as test_client:
        yield test_client


def _wait(client: TestClient, workflow_run_id: str) -> dict[str, object]:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        response = client.get(f"/api/workflows/{workflow_run_id}")
        assert response.status_code == 200
        payload = response.json()
        if payload["status"] not in {"PENDING", "RUNNING"}:
            return payload
        time.sleep(0.02)
    raise AssertionError("Workflow did not reach a durable terminal or wait state.")


def _start(client: TestClient, *, as_of_date: str) -> tuple[str, dict[str, object]]:
    created = client.post(
        "/api/cases/run",
        json={
            "contract_id": "CON-004",
            "evaluation_scope": ["FINANCE", "OPERATIONS", "RISK"],
            "as_of_date": as_of_date,
        },
    )
    assert created.status_code == 202
    workflow_run_id = created.json()["workflow_run_id"]
    return workflow_run_id, _wait(client, workflow_run_id)


def _approve(
    client: TestClient,
    approval_request_id: str,
    *,
    decision: str = "APPROVE",
) -> None:
    response = client.post(
        f"/api/approval-requests/{approval_request_id}/decision",
        json={
            "decision": decision,
            "decided_by": "FOUNDER",
            "reason": "HUMAN_REVIEW_COMPLETED",
        },
    )
    assert response.status_code == 200


def _advance_to_document_wait(
    client: TestClient,
    *,
    as_of_date: str,
) -> tuple[str, str, dict[str, object]]:
    workflow_run_id, amount_wait = _start(client, as_of_date=as_of_date)
    assert amount_wait["current_stage"] == "DECISION_POST_BANKING_REVIEW"
    evaluation_case_id = str(amount_wait["evaluation_case_id"])
    amount_response = client.post(
        f"/api/cases/{evaluation_case_id}/banking/input-supplements",
        json={
            "workflow_run_id": workflow_run_id,
            "missing_request_id": amount_wait["pending_missing_data_ids"][0],
            "requested_amount": 420_000_000,
            "requested_amount_currency": "VND",
            "evidence_note": "Founder confirmed the precheck amount.",
        },
    )
    assert amount_response.status_code == 202
    precheck_wait = _wait(client, workflow_run_id)
    assert precheck_wait["blocked_action"] == "SUBMIT_BANKING_PRECHECK"
    _approve(client, str(precheck_wait["pending_approval_ids"][0]))
    document_wait = _wait(client, workflow_run_id)
    assert document_wait["status"] == "WAITING_FOR_INPUT"
    assert document_wait["current_stage"] == "DOCUMENT_PREPARATION"
    return workflow_run_id, evaluation_case_id, document_wait


def _submit_signed_contract(
    client: TestClient,
    *,
    workflow_run_id: str,
    evaluation_case_id: str,
    document_wait: dict[str, object],
) -> dict[str, object]:
    request_id = document_wait["pending_missing_data_ids"][0]
    invalid_path = client.post(
        f"/api/cases/{evaluation_case_id}/documents/evidence-supplements",
        json={
            "workflow_run_id": workflow_run_id,
            "missing_request_id": request_id,
            "document_reference_id": "C:\\private\\signed-contract.pdf",
            "content_sha256": "a" * 64,
            "document_type": "SIGNED_CONTRACT",
            "evidence_note": "REQUESTED_DOCUMENT_REFERENCE_SUPPLIED",
        },
    )
    assert invalid_path.status_code == 422
    secret_reference = client.post(
        f"/api/cases/{evaluation_case_id}/documents/evidence-supplements",
        json={
            "workflow_run_id": workflow_run_id,
            "missing_request_id": request_id,
            "document_reference_id": "sk-proj-must-not-be-persisted",
            "content_sha256": "a" * 64,
            "document_type": "SIGNED_CONTRACT",
            "evidence_note": "REQUESTED_DOCUMENT_REFERENCE_SUPPLIED",
        },
    )
    assert secret_reference.status_code == 422
    assert "sk-proj-must-not-be-persisted" not in secret_reference.text
    accepted = client.post(
        f"/api/cases/{evaluation_case_id}/documents/evidence-supplements",
        json={
            "workflow_run_id": workflow_run_id,
            "missing_request_id": request_id,
            "document_reference_id": "DOCREF-00000000-0000-4000-8000-000000000003",
            "content_sha256": "a" * 64,
            "document_type": "SIGNED_CONTRACT",
            "evidence_note": "REQUESTED_DOCUMENT_REFERENCE_SUPPLIED",
        },
    )
    assert accepted.status_code == 202
    return _wait(client, workflow_run_id)


def test_document_wait_resume_creates_internal_package_without_release_approval(
    client: TestClient,
) -> None:
    workflow_run_id, evaluation_case_id, document_wait = _advance_to_document_wait(
        client,
        as_of_date="2026-07-21",
    )
    assert document_wait["banking_precheck_outcomes"] == [
        "CONDITIONAL_PRECHECK"
    ]
    assert document_wait["banking_precheck_eligibility_statuses"] == ["ELIGIBLE"]
    assert document_wait["banking_precheck_guarantee_decisions"] == [
        "CONDITIONAL"
    ]
    assert document_wait["banking_precheck_supported_amounts"] == [420_000_000]
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
    assert len(document_wait["document_preparation_request_ids"]) == 1
    assert len(document_wait["document_checklist_ids"]) == 1
    assert len(document_wait["document_package_draft_ids"]) == 1
    assert document_wait["document_package_readinesses"] == ["WAITING_FOR_INPUT"]
    assert document_wait["document_pending_codes"] == ["SIGNED_CONTRACT"]
    assert document_wait["document_release_package_ids"] == []
    assert document_wait["document_external_release_performed"] is False

    artifacts = client.get(f"/api/cases/{evaluation_case_id}/artifacts").json()
    package_artifact = next(
        item for item in artifacts if item["artifact_type"] == "DOCUMENT_PACKAGE_DRAFT"
    )
    package_text = str(package_artifact["payload"])
    assert "OPC-001" not in package_text
    assert "OPC Digital Operations Co." not in package_text
    manual_release = client.post(
        f"/api/cases/{evaluation_case_id}/protected-actions/"
        "SEND_DOCUMENT_TO_EXTERNAL_PARTNER",
        json={
            "workflow_run_id": workflow_run_id,
            "payload_artifact_id": package_artifact["artifact_id"],
            "requested_by": "DOCUMENT_AGENT",
            "payload": {"document_sent_to_partner": True},
        },
    )
    assert manual_release.status_code == 409

    package_ready = _submit_signed_contract(
        client,
        workflow_run_id=workflow_run_id,
        evaluation_case_id=evaluation_case_id,
        document_wait=document_wait,
    )
    assert package_ready["status"] == "COMPLETED"
    assert package_ready["current_stage"] == "INTERNAL_DECISION_PACKAGE_READY"
    assert package_ready["resume_stage"] is None
    assert package_ready["blocked_action"] is None
    assert package_ready["pending_approval_ids"] == []
    assert len(package_ready["document_release_package_ids"]) == 1
    assert package_ready["document_package_readinesses"] == [
        "READY_FOR_INTERNAL_DECISION"
    ]
    assert package_ready["document_pending_codes"] == []
    assert len(package_ready["document_evidence_supplement_ids"]) == 1
    assert package_ready["document_release_package_ready"] is True
    assert package_ready["internal_decision_package_ready"] is True
    assert package_ready["internal_decision_assembly_path"] == (
        "CONDITIONAL_DOCUMENT_READY"
    )
    assert package_ready["internal_decision_package_id"]
    assert package_ready["ready_for_internal_decision"] is True
    assert package_ready["document_release_authorized"] is False
    assert package_ready["document_external_release_performed"] is False

    requests = client.get(
        f"/api/cases/{evaluation_case_id}/approval-requests"
    ).json()
    assert any(
        item["command"]["action_type"] == "SUBMIT_BANKING_PRECHECK"
        and item["status"] == "APPROVED"
        for item in requests
    )
    assert not any(
        item["command"]["action_type"]
        == "SEND_DOCUMENT_TO_EXTERNAL_PARTNER"
        for item in requests
    )
    release_artifacts = client.get(
        f"/api/cases/{evaluation_case_id}/artifacts"
    ).json()
    release_artifact = next(
        item
        for item in release_artifacts
        if item["artifact_type"] == "DOCUMENT_RELEASE_PACKAGE"
    )
    assert release_artifact["payload"]["approval_condition_codes"] == [
        "CONTRACT_SIGNED",
        "CASHFLOW_BUFFER_CONFIRMED",
    ]
    assert release_artifact["payload"]["limitation_codes"] == [
        "DOCUMENT_REFERENCE_NOT_REPOSITORY_VERIFIED",
        "DRAFT_NOT_SIGNED",
        "CASHFLOW_OPC_GLOBAL_NOT_CONTRACT_ATTRIBUTABLE",
    ]
    release_manifest = release_artifact["payload"]["document_manifest"]
    assert len(release_manifest) == 4
    signed_manifest = next(
        item for item in release_manifest if item["document_code"] == "SIGNED_CONTRACT"
    )
    assert signed_manifest["status"] == "AVAILABLE_WITH_LIMITATIONS"
    assert signed_manifest["limitation_codes"] == [
        "DOCUMENT_REFERENCE_NOT_REPOSITORY_VERIFIED"
    ]
    assert release_artifact["payload"]["release_authorized"] is False
    assert release_artifact["payload"]["external_release_performed"] is False
    events = client.get(f"/api/workflows/{workflow_run_id}/events").json()
    event_types = {item["event_type"] for item in events}
    assert "DOCUMENT_RELEASE_PACKAGE_READY" in event_types
    assert "INTERNAL_DECISION_PACKAGE_READY" in event_types
    assert "DOCUMENT_EXTERNAL_RELEASE_PROPOSAL" not in event_types
    assert "DOCUMENT_EXTERNAL_RELEASE_AUTHORIZED" not in event_types
    assert "DOCUMENT_EXTERNAL_RELEASE_DECLINED" not in event_types


def test_package_ready_cannot_be_released_through_the_generic_action_api(
    client: TestClient,
) -> None:
    workflow_run_id, evaluation_case_id, document_wait = _advance_to_document_wait(
        client,
        as_of_date="2026-07-22",
    )
    package_ready = _submit_signed_contract(
        client,
        workflow_run_id=workflow_run_id,
        evaluation_case_id=evaluation_case_id,
        document_wait=document_wait,
    )
    assert package_ready["current_stage"] == "INTERNAL_DECISION_PACKAGE_READY"
    artifacts = client.get(f"/api/cases/{evaluation_case_id}/artifacts").json()
    release_artifact = next(
        item
        for item in artifacts
        if item["artifact_type"] == "DOCUMENT_RELEASE_PACKAGE"
    )
    attempted = client.post(
        f"/api/cases/{evaluation_case_id}/protected-actions/"
        "SEND_DOCUMENT_TO_EXTERNAL_PARTNER",
        json={
            "workflow_run_id": workflow_run_id,
            "payload_artifact_id": release_artifact["artifact_id"],
            "requested_by": "DOCUMENT_AGENT",
            "payload": {"document_sent_to_partner": True},
        },
    )
    assert attempted.status_code == 409
    requests = client.get(
        f"/api/cases/{evaluation_case_id}/approval-requests"
    ).json()
    assert not any(
        item["command"]["action_type"]
        == "SEND_DOCUMENT_TO_EXTERNAL_PARTNER"
        for item in requests
    )
    unchanged = client.get(f"/api/workflows/{workflow_run_id}").json()
    assert unchanged["status"] == "COMPLETED"
    assert unchanged["current_stage"] == "INTERNAL_DECISION_PACKAGE_READY"
    assert unchanged["document_release_package_ready"] is True
    assert unchanged["internal_decision_package_ready"] is True
    assert unchanged["ready_for_internal_decision"] is True
    assert unchanged["document_release_authorized"] is False
    assert unchanged["document_external_release_performed"] is False


def test_missing_masking_key_fails_closed_only_when_document_is_reached(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_ENABLED", "false")
    monkeypatch.delenv("OPC_MIS_MASKING_HMAC_KEY_BASE64", raising=False)
    app = create_app(
        workbook_path=TEAM_PACK,
        dataset_id="DOCUMENT_MISSING_MASKING_KEY_TEST",
        database_path=":memory:",
    )
    with TestClient(app) as client:
        workflow_run_id, amount_wait = _start(client, as_of_date="2026-07-23")
        evaluation_case_id = str(amount_wait["evaluation_case_id"])
        accepted = client.post(
            f"/api/cases/{evaluation_case_id}/banking/input-supplements",
            json={
                "workflow_run_id": workflow_run_id,
                "missing_request_id": amount_wait["pending_missing_data_ids"][0],
                "requested_amount": 420_000_000,
                "requested_amount_currency": "VND",
                "evidence_note": "Reach Document while masking key is unavailable.",
            },
        )
        assert accepted.status_code == 202
        precheck_wait = _wait(client, workflow_run_id)
        assert precheck_wait["status"] == "WAITING_FOR_APPROVAL"
        _approve(client, str(precheck_wait["pending_approval_ids"][0]))
        failed = _wait(client, workflow_run_id)
        assert failed["status"] == "FAILED_SAFE"
        assert failed["current_stage"] == "DOCUMENT_PREPARATION"
        assert failed["banking_precheck_outcomes"] == ["CONDITIONAL_PRECHECK"]
        assert len(failed["document_preparation_request_ids"]) == 1
        assert failed["document_package_draft_ids"] == []
        assert failed["document_release_package_ids"] == []
