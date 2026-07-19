"""End-to-end tests for the durable one-call automatic Initial Assessment workflow."""

import asyncio
import time
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from opc_mis.api.application import create_app
from opc_mis.domain.case_workflow_models import CaseWorkflowRun
from opc_mis.domain.enums import EvaluationScope, WorkflowStatus
from opc_mis.domain.workflow import WorkflowNode
from opc_mis.infrastructure.excel.dataset_adapter import ExcelDatasetIngestion
from opc_mis.infrastructure.excel.workbook_loader import compute_sha256
from opc_mis.infrastructure.persistence.memory_dataset_repository import (
    InMemoryDatasetRepository,
)
from opc_mis.infrastructure.persistence.sqlite_database import SQLiteDatabase
from opc_mis.infrastructure.persistence.sqlite_workflow_repository import (
    SQLiteCaseWorkflowRepository,
)

TEAM_PACK = Path("data/input/MISTalent2026_OPC_AgenticAI_TeamPack_v3.xlsx").resolve()
FULL_SCOPE = ["FINANCE", "OPERATIONS", "RISK"]
BANKING_TEST_AMOUNT = 350_000_000
BANKING_EVIDENCE_NOTE = "Amount confirmed for integration-test readiness."
TEST_HMAC_KEY = "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="


@pytest.fixture(scope="module")
def workflow_client() -> Iterator[TestClient]:
    patcher = pytest.MonkeyPatch()
    patcher.setenv("OPENAI_ENABLED", "false")
    patcher.setenv("OPC_MIS_MASKING_HMAC_KEY_BASE64", TEST_HMAC_KEY)
    try:
        app = create_app(
            workbook_path=TEAM_PACK,
            dataset_id="AUTOMATIC_WORKFLOW_TEST",
            database_path=":memory:",
        )
        with TestClient(app) as client:
            yield client
    finally:
        patcher.undo()


def start(client: TestClient, contract_id: str) -> dict[str, object]:
    response = client.post(
        "/api/cases/run",
        json={
            "contract_id": contract_id,
            "evaluation_scope": FULL_SCOPE,
            "as_of_date": "2026-07-16",
        },
    )
    assert response.status_code == 202
    return response.json()


def wait_for_terminal(
    client: TestClient,
    workflow_run_id: str,
    *,
    timeout_seconds: float = 10,
) -> dict[str, object]:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        response = client.get(f"/api/workflows/{workflow_run_id}")
        assert response.status_code == 200
        payload = response.json()
        if payload["status"] not in {"PENDING", "RUNNING"}:
            return payload
        time.sleep(0.02)
    raise AssertionError("Automatic workflow did not reach a terminal/wait state in time.")


def submit_required_banking_amount(
    client: TestClient,
    paused: dict[str, object],
) -> tuple[dict[str, object], dict[str, object]]:
    """Resolve the exact durable amount request and wait for automatic resume."""
    assert paused["status"] == "WAITING_FOR_INPUT"
    assert paused["current_stage"] == "DECISION_POST_BANKING_REVIEW"
    pending_request_ids = paused["pending_missing_data_ids"]
    assert isinstance(pending_request_ids, list)
    assert len(pending_request_ids) == 1
    workflow_run_id = str(paused["workflow_run_id"])
    evaluation_case_id = str(paused["evaluation_case_id"])

    accepted = client.post(
        f"/api/cases/{evaluation_case_id}/banking/input-supplements",
        json={
            "workflow_run_id": workflow_run_id,
            "missing_request_id": pending_request_ids[0],
            "requested_amount": BANKING_TEST_AMOUNT,
            "requested_amount_currency": "VND",
            "evidence_note": BANKING_EVIDENCE_NOTE,
        },
    )

    assert accepted.status_code == 202
    payload = accepted.json()
    assert payload["status"] == "COMPLETED"
    assert payload["current_node"] == "BANKING_INPUT_SUPPLEMENT"
    assert payload["supplement"]["requested_amount"] == BANKING_TEST_AMOUNT
    assert payload["supplement"]["provider"] == "AUTHORIZED_STAFF"
    assert payload["supplement"]["resolved_request_ids"] == pending_request_ids
    assert payload["workflow"]["workflow_run_id"] == workflow_run_id
    return payload, wait_for_terminal(client, workflow_run_id)


