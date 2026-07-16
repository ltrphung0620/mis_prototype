"""Architecture tests for the refactored Planner intake slice."""

import asyncio
from pathlib import Path

from opc_mis.business.skills.planner.component import PlannerSkill
from opc_mis.domain.artifacts import ArtifactDraft
from opc_mis.domain.components import ExecutionContext
from opc_mis.domain.enums import (
    ComponentStatus,
    EvaluationScope,
    ValidationStatus,
    WorkflowStatus,
)
from opc_mis.domain.lineage import deterministic_id
from opc_mis.domain.missing_data import MissingDataRequest
from opc_mis.domain.validation_reports import ValidationReport
from opc_mis.domain.workflow import WorkflowNode
from opc_mis.infrastructure.excel.dataset_adapter import ExcelDatasetIngestion
from opc_mis.infrastructure.persistence.memory_artifact_repository import (
    InMemoryArtifactRepository,
)
from opc_mis.infrastructure.persistence.memory_dataset_repository import (
    InMemoryDatasetRepository,
)
from opc_mis.infrastructure.persistence.memory_workflow_repository import (
    InMemoryWorkflowStateRepository,
)
from opc_mis.workflow.orchestrator import PlannerIntakeOrchestrator
from tests.conftest import execute_planner, make_request


async def _component_runtime(
    workbook_path: Path, contract_id: str
) -> tuple[PlannerSkill, ExecutionContext]:
    datasets = InMemoryDatasetRepository()
    snapshot = await ExcelDatasetIngestion(datasets).ingest(
        dataset_id="ARCHITECTURE_TEST",
        workbook_path=workbook_path,
    )
    context = ExecutionContext(
        dataset_id=snapshot.dataset_id,
        workflow_run_id="RUN-ARCHITECTURE-TEST",
        input_artifact_ids=(
            deterministic_id("DSNAP", snapshot.dataset_id, snapshot.snapshot_hash),
        ),
        requested_scope=(
            EvaluationScope.FINANCE,
            EvaluationScope.OPERATIONS,
            EvaluationScope.RISK,
        ),
        component_input={"contract_id": contract_id},
        current_node=WorkflowNode.PLANNER_INTAKE.value,
    )
    return PlannerSkill(dataset_port=datasets), context


def test_planner_returns_side_effect_free_component_result(
    team_pack_path: Path, first_contract_id: str
) -> None:
    async def execute() -> None:
        planner, context = await _component_runtime(team_pack_path, first_contract_id)
        result = await planner.execute(context)

        assert result.status in {
            ComponentStatus.COMPLETED,
            ComponentStatus.COMPLETED_WITH_WARNINGS,
        }
        assert result.approval_signals == ()
        assert result.action_commands == ()
        assert all(isinstance(artifact, ArtifactDraft) for artifact in result.artifacts)
        assert all(not hasattr(artifact, "artifact_id") for artifact in result.artifacts)

    asyncio.run(execute())


def test_planner_payload_contains_no_workflow_owned_state(
    team_pack_path: Path, first_contract_id: str
) -> None:
    result = execute_planner(make_request(team_pack_path, first_contract_id))

    assert result.planner_result is not None
    case = result.planner_result.evaluation_case
    assert case is not None
    assert "current_stage" not in type(case).model_fields
    assert "case_status" not in type(case).model_fields
    assert set(type(result.planner_result.run_plan).model_fields) == {
        "parallel_initial_tasks",
        "plan_reason",
    }
    assert "resume_node" not in MissingDataRequest.model_fields


def test_orchestrator_validates_before_artifact_persistence(
    team_pack_path: Path, first_contract_id: str
) -> None:
    class BlockingValidator:
        async def validate(self, draft: ArtifactDraft) -> ValidationReport:
            return ValidationReport(
                status=ValidationStatus.BLOCKED,
                blocking_errors=(f"Blocked {draft.artifact_type}",),
            )

    async def execute() -> None:
        planner, context = await _component_runtime(team_pack_path, first_contract_id)
        artifacts = InMemoryArtifactRepository()
        workflow = InMemoryWorkflowStateRepository()
        orchestrator = PlannerIntakeOrchestrator(
            planner=planner,
            artifact_repository=artifacts,
            workflow_repository=workflow,
            evidence_validator=BlockingValidator(),
        )

        result = await orchestrator.run_planner(context)

        assert result.status is WorkflowStatus.FAILED_SAFE
        assert result.generated_artifacts == ()
        assert await artifacts.list_by_case("ANY") == ()
        persisted = await workflow.get(context.workflow_run_id)
        assert persisted is not None
        assert persisted.status is WorkflowStatus.FAILED_SAFE

    asyncio.run(execute())


def test_orchestrator_owns_artifact_envelope_metadata(
    team_pack_path: Path, first_contract_id: str
) -> None:
    result = execute_planner(make_request(team_pack_path, first_contract_id))

    assert result.generated_artifacts
    assert all(artifact.version == 1 for artifact in result.generated_artifacts)
    assert all(artifact.input_artifact_ids for artifact in result.generated_artifacts)
    assert all(artifact.created_at.tzinfo is not None for artifact in result.generated_artifacts)
    assert all(
        artifact.validation_status in {ValidationStatus.VALID, ValidationStatus.VALID_WITH_WARNINGS}
        for artifact in result.generated_artifacts
    )


def test_orchestrator_persists_planner_pause_state(team_pack_path: Path) -> None:
    async def execute() -> None:
        planner, context = await _component_runtime(team_pack_path, "CON-NOT-PRESENT")
        workflow = InMemoryWorkflowStateRepository()
        orchestrator = PlannerIntakeOrchestrator(
            planner=planner,
            artifact_repository=InMemoryArtifactRepository(),
            workflow_repository=workflow,
        )

        result = await orchestrator.run_planner(context)
        persisted = await workflow.get(context.workflow_run_id)

        assert result.status is WorkflowStatus.WAITING_FOR_INPUT
        assert persisted is not None
        assert persisted.status is WorkflowStatus.WAITING_FOR_INPUT
        assert persisted.blocked_node == WorkflowNode.PLANNER_INTAKE.value
        assert persisted.pending_request_ids

    asyncio.run(execute())


def test_domain_and_planner_business_layers_do_not_import_adapters() -> None:
    checked = [Path("src/opc_mis/domain"), Path("src/opc_mis/business/skills/planner")]
    source = "\n".join(
        path.read_text(encoding="utf-8") for root in checked for path in root.rglob("*.py")
    )

    for forbidden in (
        "import pandas",
        "import openpyxl",
        "import fastapi",
        "import sqlite3",
        "import openai",
        "opc_mis.infrastructure",
    ):
        assert forbidden not in source
