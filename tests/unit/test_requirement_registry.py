"""Unit tests for scope-aware Planner requirements."""

from pathlib import Path

from opc_mis.domain.enums import EvaluationScope, SourceType, WorkflowStatus
from opc_mis.domain.evidence import DataPatch
from tests.conftest import execute_planner, make_request


def _contract_value_patch(contract_id: str) -> DataPatch:
    return DataPatch(
        patch_id="PATCH-MISSING-CONTRACT-VALUE",
        source=SourceType.USER_INPUT,
        target_sheet="04_CONTRACTS",
        target_record=contract_id,
        field="contract_value",
        value=None,
        evidence_note="Test scope-specific readiness",
    )


def test_finance_requirement_blocks_missing_contract_value(
    team_pack_path: Path, first_contract_id: str
) -> None:
    request = make_request(
        team_pack_path,
        first_contract_id,
        scopes=(EvaluationScope.FINANCE,),
        data_patches=(_contract_value_patch(first_contract_id),),
    )

    result = execute_planner(request)

    assert result.status is WorkflowStatus.WAITING_FOR_INPUT
    assert result.planner_result is not None
    codes = {item.requirement_code for item in result.planner_result.missing_data_requests}
    assert "FINANCE_CONTRACT_VALUE_REQUIRED" in codes
    assert any(
        evidence.source_type is SourceType.USER_INPUT and evidence.field == "contract_value"
        for artifact in result.generated_artifacts
        for evidence in artifact.evidence_refs
    )


def test_risk_scope_does_not_require_contract_value(
    team_pack_path: Path, first_contract_id: str
) -> None:
    request = make_request(
        team_pack_path,
        first_contract_id,
        scopes=(EvaluationScope.RISK,),
        data_patches=(_contract_value_patch(first_contract_id),),
    )

    result = execute_planner(request)

    assert result.status is WorkflowStatus.COMPLETED
    assert result.planner_result is not None
    assert not result.planner_result.missing_data_requests