def complete_banking_pause_if_required(
    client: TestClient,
    summary: dict[str, object],
) -> dict[str, object]:
    """Resolve Banking input and approval pauses while leaving direct routes unchanged."""
    current = summary
    for _ in range(6):
        if current["status"] == "WAITING_FOR_INPUT" and current[
            "current_stage"
        ] == "DECISION_POST_BANKING_REVIEW":
            _, current = submit_required_banking_amount(client, current)
            continue
        if current["status"] == "WAITING_FOR_INPUT" and current[
            "current_stage"
        ] == "DOCUMENT_PREPARATION":
            pending_ids = current["pending_missing_data_ids"]
            assert isinstance(pending_ids, list)
            assert len(pending_ids) == 1
            evaluation_case_id = str(current["evaluation_case_id"])
            accepted = client.post(
                f"/api/cases/{evaluation_case_id}/documents/evidence-supplements",
                json={
                    "workflow_run_id": current["workflow_run_id"],
                    "missing_request_id": pending_ids[0],
                    "document_reference_id": "DOCREF-00000000-0000-4000-8000-000000000002",
                    "content_sha256": "b" * 64,
                    "document_type": "SIGNED_CONTRACT",
                    "evidence_note": "REQUESTED_DOCUMENT_REFERENCE_SUPPLIED",
                },
            )
            assert accepted.status_code == 202
            current = wait_for_terminal(client, str(current["workflow_run_id"]))
            continue
        if current["status"] == "WAITING_FOR_APPROVAL":
            evaluation_case_id = str(current["evaluation_case_id"])
            pending_ids = current["pending_approval_ids"]
            assert isinstance(pending_ids, list)
            assert len(pending_ids) == 1
            requests = client.get(
                f"/api/cases/{evaluation_case_id}/approval-requests"
            ).json()
            pending_request = next(
                item for item in requests if item["request_id"] == pending_ids[0]
            )
            assert pending_request["command"]["action_type"] == (
                "SUBMIT_BANKING_PRECHECK"
            )
            approved = client.post(
                f"/api/approval-requests/{pending_ids[0]}/decision",
                json={
                    "decision": "APPROVE",
                    "decided_by": "FOUNDER",
                    "reason": "HUMAN_REVIEW_COMPLETED",
                },
            )
            assert approved.status_code == 200
            assert approved.json()["action_authorized"] is True
            requests = client.get(
                f"/api/cases/{evaluation_case_id}/approval-requests"
            ).json()
            assert any(
                item["request_id"] == pending_ids[0]
                and item["status"] == "APPROVED"
                for item in requests
            )
            current = wait_for_terminal(client, str(current["workflow_run_id"]))
            continue
        return current
    raise AssertionError("Workflow exceeded the expected governed pause sequence.")


