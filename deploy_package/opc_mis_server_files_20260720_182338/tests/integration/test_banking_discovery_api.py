"""Integration coverage for Banking Phase A and its Swagger boundary."""

import json
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from opc_mis.api.application import create_app
from opc_mis.infrastructure.excel.workbook_loader import compute_sha256

TEAM_PACK = Path("data/input/MISTalent2026_OPC_AgenticAI_TeamPack_v3.xlsx").resolve()
FULL_SCOPE = ["FINANCE", "OPERATIONS", "RISK"]


@pytest.fixture(scope="module")
def banking_client() -> Iterator[TestClient]:
    patcher = pytest.MonkeyPatch()
    patcher.setenv("OPENAI_ENABLED", "false")
    try:
        with TestClient(
            create_app(
                workbook_path=TEAM_PACK,
                dataset_id="BANKING_DISCOVERY_API_TEST",
                database_path=":memory:",
            )
        ) as client:
            yield client
    finally:
        patcher.undo()


def run_case(client: TestClient, contract_id: str) -> dict[str, object]:
    started = client.post(
        "/api/cases/run",
        json={
            "contract_id": contract_id,
            "evaluation_scope": FULL_SCOPE,
            "as_of_date": "2026-07-17",
        },
    )
    assert started.status_code == 202
    workflow_id = started.json()["workflow_run_id"]
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        summary = client.get(f"/api/workflows/{workflow_id}").json()
        if summary["status"] not in {"PENDING", "RUNNING"}:
            return summary
        time.sleep(0.02)
    raise AssertionError("Banking workflow did not reach a terminal state.")


def test_con004_banking_matrix_uses_exact_planner_credit_amount_before_approval(
    banking_client: TestClient,
) -> None:
    before = compute_sha256(TEAM_PACK)
    summary = run_case(banking_client, "CON-004")
    assert summary["status"] == "WAITING_FOR_APPROVAL"
    assert summary["current_stage"] == "WAITING_FOR_APPROVAL"
    assert summary["blocked_action"] == "SUBMIT_BANKING_PRECHECK"
    assert summary["banking_precheck_readiness_status"] == "READY"
    assert summary["decision_post_banking_outcome"] == "BANKING_PRECHECK_READY"
    assert summary["banking_input_supplement_id"] is None
    assert summary["pending_missing_data_ids"] == []
    assert len(summary["pending_approval_ids"]) == 1
    assert summary["banking_precheck_result_set_id"] is None
    assert summary["banking_precheck_outcomes"] == []
    assert summary["banking_precheck_execution_mode"] is None
    assert summary["banking_precheck_external_bank_submission"] is None
    case_id = summary["evaluation_case_id"]
    path = f"/api/cases/{case_id}/banking/internal-discovery"

    first = banking_client.post(path)
    second = banking_client.post(path)

    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    payload = first.json()
    assert payload["status"] == "COMPLETED"
    assert payload["component_status"] == "COMPLETED"
    assert payload["current_node"] == "BANKING_INTERNAL_OPTIONS_READY"
    assert payload["discovery_status"] == "OPTIONS_READY"

    matrix = payload["option_matrix"]
    assert matrix["requested_amount"] == 420_000_000
    assert matrix["requested_amount_currency"] == "VND"
    assert matrix["explicit_credit_case_ids"] == ["CR-002"]
    assert matrix["precheck_executed"] is False
    assert len(matrix["candidates"]) == 1
    candidate = matrix["candidates"][0]
    assert candidate["bank_product_id"] == "BANKPROD-002"
    assert candidate["minimum_amount_currency"] == "VND"
    minimum_check = next(
        item for item in candidate["criteria"] if item["code"] == "MINIMUM_AMOUNT"
    )
    assert minimum_check["status"] == "PASS"
    credit_check = next(
        item
        for item in candidate["criteria"]
        if item["code"] == "EXPLICIT_CREDIT_PROFILE_RELATIONSHIP"
    )
    assert credit_check["status"] == "PASS"
    assert candidate["precheck"]["api_id"] == "API-002"
    assert candidate["precheck"]["status"] == "MOCK_AVAILABLE_NOT_EXECUTED"
    assert candidate["precheck"]["precheck_executed"] is False
    assert matrix["data_gaps"] == []
    assert matrix["allowed_option_combinations"] == []
    assert payload["option_advice"]["status"] == "NOT_INVOKED"
    assert payload["option_advice"]["source"] == "NOT_INVOKED"
    assert payload["option_advice"]["suggestions"] == []
    assert {item["artifact_type"] for item in payload["artifact_refs"]} == {
        "BANKING_OPTION_MATRIX",
        "BANKING_DISCOVERY_RESULT",
        "BANKING_OPTION_ADVICE",
    }
    serialized = json.dumps(payload, ensure_ascii=False)
    assert "CR-002" in serialized
    assert "420000000" in serialized
    approval_requests = banking_client.get(
        f"/api/cases/{case_id}/approval-requests"
    ).json()
    assert len(approval_requests) == 1
    approval = approval_requests[0]
    assert approval["request_id"] == summary["pending_approval_ids"][0]
    assert approval["status"] == "PENDING"
    assert approval["command"]["action_type"] == "SUBMIT_BANKING_PRECHECK"
    assert approval["command"]["payload"]["requested_amount"] == 420_000_000
    assert approval["command"]["payload"]["requested_amount_currency"] == "VND"
    assert compute_sha256(TEAM_PACK) == before


