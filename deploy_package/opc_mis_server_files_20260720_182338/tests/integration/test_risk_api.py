"""End-to-end tests for Risk pre-scan, persisted wait, and automatic resume."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from opc_mis.api.application import create_app
from opc_mis.business.agents.risk.rule_engine import parse_condition
from opc_mis.business.agents.risk.source_scanner import parse_related_record
from opc_mis.domain.team_pack import SheetRegistry
from opc_mis.infrastructure.excel.workbook_loader import WorkbookLoader, compute_sha256

TEAM_PACK = Path("data/input/MISTalent2026_OPC_AgenticAI_TeamPack_v3.xlsx").resolve()


@pytest.fixture(scope="module")
def risk_client() -> Iterator[TestClient]:
    patcher = pytest.MonkeyPatch()
    patcher.setenv("OPENAI_ENABLED", "false")
    try:
        app = create_app(workbook_path=TEAM_PACK, dataset_id="RISK_API_TEST")
        with TestClient(app) as client:
            yield client
    finally:
        patcher.undo()


def create_case(client: TestClient, contract_id: str) -> dict[str, object]:
    response = client.post(
        "/api/planner/evaluate",
        json={
            "contract_id": contract_id,
            "evaluation_scope": ["FINANCE", "OPERATIONS", "RISK"],
        },
    )
    assert response.status_code == 200
    case = response.json()["planner_result"]["evaluation_case"]
    assert case is not None
    return case


def test_risk_pre_scans_then_waits_and_resumes_automatically(
    risk_client: TestClient,
) -> None:
    case = create_case(risk_client, "CON-004")
    case_id = case["evaluation_case_id"]
    path = f"/api/cases/{case_id}/initial-risk-assessment"

    first = risk_client.post(path)
    assert first.status_code == 202
    waiting = first.json()
    assert waiting["status"] == "WAITING_FOR_DEPENDENCIES"
    assert waiting["component_status"] == "COMPLETED"
    assert waiting["current_node"] == "INITIAL_RISK_FINALIZATION"
    assert waiting["checkpoint_status"] == "WAITING_FOR_FACTS"
    assert waiting["pending_dependencies"] == ["FINANCE_FACTS", "OPERATIONS_FACTS"]
    assert waiting["pre_scan"]["source_rule_ids"]
    assert waiting["pre_scan"]["source_record_counts"]["13_RISK_RULES"] == 7
    assert [item["artifact_type"] for item in waiting["artifact_refs"]] == [
        "RISK_PRE_SCAN",
        "APPROVAL_CHECKPOINTS",
    ]
    checkpoints = waiting["approval_checkpoints"]["checkpoints"]
    assert {item["source_rule_id"] for item in checkpoints} == {
        "RR-004",
        "RR-005",
    }
    assert all(item["status"] == "REGISTERED" for item in checkpoints)
    assert "RR-001" not in {item["source_rule_id"] for item in checkpoints}

    finance = risk_client.post(f"/api/cases/{case_id}/finance-assessment")
    assert finance.status_code == 200
    after_finance = risk_client.get(f"/api/cases/{case_id}/risk-status").json()
    assert after_finance["status"] == "WAITING_FOR_DEPENDENCIES"
    assert after_finance["component_status"] == "COMPLETED"
    assert after_finance["current_node"] == "INITIAL_RISK_FINALIZATION"
    assert after_finance["pending_dependencies"] == ["OPERATIONS_FACTS"]

    operations = risk_client.post(
        f"/api/cases/{case_id}/operations-assessment",
        json={"as_of_date": "2026-07-16"},
    )
    assert operations.status_code == 200
    final = risk_client.get(f"/api/cases/{case_id}/risk-status")
    assert final.status_code == 200
    assert "NaN" not in final.text
    payload = final.json()
    assert payload["status"] == "COMPLETED"
    assert payload["checkpoint_status"] == "COMPLETED_WITH_LIMITATIONS"
    assert payload["pending_dependencies"] == []
    assert payload["risk_assessment"]["contract_id"] == "CON-004"
    assert payload["risk_assessment"]["overall_risk_level"] == "HIGH"
    assert "RR-003" in payload["risk_assessment"]["triggered_rule_ids"]
    assert {item["alert_id"] for item in payload["risk_assessment"]["source_alerts"]} == {
        "AL-003"
    }
    assert all(
        item["code"].startswith("GLOBAL_")
        for item in payload["risk_assessment"]["global_context_signals"]
    )
    assert "approval_signals" not in payload
    assert {
        item["source_rule_id"]
        for item in payload["approval_checkpoints"]["checkpoints"]
    } == {
        "RR-004",
        "RR-005",
    }
    assert "generated_artifacts" not in payload
    assert "validation_reports" not in payload


def test_risk_pre_scan_is_idempotent_and_not_reversioned_by_resume(
    risk_client: TestClient,
) -> None:
    case = create_case(risk_client, "CON-005")
    case_id = case["evaluation_case_id"]
    path = f"/api/cases/{case_id}/initial-risk-assessment"

    first = risk_client.post(path).json()
    second = risk_client.post(path).json()
    first_ref = next(
        item for item in first["artifact_refs"] if item["artifact_type"] == "RISK_PRE_SCAN"
    )
    second_ref = next(
        item for item in second["artifact_refs"] if item["artifact_type"] == "RISK_PRE_SCAN"
    )
    assert first_ref == second_ref
    assert first_ref["version"] == 1

    risk_client.post(f"/api/cases/{case_id}/finance-assessment")
    risk_client.post(f"/api/cases/{case_id}/operations-assessment", json={})
    final = risk_client.get(f"/api/cases/{case_id}/risk-status").json()
    final_pre_scan = next(
        item for item in final["artifact_refs"] if item["artifact_type"] == "RISK_PRE_SCAN"
    )
    assert final_pre_scan == first_ref


def test_global_transaction_signal_never_becomes_case_risk_by_itself(
    risk_client: TestClient,
) -> None:
    case = create_case(risk_client, "CON-001")
    case_id = case["evaluation_case_id"]
    risk_client.post(f"/api/cases/{case_id}/initial-risk-assessment")
    risk_client.post(f"/api/cases/{case_id}/finance-assessment")
    risk_client.post(f"/api/cases/{case_id}/operations-assessment", json={})

    assessment = risk_client.get(f"/api/cases/{case_id}/risk-status").json()[
        "risk_assessment"
    ]
    assert assessment["global_context_signals"]
    assert assessment["overall_risk_level"] == "NO_CASE_SIGNAL"
    assert assessment["triggered_rule_ids"] == []


def test_risk_runs_generically_for_every_contract_from_workbook_rules(
    risk_client: TestClient,
) -> None:
    dataset = WorkbookLoader().load("EXPECTED_RISK", TEAM_PACK)
    margin_rule = next(
        item
        for item in dataset.records(SheetRegistry.RISK_RULES)
        if str(item.values["trigger_condition"]).startswith("gross_margin ")
    )
    parsed = parse_condition(str(margin_rule.values["trigger_condition"]))
    assert parsed is not None
    severity_weight = {"Low": 1, "Medium": 2, "High": 3, "Critical": 4}

    for contract in dataset.records(SheetRegistry.CONTRACTS):
        case = create_case(risk_client, contract.record_id)
        case_id = case["evaluation_case_id"]
        risk_client.post(f"/api/cases/{case_id}/initial-risk-assessment")
        risk_client.post(f"/api/cases/{case_id}/finance-assessment")
        risk_client.post(f"/api/cases/{case_id}/operations-assessment", json={})
        assessment = risk_client.get(f"/api/cases/{case_id}/risk-status").json()[
            "risk_assessment"
        ]

        case_ids = {
            case["contract_id"],
            case["customer_id"],
            *case["related_order_ids"],
            *case["related_invoice_ids"],
            *case["related_service_ids"],
            *case["related_credit_case_ids"],
        }
        expected_alerts = tuple(
            alert
            for alert in dataset.records(SheetRegistry.ALERTS)
            if set(parse_related_record(alert.values["related_record"])) & case_ids
        )
        expected_severities = [alert.values["severity"] for alert in expected_alerts]
        if contract.values["gross_margin"] < parsed.threshold:
            expected_severities.append(margin_rule.values["severity"])
        expected_level = (
            max(expected_severities, key=severity_weight.__getitem__).upper()
            if expected_severities
            else "NO_CASE_SIGNAL"
        )
        assert assessment["overall_risk_level"] == expected_level
        assert {item["alert_id"] for item in assessment["source_alerts"]} == {
            item.record_id for item in expected_alerts
        }


def test_risk_requires_planner_and_never_modifies_team_pack(
    risk_client: TestClient,
) -> None:
    before = compute_sha256(TEAM_PACK)

    response = risk_client.post(
        "/api/cases/CASE-NOT-PRESENT/initial-risk-assessment"
    )

    assert response.status_code == 404
    assert compute_sha256(TEAM_PACK) == before


def test_swagger_exposes_risk_start_and_status(risk_client: TestClient) -> None:
    paths = risk_client.get("/openapi.json").json()["paths"]

    assert "/api/cases/{evaluation_case_id}/initial-risk-assessment" in paths
    assert "/api/cases/{evaluation_case_id}/risk-status" in paths
    assert paths["/api/cases/{evaluation_case_id}/initial-risk-assessment"]["post"][
        "tags"
    ] == ["Risk"]