def test_con004_pauses_for_amount_then_for_submission_approval(
    workflow_client: TestClient,
) -> None:
    before = compute_sha256(TEAM_PACK)

    created = start(workflow_client, "CON-004")
    paused = wait_for_terminal(workflow_client, str(created["workflow_run_id"]))

    assert paused["status"] == "WAITING_FOR_INPUT"
    assert paused["current_stage"] == "DECISION_POST_BANKING_REVIEW"
    assert paused["resume_stage"] == "DECISION_POST_BANKING_REVIEW"
    assert paused["decision_route_outcome"] == "BANKING_DISCOVERY_REQUIRED"
    assert paused["banking_discovery_request_id"]
    assert paused["banking_discovery_status"] == "OPTIONS_READY_WITH_GAPS"
    assert paused["banking_precheck_readiness_status"] == "INPUT_REQUIRED"
    assert paused["decision_post_banking_outcome"] == "BANKING_INPUT_REQUIRED"
    assert paused["pending_missing_data_ids"]
    case_id = str(paused["evaluation_case_id"])
    initial_artifacts = workflow_client.get(
        f"/api/cases/{case_id}/artifacts"
    ).json()
    initial_request = next(
        item
        for item in initial_artifacts
        if item["artifact_type"] == "BANKING_DISCOVERY_REQUEST"
    )
    initial_matrix = next(
        item
        for item in initial_artifacts
        if item["artifact_type"] == "BANKING_OPTION_MATRIX"
    )
    initial_minimum = next(
        item
        for item in initial_matrix["payload"]["candidates"][0]["criteria"]
        if item["code"] == "MINIMUM_AMOUNT"
    )
    assert initial_request["payload"]["requested_amount"] is None
    assert initial_matrix["version"] == 1
    assert initial_matrix["payload"]["requested_amount"] is None
    assert initial_minimum["status"] == "NOT_EVALUABLE"
    assert {item["code"] for item in initial_matrix["payload"]["data_gaps"]} == {
        "REQUESTED_AMOUNT_UNAVAILABLE"
    }

    accepted, approval_wait = submit_required_banking_amount(
        workflow_client, paused
    )

    assert accepted["supplement"]["source_artifact_ids"]
    assert approval_wait["status"] == "WAITING_FOR_APPROVAL"
    assert approval_wait["current_stage"] == "WAITING_FOR_APPROVAL"
    assert approval_wait["resume_stage"] == (
        "BANKING_PRECHECK_SUBMISSION_PROPOSAL"
    )
    assert approval_wait["blocked_action"] == "SUBMIT_BANKING_PRECHECK"
    assert len(approval_wait["pending_approval_ids"]) == 1
    assert approval_wait["banking_precheck_submission_proposal_id"]
    assert approval_wait["banking_precheck_submission_candidate_ids"] == (
        approval_wait["precheck_ready_option_ids"]
    )
    final = complete_banking_pause_if_required(workflow_client, approval_wait)
    assert final["status"] == "COMPLETED"
    assert final["current_stage"] == "INTERNAL_DECISION_PACKAGE_READY"
    assert final["banking_discovery_status"] == "OPTIONS_READY"
    assert final["banking_input_supplement_id"] == accepted["supplement"][
        "supplement_id"
    ]
    assert final["banking_precheck_readiness_status"] == "READY"
    assert final["decision_post_banking_outcome"] == "BANKING_PRECHECK_READY"
    assert final["decision_post_precheck_outcome"] == (
        "CONDITIONAL_OPTIONS_AVAILABLE"
    )
    assert final["precheck_ready_option_ids"]
    assert final["pending_missing_data_ids"] == []
    assert final["banking_discovery_result_id"]
    assert final["banking_option_matrix_id"]
    assert final["banking_option_advice_id"]
    assert final["banking_option_count"] == 1
    assert final["banking_precheck_result_set_id"]
    assert final["banking_precheck_normalized_result_ids"]
    assert final["banking_precheck_outcomes"] == ["CONDITIONAL_PRECHECK"]
    assert final["banking_precheck_eligibility_statuses"] == ["ELIGIBLE"]
    assert final["banking_precheck_guarantee_decisions"] == ["CONDITIONAL"]
    assert final["banking_precheck_supported_amounts"] == [BANKING_TEST_AMOUNT]
    assert final["document_release_package_ready"] is True
    assert final["internal_decision_package_ready"] is True
    assert final["internal_decision_assembly_path"] == (
        "CONDITIONAL_DOCUMENT_READY"
    )
    assert final["ready_for_internal_decision"] is True
    assert final["document_release_authorized"] is False
    assert final["document_external_release_performed"] is False
    assert final["banking_precheck_execution_mode"] == "SIMULATED"
    assert (
        final["banking_precheck_result_authority"]
        == "SIMULATED_NON_BINDING"
    )
    assert final["banking_precheck_external_bank_submission"] is False
    assert final["banking_precheck_bank_approval_obtained"] is False
    # Two Risk checkpoints are registered during the scan.  The exact banking
    # proposal later adds one API-policy checkpoint and one amount checkpoint.
    assert final["approval_checkpoint_count"] == 4
    assert final["pending_approval_ids"] == []
    node_status = {item["node"]: item["status"] for item in final["nodes"]}
    assert set(node_status) == {
        "PLANNER_INTAKE",
        "INITIAL_RISK_PRE_SCAN",
        "FINANCE_ASSESSMENT",
        "OPERATIONS_ASSESSMENT",
        "INITIAL_RISK_FINALIZATION",
        "DECISION_ROUTE_PLANNING",
        "BANKING_DISCOVERY_HANDOFF",
        "BANKING_INTERNAL_DISCOVERY",
        "BANKING_PRECHECK_READINESS",
        "DECISION_POST_BANKING_REVIEW",
        "BANKING_INPUT_SUPPLEMENT",
        "BANKING_PRECHECK_SUBMISSION_PROPOSAL",
        "BANKING_PRECHECK_EXECUTION",
        "DECISION_POST_PRECHECK_REVIEW",
        "DECISION_DOCUMENT_HANDOFF",
        "DOCUMENT_PREPARATION",
        "DOCUMENT_INPUT_INTAKE",
        "INTERNAL_DECISION_PACKAGE_ASSEMBLY",
        "APPROVAL_GATE",
    }
    assert all(
        status in {"COMPLETED", "COMPLETED_WITH_WARNINGS"}
        for status in node_status.values()
    )
    artifact_types = {item["artifact_type"] for item in final["artifact_refs"]}
    assert {
        "PLANNER_RESULT",
        "EVALUATION_CASE",
        "FINANCE_FACTS",
        "FINANCE_ASSESSMENT",
        "OPERATIONS_FACTS",
        "OPERATIONS_ASSESSMENT",
        "RISK_PRE_SCAN",
        "APPROVAL_CHECKPOINTS",
        "RISK_RULE_EVALUATION",
        "INITIAL_RISK_ASSESSMENT",
        "DECISION_ROUTE_PLAN",
        "BANKING_DISCOVERY_REQUEST",
        "BANKING_OPTION_MATRIX",
        "BANKING_DISCOVERY_RESULT",
        "BANKING_OPTION_ADVICE",
        "BANKING_INPUT_SUPPLEMENT",
        "BANKING_PRECHECK_READINESS",
        "DECISION_POST_BANKING_REVIEW",
        "BANKING_PRECHECK_SUBMISSION_PROPOSAL",
        "BANKING_PRECHECK_RESULT_SET",
        "DECISION_POST_PRECHECK_REVIEW",
        "DOCUMENT_PREPARATION_REQUEST",
        "DOCUMENT_CHECKLIST",
        "DOCUMENT_PACKAGE_DRAFT",
        "DOCUMENT_EVIDENCE_SUPPLEMENT",
        "DOCUMENT_RELEASE_PACKAGE",
        "INTERNAL_DECISION_PACKAGE",
    }.issubset(artifact_types)
    final_artifacts = workflow_client.get(f"/api/cases/{case_id}/artifacts").json()
    requests = [
        item
        for item in final_artifacts
        if item["artifact_type"] == "BANKING_DISCOVERY_REQUEST"
    ]
    matrices = sorted(
        (
            item
            for item in final_artifacts
            if item["artifact_type"] == "BANKING_OPTION_MATRIX"
        ),
        key=lambda item: item["version"],
    )
    assert len(requests) == 1
    assert requests[0]["payload"]["requested_amount"] is None
    assert [item["version"] for item in matrices] == [1, 2]
    assert matrices[0]["payload"]["requested_amount"] is None
    assert matrices[1]["payload"]["requested_amount"] == BANKING_TEST_AMOUNT
    resumed_minimum = next(
        item
        for item in matrices[1]["payload"]["candidates"][0]["criteria"]
        if item["code"] == "MINIMUM_AMOUNT"
    )
    assert resumed_minimum["status"] == "PASS"
    assert matrices[1]["payload"]["data_gaps"] == []

    exact_retry = workflow_client.post(
        f"/api/cases/{case_id}/banking/input-supplements",
        json={
            "workflow_run_id": paused["workflow_run_id"],
            "missing_request_id": paused["pending_missing_data_ids"][0],
            "requested_amount": BANKING_TEST_AMOUNT,
            "requested_amount_currency": "VND",
            "evidence_note": BANKING_EVIDENCE_NOTE,
        },
    )
    assert exact_retry.status_code == 202
    assert exact_retry.json()["supplement"]["supplement_id"] == accepted["supplement"][
        "supplement_id"
    ]
    after_retry = workflow_client.get(f"/api/cases/{case_id}/artifacts").json()
    assert sum(
        item["artifact_type"] == "BANKING_INPUT_SUPPLEMENT"
        for item in after_retry
    ) == 1
    assert sum(
        item["artifact_type"] == "BANKING_OPTION_MATRIX" for item in after_retry
    ) == 2
    assert sum(
        item["artifact_type"] == "BANKING_PRECHECK_SUBMISSION_PROPOSAL"
        for item in after_retry
    ) == 1
    approval_requests = workflow_client.get(
        f"/api/cases/{case_id}/approval-requests"
    ).json()
    assert any(
        item["command"]["action_type"] == "SUBMIT_BANKING_PRECHECK"
        and item["status"] == "APPROVED"
        for item in approval_requests
    )
    assert not any(
        item["command"]["action_type"]
        == "SEND_DOCUMENT_TO_EXTERNAL_PARTNER"
        for item in approval_requests
    )
    events = workflow_client.get(
        f"/api/workflows/{paused['workflow_run_id']}/events"
    ).json()
    assert [item["event_type"] for item in events].count(
        "BANKING_INPUT_SUPPLEMENT_ACCEPTED"
    ) == 1
    assert [item["event_type"] for item in events].count(
        "APPROVAL_REQUESTED"
    ) == 1
    assert "DOCUMENT_RELEASE_PACKAGE_READY" in {
        item["event_type"] for item in events
    }
    assert not {
        "DOCUMENT_EXTERNAL_RELEASE_PROPOSAL",
        "DOCUMENT_EXTERNAL_RELEASE_AUTHORIZED",
        "DOCUMENT_EXTERNAL_RELEASE_DECLINED",
    }.intersection(item["event_type"] for item in events)
    assert compute_sha256(TEAM_PACK) == before


