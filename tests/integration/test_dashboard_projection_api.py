"""Founder dashboard projection HTTP boundary tests."""

from collections.abc import Iterator
from pathlib import Path
from time import sleep
from typing import Any

import pytest
from fastapi.testclient import TestClient

from opc_mis.api.application import create_app

TEAM_PACK = Path("data/input/MISTalent2026_OPC_AgenticAI_TeamPack_v3.xlsx").resolve()


@pytest.fixture(scope="module")
def projection_client() -> Iterator[TestClient]:
    app = create_app(
        workbook_path=TEAM_PACK,
        dataset_id="DASHBOARD_PROJECTION_TEST",
        database_path=":memory:",
    )
    with TestClient(app) as client:
        yield client


def _all_keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {
            nested
            for item in value.values()
            for nested in _all_keys(item)
        }
    if isinstance(value, list):
        return {nested for item in value for nested in _all_keys(item)}
    return set()


def test_dashboard_projection_route_returns_canonical_safe_read_model(
    projection_client: TestClient,
) -> None:
    catalog = projection_client.get("/api/contracts").json()
    contract_id = catalog["contract_ids"][0]
    started = projection_client.post(
        "/api/cases/run",
        json={
            "contract_id": contract_id,
            "evaluation_scope": ["FINANCE", "OPERATIONS", "RISK"],
            "as_of_date": "2026-07-19",
        },
    )
    assert started.status_code == 202

    response = projection_client.get(
        f"/api/workflows/{started.json()['workflow_run_id']}/dashboard"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["workflow_run_id"] == started.json()["workflow_run_id"]
    assert payload["contract_id"] == contract_id
    assert payload["progress"]["basis"] == "CANONICAL_WORKFLOW_TASKS"
    assert payload["stages"][2]["parallel"] is True
    assert [item["task_id"] for item in payload["stages"][2]["tasks"]] == [
        "FINANCE_ASSESSMENT",
        "OPERATIONS_ASSESSMENT",
    ]
    assert [item["owner_id"] for item in payload["stages"][2]["tasks"]] == [
        "FINANCE",
        "OPERATIONS",
    ]
    keys = _all_keys(payload)
    assert not keys.intersection(
        {
            "evidence_ids",
            "source_evidence_ids",
            "evidence_refs",
            "source_artifact_ids",
            "sheet",
            "sheet_name",
            "row",
            "row_number",
            "narrative_source",
            "composer_model",
        }
    )


def test_dashboard_projection_route_returns_not_found_for_unknown_run(
    projection_client: TestClient,
) -> None:
    response = projection_client.get("/api/workflows/CWF-DOES-NOT-EXIST/dashboard")

    assert response.status_code == 404


def test_con_004_projection_exposes_explicit_planner_requirement_only(
    projection_client: TestClient,
) -> None:
    catalog = projection_client.get("/api/contracts").json()
    assert "CON-004" in catalog["contract_ids"]
    started = projection_client.post(
        "/api/cases/run",
        json={
            "contract_id": "CON-004",
            "evaluation_scope": ["FINANCE", "OPERATIONS", "RISK"],
            "as_of_date": "2026-07-19",
        },
    )
    assert started.status_code == 202
    url = f"/api/workflows/{started.json()['workflow_run_id']}/dashboard"
    payload: dict[str, Any] = {}
    for _ in range(100):
        response = projection_client.get(url)
        assert response.status_code == 200
        payload = response.json()
        if payload["input"]["available"]:
            break
        sleep(0.02)

    assert payload["input"]["available"] is True
    requirements = payload["input"]["contract_requirements"]
    bound_requirement = next(
        item for item in requirements if item["credit_case_id"] == "CR-002"
    )
    assert bound_requirement == {
        "requirement_type": "PERFORMANCE_BOND",
        "certainty": "REQUIRED",
        "requested_amount": 420_000_000,
        "requested_amount_currency": "VND",
        "credit_case_id": "CR-002",
    }
    assert not _all_keys(payload["input"]).intersection(
        {
            "evidence_ids",
            "source_evidence_ids",
            "evidence_refs",
            "source_record_ids",
            "source_fields",
        }
    )

    for _ in range(250):
        response = projection_client.get(url)
        assert response.status_code == 200
        payload = response.json()
        if payload["execution_status"] == "WAITING_FOR_APPROVAL":
            break
        sleep(0.02)

    assert payload["execution_status"] == "WAITING_FOR_APPROVAL"
    approval = next(
        item
        for item in payload["pending_interactions"]
        if item["interaction_type"] == "APPROVAL"
    )
    assert approval["protected_action"] == "SUBMIT_BANKING_PRECHECK"
    assert approval["approval_request_ids"]
    assert approval["title_vi"] == (
        "Cho phép gửi yêu cầu kiểm tra sơ bộ tới ngân hàng"
    )
