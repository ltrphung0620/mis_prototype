"""Unit tests for ordered durable workflow events and recovery filtering."""

import asyncio
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from opc_mis.domain.case_workflow_models import CaseWorkflowRun
from opc_mis.domain.enums import EvaluationScope, WorkflowStatus
from opc_mis.domain.workflow import WorkflowNode
from opc_mis.infrastructure.persistence.sqlite_database import SQLiteDatabase
from opc_mis.infrastructure.persistence.sqlite_runtime_event_repository import (
    SQLiteRuntimeEventRepository,
)
from opc_mis.infrastructure.persistence.sqlite_workflow_repository import (
    SQLiteCaseWorkflowRepository,
)


def test_event_sequence_is_monotonic_under_concurrent_append(tmp_path: Path) -> None:
    async def execute() -> None:
        database = SQLiteDatabase(tmp_path / "events.db")
        await database.initialize()
        repository = SQLiteRuntimeEventRepository(database)
        now = datetime.now(UTC)
        await asyncio.gather(
            *(
                repository.append(
                    workflow_run_id="RUN-TEST",
                    event_type="NODE_STARTED",
                    node=WorkflowNode.PLANNER_INTAKE,
                    metadata={"worker": index},
                    created_at=now,
                )
                for index in range(20)
            )
        )
        events = await repository.list_after("RUN-TEST", 0)
        await database.close()

        assert tuple(item.sequence for item in events) == tuple(range(1, 21))
        assert len({item.event_id for item in events}) == 20

    asyncio.run(execute())


def test_recovery_returns_only_active_dataset_snapshot(tmp_path: Path) -> None:
    async def execute() -> None:
        database = SQLiteDatabase(tmp_path / "recovery.db")
        await database.initialize()
        repository = SQLiteCaseWorkflowRepository(database)
        now = datetime.now(UTC)
        for run_id, dataset_id, snapshot_hash in (
            ("RUN-MATCH", "DATASET-A", "HASH-A"),
            ("RUN-OTHER-DATASET", "DATASET-B", "HASH-A"),
            ("RUN-OLD-SNAPSHOT", "DATASET-A", "HASH-OLD"),
        ):
            await repository.save_run(
                CaseWorkflowRun(
                    workflow_run_id=run_id,
                    dataset_id=dataset_id,
                    dataset_snapshot_hash=snapshot_hash,
                    contract_id="CONTRACT",
                    status=WorkflowStatus.PENDING,
                    current_stage=WorkflowNode.PLANNER_INTAKE.value,
                    requested_scope=(
                        EvaluationScope.FINANCE,
                        EvaluationScope.OPERATIONS,
                        EvaluationScope.RISK,
                    ),
                    created_at=now,
                    updated_at=now,
                )
            )
        recovered = await repository.list_recoverable("DATASET-A", "HASH-A")
        await database.close()

        assert tuple(item.workflow_run_id for item in recovered) == ("RUN-MATCH",)

    asyncio.run(execute())


def test_run_request_id_persists_and_legacy_run_json_remains_readable(
    tmp_path: Path,
) -> None:
    async def execute() -> None:
        database = SQLiteDatabase(tmp_path / "run-request-id.db")
        await database.initialize()
        repository = SQLiteCaseWorkflowRepository(database)
        now = datetime.now(UTC)
        base = CaseWorkflowRun(
            workflow_run_id="RUN-LEGACY",
            dataset_id="DATASET-A",
            dataset_snapshot_hash="HASH-A",
            contract_id="CONTRACT",
            status=WorkflowStatus.PENDING,
            current_stage=WorkflowNode.PLANNER_INTAKE.value,
            requested_scope=(
                EvaluationScope.FINANCE,
                EvaluationScope.OPERATIONS,
                EvaluationScope.RISK,
            ),
            created_at=now,
            updated_at=now,
        )

        def insert_legacy(connection: sqlite3.Connection) -> None:
            connection.execute(
                """
                INSERT INTO case_workflow_runs(workflow_run_id, status, model_json)
                VALUES (?, ?, ?)
                """,
                (
                    base.workflow_run_id,
                    base.status.value,
                    base.model_dump_json(exclude={"run_request_id"}),
                ),
            )

        await database.run(insert_legacy)
        legacy = await repository.get_run("RUN-LEGACY")
        assert legacy is not None
        assert legacy.run_request_id is None

        current = base.model_copy(
            update={
                "workflow_run_id": "RUN-CURRENT",
                "run_request_id": "RUN-REQUEST-0001",
            }
        )
        await repository.save_run(current)
        persisted = await repository.get_run("RUN-CURRENT")
        await database.close()

        assert persisted is not None
        assert persisted.run_request_id == "RUN-REQUEST-0001"

    asyncio.run(execute())