def test_duplicate_start_reuses_workflow_and_does_not_repeat_nodes(
    workflow_client: TestClient,
) -> None:
    first = start(workflow_client, "CON-005")
    final = wait_for_terminal(workflow_client, str(first["workflow_run_id"]))
    second = start(workflow_client, "CON-005")

    assert second["workflow_run_id"] == first["workflow_run_id"]
    assert second["status"] == "COMPLETED"
    nodes = {item["node"]: item for item in final["nodes"]}
    assert nodes["PLANNER_INTAKE"]["attempt"] == 1
    assert nodes["FINANCE_ASSESSMENT"]["attempt"] == 1
    assert nodes["OPERATIONS_ASSESSMENT"]["attempt"] == 1
    assert nodes["INITIAL_RISK_PRE_SCAN"]["attempt"] == 1
    assert nodes["INITIAL_RISK_FINALIZATION"]["attempt"] == 1
    assert nodes["DECISION_ROUTE_PLANNING"]["attempt"] == 1
    events = workflow_client.get(
        f"/api/workflows/{first['workflow_run_id']}/events"
    ).json()
    assert [item["event_type"] for item in events].count("WORKFLOW_CREATED") == 1
    assert [item["event_type"] for item in events].count("WORKFLOW_COMPLETED") == 1
    dependency_waits = [
        item
        for item in events
        if item["event_type"] == "NODE_WAITING"
        and item["node"] == "INITIAL_RISK_FINALIZATION"
    ]
    assert len(dependency_waits) == 1
    assert dependency_waits[0]["metadata"]["waiting_for"] == [
        "FINANCE_FACTS",
        "OPERATIONS_FACTS",
    ]


