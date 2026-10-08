"""Unit tests for exact relationship resolution and Planner boundaries."""

from pathlib import Path

import pandas as pd

from opc_mis.domain.enums import RunTaskType, WorkflowStatus
from tests.conftest import execute_planner, make_request


def test_case_uses_exact_contract_order_and_invoice_relationships(
    team_pack_path: Path, first_contract_id: str
) -> None:
    orders = pd.read_excel(team_pack_path, sheet_name="06_ORDERS", dtype=object)
    invoices = pd.read_excel(team_pack_path, sheet_name="07_INVOICES", dtype=object)
    expected_orders = tuple(
        orders.loc[orders["contract_id"] == first_contract_id, "order_id"].astype(str)
    )
    expected_invoices = tuple(
        invoices.loc[invoices["order_id"].isin(expected_orders), "invoice_id"].astype(str)
    )

    result = execute_planner(make_request(team_pack_path, first_contract_id))

    assert result.status is WorkflowStatus.COMPLETED
    assert result.planner_result is not None
    case = result.planner_result.evaluation_case
    assert case is not None
    assert case.related_order_ids == expected_orders
    assert case.related_invoice_ids == expected_invoices


def test_initial_plan_contains_only_three_executable_tasks(
    team_pack_path: Path, first_contract_id: str
) -> None:
    result = execute_planner(make_request(team_pack_path, first_contract_id))
    assert result.planner_result is not None
    plan = result.planner_result.run_plan

    assert plan.parallel_initial_tasks == (
        RunTaskType.FINANCE_ASSESSMENT,
        RunTaskType.OPERATIONS_ASSESSMENT,
        RunTaskType.INITIAL_RISK_SCAN,
    )
    assert not hasattr(plan, "deferred_tasks")


def test_planner_result_contains_no_approval_request_type(
    team_pack_path: Path, first_contract_id: str
) -> None:
    result = execute_planner(make_request(team_pack_path, first_contract_id))

    assert "ApprovalRequest" not in result.model_dump_json()
    assert "supplier confirmation" not in result.model_dump_json().lower()


def test_execution_is_deterministic(team_pack_path: Path, first_contract_id: str) -> None:
    request = make_request(team_pack_path, first_contract_id)

    first = execute_planner(request)
    second = execute_planner(request)

    assert first.planner_result == second.planner_result
    assert [artifact.artifact_id for artifact in first.generated_artifacts] == [
        artifact.artifact_id for artifact in second.generated_artifacts
    ]


def test_scope_order_and_path_spelling_do_not_change_artifact_identity(
    team_pack_path: Path, first_contract_id: str
) -> None:
    relative_path = Path("data/input/MISTalent2026_OPC_AgenticAI_TeamPack_v3.xlsx")
    first_request = make_request(
        relative_path,
        first_contract_id,
        scopes=("RISK", "FINANCE", "OPERATIONS"),
    )
    second_request = make_request(team_pack_path, first_contract_id)

    first = execute_planner(first_request)
    second = execute_planner(second_request)

    assert first.planner_result is not None
    assert second.planner_result is not None
    assert first.planner_result.evaluation_case is not None
    assert second.planner_result.evaluation_case is not None
    assert (
        first.planner_result.evaluation_case.evaluation_case_id
        == second.planner_result.evaluation_case.evaluation_case_id
    )
    assert [artifact.artifact_id for artifact in first.generated_artifacts] == [
        artifact.artifact_id for artifact in second.generated_artifacts
    ]
    assert [artifact.input_hash for artifact in first.generated_artifacts] == [
        artifact.input_hash for artifact in second.generated_artifacts
    ]
