"""Workbook immutability, generic boundaries, and source-code safety tests."""

from pathlib import Path

from opc_mis.domain.enums import WorkflowStatus
from opc_mis.infrastructure.excel.workbook_loader import compute_sha256
from tests.conftest import execute_planner, make_request


def test_workbook_hash_is_unchanged_after_planner(
    team_pack_path: Path, first_contract_id: str
) -> None:
    before = compute_sha256(team_pack_path)
    result = execute_planner(make_request(team_pack_path, first_contract_id))
    after = compute_sha256(team_pack_path)

    assert result.status is WorkflowStatus.COMPLETED
    assert before == after


def test_con005_is_not_blocked_by_supplier_confirmation(team_pack_path: Path) -> None:
    result = execute_planner(make_request(team_pack_path, "CON-005"))

    assert result.status is WorkflowStatus.COMPLETED
    assert result.planner_result is not None
    requirement_codes = {
        item.requirement_code for item in result.planner_result.missing_data_requests
    }
    assert all("SUPPLIER" not in code for code in requirement_codes)


def test_production_source_has_no_demo_contract_ids_or_excel_row_constants() -> None:
    source_files = list(Path("src").rglob("*.py"))
    source = "\n".join(path.read_text(encoding="utf-8") for path in source_files)

    assert "CON-004" not in source
    assert "CON-005" not in source
    assert "min_row=" not in source
    assert "max_row=" not in source
