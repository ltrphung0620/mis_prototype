"""Run Dataset Ingestion and Planner Intake through the workflow layer."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from pydantic import ValidationError

from opc_mis.business.skills.planner.component import PlannerSkill
from opc_mis.domain.components import ExecutionContext
from opc_mis.domain.enums import ComponentStatus, EvaluationScope, WorkflowStatus
from opc_mis.domain.lineage import deterministic_id
from opc_mis.domain.planner_models import PlannerExecutionResult
from opc_mis.domain.workflow import WorkflowNode
from opc_mis.infrastructure.excel.dataset_adapter import ExcelDatasetIngestion
from opc_mis.infrastructure.excel.overlay_store import PatchApplicationError
from opc_mis.infrastructure.excel.workbook_loader import WorkbookError
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

EXIT_COMPLETED = 0
EXIT_WAITING_FOR_INPUT = 2
EXIT_FAILED_SAFE = 3
EXIT_INVALID_REQUEST = 4


def build_parser() -> argparse.ArgumentParser:
    """Build the standalone Planner workflow CLI parser."""
    parser = argparse.ArgumentParser(description="Run OPC MIS Planner Intake workflow")
    parser.add_argument("--workbook", required=True, type=Path)
    parser.add_argument("--contract", required=True)
    parser.add_argument(
        "--scope",
        required=True,
        nargs="+",
        choices=[scope.value for scope in EvaluationScope],
    )
    parser.add_argument("--dataset-id", default="MISTalent2026_OPC_AgenticAI_TeamPack_v3")
    return parser


def _error_result(message: str) -> PlannerExecutionResult:
    return PlannerExecutionResult(
        status=WorkflowStatus.FAILED_SAFE,
        component_status=ComponentStatus.FAILED_SAFE,
        current_node=WorkflowNode.DATASET_INGESTION.value,
        planner_result=None,
        generated_artifacts=(),
        validation_errors=(message,),
    )


async def _run(args: argparse.Namespace) -> PlannerExecutionResult:
    dataset_repository = InMemoryDatasetRepository()
    artifact_repository = InMemoryArtifactRepository()
    workflow_repository = InMemoryWorkflowStateRepository()
    ingestion = ExcelDatasetIngestion(dataset_repository)
    snapshot = await ingestion.ingest(
        dataset_id=args.dataset_id,
        workbook_path=args.workbook,
    )
    context = ExecutionContext(
        dataset_id=args.dataset_id,
        workflow_run_id=deterministic_id(
            "RUN",
            args.dataset_id,
            snapshot.snapshot_hash,
            args.contract,
            args.scope,
        ),
        input_artifact_ids=(deterministic_id("DSNAP", args.dataset_id, snapshot.snapshot_hash),),
        requested_scope=tuple(args.scope),
        component_input={"contract_id": args.contract},
        current_node=WorkflowNode.PLANNER_INTAKE.value,
    )
    orchestrator = PlannerIntakeOrchestrator(
        planner=PlannerSkill(dataset_port=dataset_repository),
        artifact_repository=artifact_repository,
        workflow_repository=workflow_repository,
    )
    return await orchestrator.run_planner(context)


def main(argv: list[str] | None = None) -> int:
    """Execute Planner Intake and map workflow outcomes to documented exit codes."""
    args = build_parser().parse_args(argv)
    try:
        result = asyncio.run(_run(args))
    except ValidationError as exc:
        print(_error_result(str(exc)).model_dump_json(indent=2))
        return EXIT_INVALID_REQUEST
    except (WorkbookError, PatchApplicationError, OSError) as exc:
        print(_error_result(str(exc)).model_dump_json(indent=2))
        return EXIT_FAILED_SAFE

    print(result.model_dump_json(indent=2))
    if result.status is WorkflowStatus.COMPLETED:
        return EXIT_COMPLETED
    if result.status is WorkflowStatus.WAITING_FOR_INPUT:
        return EXIT_WAITING_FOR_INPUT
    return EXIT_FAILED_SAFE


if __name__ == "__main__":
    sys.exit(main())
