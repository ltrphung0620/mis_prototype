"""Invalid contract behavior and CLI serialization tests."""

import json
import os
import subprocess
import sys
from pathlib import Path

from opc_mis.domain.enums import ReadinessStatus, WorkflowStatus
from opc_mis.domain.workflow import WorkflowNode
from tests.conftest import execute_planner, make_request


def test_invalid_contract_returns_blocking_missing_data_request(
    team_pack_path: Path,
) -> None:
    result = execute_planner(make_request(team_pack_path, "CON-NOT-PRESENT"))

    assert result.status is WorkflowStatus.WAITING_FOR_INPUT
    assert result.planner_result is not None
    assert result.planner_result.evaluation_case is None
    assert result.planner_result.data_readiness.status is ReadinessStatus.BLOCKED
    missing = result.planner_result.missing_data_requests
    assert any(item.requirement_code == "CONTRACT_NOT_FOUND" for item in missing)
    assert all(item.raised_by == "PLANNER_SKILL" for item in missing)
    assert result.current_node == WorkflowNode.PLANNER_INTAKE.value
    assert result.planner_result.run_plan.parallel_initial_tasks == ()


def test_cli_output_is_valid_json_and_waiting_is_handled(team_pack_path: Path) -> None:
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(Path("src").resolve())
    command = [
        sys.executable,
        "-m",
        "opc_mis.cli.run_planner",
        "--workbook",
        str(team_pack_path),
        "--contract",
        "CON-NOT-PRESENT",
        "--scope",
        "FINANCE",
        "OPERATIONS",
        "RISK",
    ]

    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )

    payload = json.loads(completed.stdout)
    assert completed.returncode == 2
    assert payload["status"] == "WAITING_FOR_INPUT"
    assert "NaN" not in completed.stdout
