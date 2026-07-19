"""Integration tests for deterministic Decision Initial Route and Master wiring."""

import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from opc_mis.api.application import create_app
from opc_mis.domain.enums import FinanceObservationCode
from opc_mis.infrastructure.excel.workbook_loader import compute_sha256

TEAM_PACK = Path("data/input/MISTalent2026_OPC_AgenticAI_TeamPack_v3.xlsx").resolve()


@pytest.fixture(scope="module")
def decision_client() -> Iterator[TestClient]:
    patcher = pytest.MonkeyPatch()
    patcher.setenv("OPENAI_ENABLED", "false")
    try:
        app = create_app(
            workbook_path=TEAM_PACK,
            dataset_id="DECISION_INITIAL_ROUTE_API_TEST",
            database_path=":memory:",
        )
        with TestClient(app) as client:
            yield client
    finally:
        patcher.undo()


def run_to_route(client: TestClient, contract_id: str) -> dict[str, object]:
    started = client.post(
        "/api/cases/run",
        json={
            "contract_id": contract_id,
            "evaluation_scope": ["FINANCE", "OPERATIONS", "RISK"],
            "as_of_date": "2026-07-17",
        },
    )
    assert started.status_code == 202
    workflow_id = started.json()["workflow_run_id"]
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        payload = client.get(f"/api/workflows/{workflow_id}").json()
        if payload["status"] not in {"PENDING", "RUNNING"}:
            return payload
        time.sleep(0.02)
    raise AssertionError("Decision Initial Route workflow did not complete in time.")


def artifacts_for_summary(
    client: TestClient, summary: dict[str, object]
) -> list[dict[str, object]]:
    response = client.get(f"/api/cases/{summary['evaluation_case_id']}/artifacts")
    assert response.status_code == 200
    return response.json()


def test_initial_route_is_generic_across_actual_contracts(
    decision_client: TestClient,
) -> None:
    contract_ids = decision_client.get("/api/contracts").json()["contract_ids"]

    for contract_id in contract_ids:
        summary = run_to_route(decision_client, contract_id)
        artifacts = artifacts_for_summary(decision_client, summary)
        finance = next(
            item for item in artifacts if item["artifact_type"] == "FINANCE_FACTS"
        )["payload"]
        route = next(
            item
            for item in artifacts
            if item["artifact_type"] == "DECISION_ROUTE_PLAN"
        )["payload"]
        banking_signal = any(
            item["code"]
            == FinanceObservationCode.PERFORMANCE_BOND_REQUIREMENT_OBSERVED.value
            for item in finance["observations"]
        )
        expected = (
            "BANKING_DISCOVERY_REQUIRED"
            if banking_signal
            else "DIRECT_INTERNAL_DECISION"
        )
        banking_requests = [
            item
            for item in artifacts
            if item["artifact_type"] == "BANKING_DISCOVERY_REQUEST"
        ]
        banking_outputs = [
            item
            for item in artifacts
            if item["artifact_type"]
            in {
                "BANKING_OPTION_MATRIX",
                "BANKING_DISCOVERY_RESULT",
                "BANKING_OPTION_ADVICE",
            }
        ]

        assert summary["status"] == (
            "WAITING_FOR_INPUT" if banking_signal else "COMPLETED"
        )
        assert summary["current_stage"] == (
            "DECISION_POST_BANKING_REVIEW"
            if banking_signal
            else "DECISION_ROUTE_PLANNED"
        )
        assert summary["decision_route_outcome"] == expected
        assert bool(summary["banking_discovery_request_id"]) is banking_signal
        assert len(banking_requests) == int(banking_signal)
        assert len(banking_outputs) == 3 * int(banking_signal)
        assert bool(summary["pending_missing_data_ids"]) is banking_signal
        assert summary["banking_precheck_readiness_status"] == (
            "INPUT_REQUIRED" if banking_signal else None
        )
        assert summary["decision_post_banking_outcome"] == (
            "BANKING_INPUT_REQUIRED" if banking_signal else None
        )
        assert route["contract_id"] == contract_id
        assert route["route_outcome"] == expected
        assert route["execution_mode"] == "INITIAL_ROUTE"
        assert "next_node" not in route
        approvals = decision_client.get(
            f"/api/cases/{summary['evaluation_case_id']}/approval-requests"
        ).json()
        assert approvals == []


