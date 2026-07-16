"""End-to-end Operations API tests across the actual TeamPack contracts."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from opc_mis.api.application import create_app
from opc_mis.domain.enums import OperationsMetric
from opc_mis.domain.team_pack import SheetRegistry
from opc_mis.infrastructure.excel.workbook_loader import WorkbookLoader, compute_sha256

TEAM_PACK = Path("data/input/MISTalent2026_OPC_AgenticAI_TeamPack_v3.xlsx").resolve()


@pytest.fixture(scope="module")
def operations_client() -> Iterator[TestClient]:
    app = create_app(workbook_path=TEAM_PACK, dataset_id="OPERATIONS_API_TEST")
    with TestClient(app) as client:
        yield client


def run_operations(
    client: TestClient,
    contract_id: str,
    *,
    as_of_date: str | None = None,
) -> dict[str, object]:
    planner_response = client.post(
        "/api/planner/evaluate",
        json={
            "contract_id": contract_id,
            "evaluation_scope": ["FINANCE", "OPERATIONS", "RISK"],
        },
    )
    assert planner_response.status_code == 200
    case = planner_response.json()["planner_result"]["evaluation_case"]
    response = client.post(
        f"/api/cases/{case['evaluation_case_id']}/operations-assessment",
        json={"as_of_date": as_of_date},
    )
    assert response.status_code == 200
    assert "NaN" not in response.text
    return response.json()


def nested_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        keys = set(value)
        for item in value.values():
            keys.update(nested_keys(item))
        return keys
    if isinstance(value, list):
        keys: set[str] = set()
        for item in value:
            keys.update(nested_keys(item))
        return keys
    return set()


def test_swagger_exposes_operations_endpoint(operations_client: TestClient) -> None:
    paths = operations_client.get("/openapi.json").json()["paths"]

    assert "/api/cases/{evaluation_case_id}/operations-assessment" in paths


def test_operations_runs_for_every_actual_contract_without_downstream_outputs(
    operations_client: TestClient,
) -> None:
    contract_ids = operations_client.get("/api/contracts").json()["contract_ids"]
    forbidden = {
        "risk_level",
        "risk_score",
        "severity",
        "triggered_rule_ids",
        "approval_required",
        "approval_request",
        "banking_option",
        "decision_card",
        "penalty_amount",
        "capacity_score",
        "feasibility",
    }
    for contract_id in contract_ids:
        payload = run_operations(operations_client, contract_id)
        assert payload["status"] == "COMPLETED"
        assert payload["operations_facts"]["contract_id"] == contract_id
        assert payload["operations_assessment"]["contract_id"] == contract_id
        assert not forbidden.intersection(nested_keys(payload["operations_assessment"]))
        assert [item["artifact_type"] for item in payload["generated_artifacts"]] == [
            "OPERATIONS_FACTS",
            "OPERATIONS_ASSESSMENT",
        ]
        assert all(report["status"] == "VALID" for report in payload["validation_reports"])


def test_operations_counts_only_explicit_orders(operations_client: TestClient) -> None:
    dataset = WorkbookLoader().load("EXPECTED_OPERATIONS", TEAM_PACK)
    for contract in dataset.records(SheetRegistry.CONTRACTS):
        payload = run_operations(operations_client, contract.record_id)
        facts = {item["metric"]: item["value"] for item in payload["operations_facts"]["facts"]}
        expected_orders = tuple(
            order
            for order in dataset.records(SheetRegistry.ORDERS)
            if order.values["contract_id"] == contract.record_id
        )
        assert facts[OperationsMetric.RELATED_ORDER_COUNT.value] == len(expected_orders)
        assert {item["order_id"] for item in payload["operations_facts"]["order_schedules"]} == {
            order.record_id for order in expected_orders
        }


def test_source_flagged_and_pending_labels_do_not_become_decisions(
    operations_client: TestClient,
) -> None:
    dataset = WorkbookLoader().load("EXPECTED_STATUS", TEAM_PACK)
    contracts_by_status = {
        order.values["status"]: order.values["contract_id"]
        for order in dataset.records(SheetRegistry.ORDERS)
    }
    for source_status in ("At risk", "Pending approval"):
        contract_id = contracts_by_status[source_status]
        payload = run_operations(operations_client, contract_id)
        schedules = payload["operations_facts"]["order_schedules"]
        assert source_status in {item["source_status"] for item in schedules}
        assert "risk_level" not in nested_keys(payload)
        assert "approval_required" not in nested_keys(payload)


def test_as_of_date_is_explicit_and_has_user_input_lineage(
    operations_client: TestClient,
) -> None:
    contract_id = operations_client.get("/api/contracts").json()["contract_ids"][0]
    without_date = run_operations(operations_client, contract_id)
    with_date = run_operations(operations_client, contract_id, as_of_date="2026-07-16")
    without_facts = {item["metric"]: item for item in without_date["operations_facts"]["facts"]}
    with_facts = {item["metric"]: item for item in with_date["operations_facts"]["facts"]}

    assert without_facts[OperationsMetric.OPEN_PAST_DUE_ORDER_COUNT.value]["value"] is None
    assert with_facts[OperationsMetric.OPEN_PAST_DUE_ORDER_COUNT.value]["value"] is not None
    evidence = with_date["generated_artifacts"][0]["evidence_refs"]
    assert any(
        item["source_type"] == "USER_INPUT" and item["field"] == "as_of_date" for item in evidence
    )


def test_operations_artifacts_are_idempotent(operations_client: TestClient) -> None:
    contract_id = operations_client.get("/api/contracts").json()["contract_ids"][-1]
    first = run_operations(operations_client, contract_id, as_of_date="2026-07-16")
    second = run_operations(operations_client, contract_id, as_of_date="2026-07-16")

    assert [item["artifact_id"] for item in first["generated_artifacts"]] == [
        item["artifact_id"] for item in second["generated_artifacts"]
    ]


def test_operations_requires_existing_planner_case(operations_client: TestClient) -> None:
    response = operations_client.post(
        "/api/cases/CASE-NOT-PRESENT/operations-assessment",
        json={},
    )

    assert response.status_code == 404


def test_operations_never_modifies_team_pack(operations_client: TestClient) -> None:
    before = compute_sha256(TEAM_PACK)
    contract_id = operations_client.get("/api/contracts").json()["contract_ids"][0]

    run_operations(operations_client, contract_id)

    assert compute_sha256(TEAM_PACK) == before