def test_duplicate_banking_start_reuses_matrix_advice_and_node_attempt(
    workflow_client: TestClient,
) -> None:
    first = start(workflow_client, "CON-004")
    terminal = wait_for_terminal(workflow_client, str(first["workflow_run_id"]))
    final = complete_banking_pause_if_required(workflow_client, terminal)
    attempts_before = {
        item["node"]: item["attempt"] for item in final["nodes"]
    }
    artifact_refs_before = final["artifact_refs"]
    second = start(workflow_client, "CON-004")

    assert second["workflow_run_id"] == first["workflow_run_id"]
    assert second["status"] == "COMPLETED"
    after = workflow_client.get(
        f"/api/workflows/{first['workflow_run_id']}"
    ).json()
    assert {
        item["node"]: item["attempt"] for item in after["nodes"]
    } == attempts_before
    assert after["artifact_refs"] == artifact_refs_before
    artifact_types = [item["artifact_type"] for item in final["artifact_refs"]]
    assert artifact_types.count("BANKING_DISCOVERY_REQUEST") == 1
    assert artifact_types.count("BANKING_OPTION_MATRIX") == 2
    assert artifact_types.count("BANKING_DISCOVERY_RESULT") == 2
    assert artifact_types.count("BANKING_OPTION_ADVICE") == 2
    assert artifact_types.count("BANKING_PRECHECK_READINESS") == 2
    assert artifact_types.count("DECISION_POST_BANKING_REVIEW") == 2
    assert artifact_types.count("BANKING_INPUT_SUPPLEMENT") == 1
    assert artifact_types.count("BANKING_PRECHECK_SUBMISSION_PROPOSAL") == 1


