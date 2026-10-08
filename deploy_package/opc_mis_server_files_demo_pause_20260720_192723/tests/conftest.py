"""Shared fixtures and workflow harness for Planner tests."""

import asyncio
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import pytest

from opc_mis.business.skills.planner.component import PlannerSkill
from opc_mis.domain.components import ExecutionContext
from opc_mis.domain.enums import EvaluationScope
from opc_mis.domain.evidence import DataPatch
from opc_mis.domain.lineage import deterministic_id
from opc_mis.domain.planner_models import PlannerExecutionResult
from opc_mis.domain.workflow import WorkflowNode
from opc_mis.governance.evidence_validator import EvidenceValidator
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


@dataclass(frozen=True)
class PlannerScenario:
    """Interface-layer input used to assemble an isolated Planner workflow run."""

    workbook_path: Path
    dataset_id: str
    contract_id: str
    scopes: tuple[EvaluationScope, ...]
    data_patches: tuple[DataPatch, ...]


@pytest.fixture
def team_pack_path() -> Path:
    return Path("data/input/MISTalent2026_OPC_AgenticAI_TeamPack_v3.xlsx").resolve()


@pytest.fixture
def first_contract_id(team_pack_path: Path) -> str:
    frame = pd.read_excel(team_pack_path, sheet_name="04_CONTRACTS", dtype=object)
    return str(frame.loc[0, "contract_id"])


def make_request(
    workbook_path: Path,
    contract_id: str,
    scopes: tuple[EvaluationScope, ...] = (
        EvaluationScope.FINANCE,
        EvaluationScope.OPERATIONS,
        EvaluationScope.RISK,
    ),
    *,
    data_patches: tuple[DataPatch, ...] = (),
) -> PlannerScenario:
    return PlannerScenario(
        workbook_path=workbook_path,
        dataset_id="TEAM_PACK_TEST",
        contract_id=contract_id,
        scopes=scopes,
        data_patches=data_patches,
    )


def execute_planner(
    scenario: PlannerScenario,
    *,
    artifact_repository: InMemoryArtifactRepository | None = None,
    evidence_validator: EvidenceValidator | None = None,
) -> PlannerExecutionResult:
    """Run ingestion and Planner through the same Orchestrator used by the CLI."""

    async def execute() -> PlannerExecutionResult:
        dataset_repository = InMemoryDatasetRepository()
        artifacts = artifact_repository or InMemoryArtifactRepository()
        snapshot = await ExcelDatasetIngestion(dataset_repository).ingest(
            dataset_id=scenario.dataset_id,
            workbook_path=scenario.workbook_path,
            patches=scenario.data_patches,
        )
        context = ExecutionContext(
            dataset_id=scenario.dataset_id,
            workflow_run_id=deterministic_id(
                "RUN",
                scenario.dataset_id,
                snapshot.snapshot_hash,
                scenario.contract_id,
                scenario.scopes,
            ),
            input_artifact_ids=(
                deterministic_id("DSNAP", scenario.dataset_id, snapshot.snapshot_hash),
            ),
            requested_scope=scenario.scopes,
            component_input={"contract_id": scenario.contract_id},
            current_node=WorkflowNode.PLANNER_INTAKE.value,
        )
        orchestrator = PlannerIntakeOrchestrator(
            planner=PlannerSkill(dataset_port=dataset_repository),
            artifact_repository=artifacts,
            workflow_repository=InMemoryWorkflowStateRepository(),
            evidence_validator=evidence_validator,
        )
        return await orchestrator.run_planner(context)

    return asyncio.run(execute())
