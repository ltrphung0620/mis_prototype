"""End-to-end Finance API tests across the actual TeamPack contracts."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from opc_mis.api.application import create_app
from opc_mis.domain.enums import FinanceMetric
from opc_mis.domain.team_pack import SheetRegistry
from opc_mis.infrastructure.excel.workbook_loader import WorkbookLoader, compute_sha256

TEAM_PACK = Path("data/input/MISTalent2026_OPC_AgenticAI_TeamPack_v3.xlsx").resolve()


@pytest.fixture(scope="module")
def finance_client() -> Iterator[TestClient]:
    patcher = pytest.MonkeyPatch()
    patcher.setenv("OPENAI_ENABLED", "false")
    try:
        app = create_app(workbook_path=TEAM_PACK, dataset_id="FINANCE_API_TEST")
        with TestClient(app) as client:
            yield client
    finally:
        patcher.undo()


def run_finance(client: TestClient, contract_id: str) -> dict[str, object]:
    planner_response = client.post(
        "/api/planner/evaluate",
        json={
            "contract_id": contract_id,
            "evaluation_scope": ["FINANCE", "OPERATIONS", "RISK"],
        },
    )
    assert planner_response.status_code == 200
    case = planner_response.json()["planner_result"]["evaluation_case"]
    assert case is not None
    finance_response = client.post(f"/api/cases/{case['evaluation_case_id']}/finance-assessment")
    assert finance_response.status_code == 200
    assert "NaN" not in finance_response.text
    return finance_response.json()


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


def test_swagger_exposes_finance_and_artifact_endpoints(
    finance_client: TestClient,
) -> None:
    paths = finance_client.get("/openapi.json").json()["paths"]

    assert "/api/cases/{evaluation_case_id}/finance-assessment" in paths
    assert "/api/cases/{evaluation_case_id}/artifacts" in paths


def test_finance_runs_for_every_actual_contract_without_downstream_outputs(
    finance_client: TestClient,
) -> None:
    contract_ids = finance_client.get("/api/contracts").json()["contract_ids"]

    for contract_id in contract_ids:
        payload = run_finance(finance_client, contract_id)
        assert payload["status"] == "COMPLETED"
        assert payload["finance_facts"]["contract_id"] == contract_id
        assert payload["finance_assessment"]["contract_id"] == contract_id
        assert payload["finance_assessment"]["narrative_source"] == ("DETERMINISTIC_FALLBACK")
        artifacts = payload["generated_artifacts"]
        assert [item["artifact_type"] for item in artifacts] == [
            "FINANCE_FACTS",
            "FINANCE_ASSESSMENT",
        ]
        assert len(artifacts[0]["input_artifact_ids"]) == 2
        assert len(artifacts[1]["input_artifact_ids"]) == 3
        assert all(report["status"] == "VALID" for report in payload["validation_reports"])
        forbidden = {
            "risk_level",
            "risk_score",
            "severity",
            "triggered_rule_ids",
            "approval_required",
            "approval_request",
            "banking_option",
            "decision_card",
        }
        assert not forbidden.intersection(nested_keys(payload["finance_assessment"]))


def test_finance_totals_match_explicit_team_pack_relationships(
    finance_client: TestClient,
) -> None:
    dataset = WorkbookLoader().load("EXPECTED_FINANCE", TEAM_PACK)
    for contract in dataset.records(SheetRegistry.CONTRACTS):
        payload = run_finance(finance_client, contract.record_id)
        case_facts = payload["finance_facts"]["facts"]
        facts = {item["metric"]: item["value"] for item in case_facts}
        orders = tuple(
            order
            for order in dataset.records(SheetRegistry.ORDERS)
            if order.values["contract_id"] == contract.record_id
        )
        order_ids = {order.record_id for order in orders}
        invoices = tuple(
            invoice
            for invoice in dataset.records(SheetRegistry.INVOICES)
            if invoice.values["order_id"] in order_ids
        )
        assert facts[FinanceMetric.ORDER_REVENUE_TOTAL.value] == sum(
            order.values["order_revenue"] for order in orders
        )
        assert facts[FinanceMetric.ORDER_ESTIMATED_COST_TOTAL.value] == sum(
            order.values["estimated_cost"] for order in orders
        )
        assert facts[FinanceMetric.INVOICE_TOTAL.value] == sum(
            invoice.values["invoice_amount"] for invoice in invoices
        )


def test_finance_artifacts_are_idempotent(finance_client: TestClient) -> None:
    contract_id = finance_client.get("/api/contracts").json()["contract_ids"][0]
    first = run_finance(finance_client, contract_id)
    second = run_finance(finance_client, contract_id)

    assert [item["artifact_id"] for item in first["generated_artifacts"]] == [
        item["artifact_id"] for item in second["generated_artifacts"]
    ]
    assert [item["version"] for item in second["generated_artifacts"]] == [1, 1]


def test_finance_requires_an_existing_planner_case(finance_client: TestClient) -> None:
    response = finance_client.post("/api/cases/CASE-NOT-PRESENT/finance-assessment")

    assert response.status_code == 404


def test_finance_never_modifies_team_pack(finance_client: TestClient) -> None:
    before = compute_sha256(TEAM_PACK)
    contract_id = finance_client.get("/api/contracts").json()["contract_ids"][-1]

    run_finance(finance_client, contract_id)

    assert compute_sha256(TEAM_PACK) == before