def test_nonexistent_contract_waits_for_input_without_starting_downstream(
    workflow_client: TestClient,
) -> None:
    created = start(workflow_client, "CON-NOT-PRESENT")
    waiting = wait_for_terminal(workflow_client, str(created["workflow_run_id"]))

    assert waiting["status"] == "WAITING_FOR_INPUT"
    assert waiting["current_stage"] == "PLANNER_INTAKE"
    assert waiting["pending_missing_data_ids"]
    assert [item["node"] for item in waiting["nodes"]] == ["PLANNER_INTAKE"]
    assert waiting["nodes"][0]["status"] == "WAITING_FOR_INPUT"


def test_event_cursor_scope_validation_and_resume_conflict(
    workflow_client: TestClient,
) -> None:
    created = start(workflow_client, "CON-003")
    final = wait_for_terminal(workflow_client, str(created["workflow_run_id"]))
    workflow_id = str(created["workflow_run_id"])
    events = workflow_client.get(f"/api/workflows/{workflow_id}/events").json()
    cursor = events[len(events) // 2]["sequence"]
    after = workflow_client.get(
        f"/api/workflows/{workflow_id}/events?after_sequence={cursor}"
    ).json()

    assert final["status"] == "COMPLETED"
    assert after
    assert all(item["sequence"] > cursor for item in after)
    assert workflow_client.post(f"/api/workflows/{workflow_id}/resume").status_code == 409
    invalid_scope = workflow_client.post(
        "/api/cases/run",
        json={"contract_id": "CON-003", "evaluation_scope": ["FINANCE"]},
    )
    assert invalid_scope.status_code == 422


def test_every_contract_can_complete_through_the_automatic_workflow(
    workflow_client: TestClient,
) -> None:
    contract_ids = workflow_client.get("/api/contracts").json()["contract_ids"]

    for contract_id in contract_ids:
        created = start(workflow_client, contract_id)
        terminal = wait_for_terminal(
            workflow_client, str(created["workflow_run_id"])
        )
        final = complete_banking_pause_if_required(workflow_client, terminal)
        assert final["status"] == "COMPLETED"


def test_swagger_exposes_each_workflow_route_once(workflow_client: TestClient) -> None:
    paths = workflow_client.get("/openapi.json").json()["paths"]
    methods = {
        "/api/cases/run": "post",
        "/api/workflows/{workflow_run_id}": "get",
        "/api/workflows/{workflow_run_id}/resume": "post",
        "/api/workflows/{workflow_run_id}/events": "get",
    }

    for path, method in methods.items():
        assert path in paths
        assert list(paths[path]) == [method]
        assert paths[path][method]["tags"] == ["Workflow"]


def test_pending_workflow_recovers_after_runtime_restart(
    tmp_path: Path,
) -> None:
    dataset_id = "WORKFLOW_RESTART_TEST"
    database_path = tmp_path / "workflow-restart.db"
    async def snapshot_hash() -> str:
        datasets = InMemoryDatasetRepository()
        snapshot = await ExcelDatasetIngestion(datasets).ingest(
            dataset_id=dataset_id,
            workbook_path=TEAM_PACK,
        )
        return snapshot.snapshot_hash

    active_snapshot_hash = asyncio.run(snapshot_hash())
    now = datetime.now(UTC)
    seeded = CaseWorkflowRun(
        workflow_run_id="CWF-RECOVERY-TEST",
        dataset_id=dataset_id,
        dataset_snapshot_hash=active_snapshot_hash,
        contract_id="CON-004",
        status=WorkflowStatus.PENDING,
        current_stage=WorkflowNode.PLANNER_INTAKE.value,
        requested_scope=(
            EvaluationScope.FINANCE,
            EvaluationScope.OPERATIONS,
            EvaluationScope.RISK,
        ),
        as_of_date=datetime(2026, 7, 16).date(),
        created_at=now,
        updated_at=now,
    )

    async def seed() -> None:
        database = SQLiteDatabase(database_path)
        await database.initialize()
        await SQLiteCaseWorkflowRepository(database).save_run(seeded)
        await database.close()

    asyncio.run(seed())
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
            terminal = wait_for_terminal(client, seeded.workflow_run_id)
            completed = complete_banking_pause_if_required(client, terminal)
            assert completed["status"] == "COMPLETED"
            assert completed["current_stage"] == (
                "INTERNAL_DECISION_PACKAGE_READY"
            )
            assert completed["banking_precheck_result_set_id"]
            assert completed["decision_post_precheck_review_id"]
            assert completed["banking_precheck_execution_mode"] == "SIMULATED"
            assert completed["banking_precheck_external_bank_submission"] is False
            assert completed["banking_precheck_bank_approval_obtained"] is False
            artifact_ids = {
                item["artifact_id"] for item in completed["artifact_refs"]
            }

        with TestClient(
            create_app(
                workbook_path=TEAM_PACK,
                dataset_id=dataset_id,
                database_path=database_path,
            )
        ) as restarted:
            restored = restarted.get(
                f"/api/workflows/{seeded.workflow_run_id}"
            ).json()
            assert restored["status"] == "COMPLETED"
            assert {
                item["artifact_id"] for item in restored["artifact_refs"]
            } == artifact_ids
    finally:
        patcher.undo()
