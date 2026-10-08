"""FastAPI and Swagger integration tests for contract-specific Planner output."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from opc_mis.api.application import create_app
from opc_mis.domain.team_pack import SheetRegistry
from opc_mis.infrastructure.excel.workbook_loader import WorkbookLoader, compute_sha256

TEAM_PACK = Path("data/input/MISTalent2026_OPC_AgenticAI_TeamPack_v3.xlsx").resolve()


@pytest.fixture(scope="module")
def api_client() -> Iterator[TestClient]:
    app = create_app(workbook_path=TEAM_PACK, dataset_id="API_TEST_DATASET")
    with TestClient(app) as client:
        yield client


def test_swagger_exposes_planner_contract(api_client: TestClient) -> None:
    response = api_client.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/api/contracts" in paths
    assert "/api/planner/evaluate" in paths
    assert "post" in paths["/api/planner/evaluate"]


def test_contract_catalog_comes_from_actual_team_pack(api_client: TestClient) -> None:
    dataset = WorkbookLoader().load("EXPECTED", TEAM_PACK)
    expected = [record.record_id for record in dataset.records(SheetRegistry.CONTRACTS)]

    response = api_client.get("/api/contracts")

    assert response.status_code == 200
    assert response.json()["contract_ids"] == expected


def test_api_evaluates_requested_contract(api_client: TestClient) -> None:
    response = api_client.post(
        "/api/planner/evaluate",
        json={
            "contract_id": "CON-004",
            "evaluation_scope": ["FINANCE", "OPERATIONS", "RISK"],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "COMPLETED"
    assert payload["component_status"] == "COMPLETED_WITH_WARNINGS"
    assert payload["current_node"] == "INITIAL_ASSESSMENT"
    assert payload["planner_result"]["evaluation_case"]["contract_id"] == "CON-004"
    assert "NaN" not in response.text


def test_api_evaluates_every_contract_in_catalog(api_client: TestClient) -> None:
    contract_ids = api_client.get("/api/contracts").json()["contract_ids"]

    for contract_id in contract_ids:
        response = api_client.post(
            "/api/planner/evaluate",
            json={
                "contract_id": contract_id,
                "evaluation_scope": ["FINANCE", "OPERATIONS", "RISK"],
            },
        )

        assert response.status_code == 200
        case = response.json()["planner_result"]["evaluation_case"]
        assert case is not None
        assert case["contract_id"] == contract_id


def test_api_returns_business_pause_for_unknown_contract(api_client: TestClient) -> None:
    response = api_client.post(
        "/api/planner/evaluate",
        json={
            "contract_id": "CON-NOT-PRESENT",
            "evaluation_scope": ["FINANCE", "OPERATIONS", "RISK"],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "WAITING_FOR_INPUT"
    assert payload["current_node"] == "PLANNER_INTAKE"
    assert (
        payload["planner_result"]["missing_data_requests"][0]["requirement_code"]
        == "CONTRACT_NOT_FOUND"
    )


def test_api_rejects_invalid_request(api_client: TestClient) -> None:
    response = api_client.post(
        "/api/planner/evaluate",
        json={"contract_id": "   ", "evaluation_scope": []},
    )

    assert response.status_code == 422


def test_api_never_modifies_team_pack(api_client: TestClient) -> None:
    before = compute_sha256(TEAM_PACK)

    response = api_client.post(
        "/api/planner/evaluate",
        json={"contract_id": "CON-005", "evaluation_scope": ["FINANCE"]},
    )

    assert response.status_code == 200
    assert compute_sha256(TEAM_PACK) == before