def test_direct_route_is_not_applicable_and_creates_no_banking_artifact(
    banking_client: TestClient,
) -> None:
    summary = run_case(banking_client, "CON-005")
    response = banking_client.post(
        f"/api/cases/{summary['evaluation_case_id']}/banking/internal-discovery"
    )

    assert response.status_code == 200
    assert response.json()["discovery_status"] == "NOT_APPLICABLE"
    assert response.json()["artifact_refs"] == []
    artifacts = banking_client.get(
        f"/api/cases/{summary['evaluation_case_id']}/artifacts"
    ).json()
    assert not any(
        item["artifact_type"].startswith("BANKING_") for item in artifacts
    )


def test_banking_waits_for_decision_request_and_missing_case_is_404() -> None:
    with TestClient(
        create_app(
            workbook_path=TEAM_PACK,
            dataset_id="BANKING_DISCOVERY_WAIT_TEST",
            database_path=":memory:",
        )
    ) as client:
        planner = client.post(
            "/api/planner/evaluate",
            json={"contract_id": "CON-004", "evaluation_scope": FULL_SCOPE},
        ).json()
        case_id = planner["planner_result"]["evaluation_case"][
            "evaluation_case_id"
        ]
        waiting = client.post(
            f"/api/cases/{case_id}/banking/internal-discovery"
        )
        missing = client.post(
            "/api/cases/CASE-NOT-PRESENT/banking/internal-discovery"
        )

    assert waiting.status_code == 409
    assert waiting.json()["status"] == "WAITING_FOR_INPUT"
    assert waiting.json()["discovery_status"] == "WAITING_FOR_REQUEST"
    assert waiting.json()["missing_data_requests"][0]["requirement_code"] == (
        "BANKING_DISCOVERY_REQUEST_REQUIRED"
    )
    assert missing.status_code == 404


def test_banking_swagger_route_is_exposed_once(
    banking_client: TestClient,
) -> None:
    paths = banking_client.get("/openapi.json").json()["paths"]
    path = "/api/cases/{evaluation_case_id}/banking/internal-discovery"
    input_path = "/api/cases/{evaluation_case_id}/banking/input-supplements"

    assert list(paths[path]) == ["post"]
    assert paths[path]["post"]["tags"] == ["Banking"]
    assert list(paths[input_path]) == ["post"]
    assert paths[input_path]["post"]["tags"] == ["Banking"]
