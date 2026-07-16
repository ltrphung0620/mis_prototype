"""Unit tests for isolated in-memory data patches."""

from pathlib import Path

from opc_mis.domain.enums import SourceType
from opc_mis.domain.evidence import DataPatch
from opc_mis.domain.lineage import LineageFactory
from opc_mis.domain.team_pack import SheetRegistry
from opc_mis.infrastructure.excel.overlay_store import OverlayStore
from opc_mis.infrastructure.excel.workbook_loader import WorkbookLoader, compute_sha256
from tests.conftest import execute_planner, make_request


def test_patch_changes_only_the_overlay(team_pack_path: Path, first_contract_id: str) -> None:
    before_hash = compute_sha256(team_pack_path)
    dataset = WorkbookLoader().load("DATASET", team_pack_path)
    original = dataset.lookup(SheetRegistry.CONTRACTS, first_contract_id)[0]
    original_status = original.values["status"]
    patch = DataPatch(
        patch_id="PATCH-STATUS",
        source=SourceType.USER_INPUT,
        canonical_entity_type="CONTRACT",
        target_record=first_contract_id,
        field="status",
        value=" User supplied status ",
        evidence_note="Unit test patch",
    )

    overlaid = OverlayStore().apply(
        dataset,
        (patch,),
        LineageFactory("DATASET", dataset.workbook_hash),
    )
    patched = overlaid.lookup(SheetRegistry.CONTRACTS, first_contract_id)[0]

    assert patched.values["status"] == "User supplied status"
    assert patched.patched_evidence["status"].source_type is SourceType.USER_INPUT
    assert original.values["status"] == original_status
    assert compute_sha256(team_pack_path) == before_hash


def test_selected_patch_is_present_in_case_lineage(
    team_pack_path: Path, first_contract_id: str
) -> None:
    patch = DataPatch(
        patch_id="PATCH-CASE-STATUS",
        source=SourceType.USER_INPUT,
        canonical_entity_type="CONTRACT",
        target_record=first_contract_id,
        field="status",
        value="User supplied status",
        evidence_note="Verify case lineage",
    )

    result = execute_planner(make_request(team_pack_path, first_contract_id, data_patches=(patch,)))

    assert result.planner_result is not None
    case = result.planner_result.evaluation_case
    assert case is not None
    assert any(
        evidence.source_type is SourceType.USER_INPUT
        and evidence.record_id == first_contract_id
        and evidence.field == "status"
        for evidence in case.evidence_refs
    )