def test_con004_route_has_exact_observation_and_evidence_lineage(
    decision_client: TestClient,
) -> None:
    summary = run_to_route(decision_client, "CON-004")
    artifacts = artifacts_for_summary(decision_client, summary)
    finance = next(
        item for item in artifacts if item["artifact_type"] == "FINANCE_FACTS"
    )
    route = next(
        item for item in artifacts if item["artifact_type"] == "DECISION_ROUTE_PLAN"
    )
    source_observation = next(
        item
        for item in finance["payload"]["observations"]
        if item["code"] == "PERFORMANCE_BOND_REQUIREMENT_OBSERVED"
    )
    reason = route["payload"]["routing_reasons"][0]

    assert route["payload"]["route_outcome"] == "BANKING_DISCOVERY_REQUIRED"
    assert route["payload"]["required_capabilities"] == [
        "BANKING_INTERNAL_DISCOVERY"
    ]
    assert reason["source_artifact_id"] == finance["artifact_id"]
    assert reason["source_reference_ids"] == [source_observation["observation_id"]]
    assert reason["evidence_ids"] == source_observation["evidence_ids"]
    assert set(reason["evidence_ids"]).issubset(
        {item["evidence_id"] for item in route["evidence_refs"]}
    )
    assert "requested_amount" not in route["payload"]
    assert "banking_option" not in route["payload"]
    banking_request = next(
        item
        for item in artifacts
        if item["artifact_type"] == "BANKING_DISCOVERY_REQUEST"
    )
    request_payload = banking_request["payload"]
    assert request_payload["requested_capability"] == "BANKING_INTERNAL_DISCOVERY"
    assert request_payload["need_types"] == ["PERFORMANCE_BOND"]
    assert request_payload["requested_amount"] is None
    assert request_payload["requested_amount_currency"] == "VND"
    assert request_payload["constraints"] == []
    assert request_payload["source_route_artifact_id"] == route["artifact_id"]
    assert request_payload["source_route_plan_id"] == route["payload"]["route_plan_id"]
    assert request_payload["evidence_ids"] == reason["evidence_ids"]
    assert set(request_payload["evidence_ids"]).issubset(
        {item["evidence_id"] for item in banking_request["evidence_refs"]}
    )


def test_manual_route_waits_when_initial_assessment_is_incomplete(
) -> None:
    with TestClient(
        create_app(
            workbook_path=TEAM_PACK,
            dataset_id="DECISION_ROUTE_INCOMPLETE_TEST",
            database_path=":memory:",
        )
    ) as client:
        planner = client.post(
            "/api/planner/evaluate",
            json={
                "contract_id": "CON-002",
                "evaluation_scope": ["FINANCE", "OPERATIONS", "RISK"],
            },
        ).json()
        case_id = planner["planner_result"]["evaluation_case"]["evaluation_case_id"]
        response = client.post(f"/api/cases/{case_id}/decision-route")

    assert response.status_code == 409
    payload = response.json()
    assert payload["status"] == "WAITING_FOR_INPUT"
    assert {item["field"] for item in payload["missing_data_requests"]} == {
        "FINANCE_FACTS",
        "OPERATIONS_FACTS",
        "INITIAL_RISK_ASSESSMENT",
        "APPROVAL_CHECKPOINTS",
    }
    assert payload["artifact_refs"] == []


def test_manual_route_is_idempotent_and_swagger_exposes_it_once(
    decision_client: TestClient,
) -> None:
    summary = run_to_route(decision_client, "CON-005")
    path = f"/api/cases/{summary['evaluation_case_id']}/decision-route"
    first = decision_client.post(path)
    second = decision_client.post(path)

    assert first.status_code == second.status_code == 200
    assert first.json()["route_plan"] == second.json()["route_plan"]
    assert first.json()["artifact_refs"] == second.json()["artifact_refs"]
    openapi = decision_client.get("/openapi.json").json()["paths"]
    assert list(openapi["/api/cases/{evaluation_case_id}/decision-route"]) == [
        "post"
    ]
    assert openapi["/api/cases/{evaluation_case_id}/decision-route"]["post"][
        "tags"
    ] == ["Decision"]


def test_decision_route_requires_a_case_and_keeps_workbook_read_only(
    decision_client: TestClient,
) -> None:
    before = compute_sha256(TEAM_PACK)

    response = decision_client.post(
        "/api/cases/CASE-NOT-PRESENT/decision-route"
    )

    assert response.status_code == 404
    assert compute_sha256(TEAM_PACK) == before


def test_manual_banking_handoff_is_idempotent_and_does_not_create_approval(
    decision_client: TestClient,
) -> None:
    summary = run_to_route(decision_client, "CON-004")
    path = (
        f"/api/cases/{summary['evaluation_case_id']}"
        "/banking-discovery-request"
    )
    first = decision_client.post(path)
    second = decision_client.post(path)

    assert first.status_code == second.status_code == 200
    assert first.json()["handoff_status"] == "REQUEST_CREATED"
    assert first.json()["banking_discovery_request"] == second.json()[
        "banking_discovery_request"
    ]
    assert first.json()["artifact_refs"] == second.json()["artifact_refs"]
    request = first.json()["banking_discovery_request"]
    assert request["requested_amount"] is None
    assert request["constraints"] == []
    approvals = decision_client.get(
        f"/api/cases/{summary['evaluation_case_id']}/approval-requests"
    ).json()
    assert approvals == []


def test_manual_banking_handoff_is_not_applicable_to_a_direct_route(
    decision_client: TestClient,
) -> None:
    summary = run_to_route(decision_client, "CON-005")
    response = decision_client.post(
        f"/api/cases/{summary['evaluation_case_id']}"
        "/banking-discovery-request"
    )

    assert response.status_code == 200
    assert response.json()["handoff_status"] == "NOT_APPLICABLE"
    assert response.json()["banking_discovery_request"] is None
    assert response.json()["artifact_refs"] == []


def test_banking_handoff_waits_for_decision_route_and_is_exposed_once() -> None:
    with TestClient(
        create_app(
            workbook_path=TEAM_PACK,
            dataset_id="BANKING_HANDOFF_INCOMPLETE_TEST",
            database_path=":memory:",
        )
    ) as client:
        planner = client.post(
            "/api/planner/evaluate",
            json={
                "contract_id": "CON-004",
                "evaluation_scope": ["FINANCE", "OPERATIONS", "RISK"],
            },
        ).json()
        case_id = planner["planner_result"]["evaluation_case"][
            "evaluation_case_id"
        ]
        response = client.post(
            f"/api/cases/{case_id}/banking-discovery-request"
        )
        paths = client.get("/openapi.json").json()["paths"]

    assert response.status_code == 409
    assert response.json()["handoff_status"] == "WAITING_FOR_ROUTE"
    path = "/api/cases/{evaluation_case_id}/banking-discovery-request"
    assert list(paths[path]) == ["post"]
    assert paths[path]["post"]["tags"] == ["Decision"]


def test_banking_handoff_requires_an_evaluation_case(
    decision_client: TestClient,
) -> None:
    before = compute_sha256(TEAM_PACK)

    response = decision_client.post(
        "/api/cases/CASE-NOT-PRESENT/banking-discovery-request"
    )

    assert response.status_code == 404
    assert compute_sha256(TEAM_PACK) == before
