"""Durable adapters for legacy workflow state and Master Workflow state."""

import sqlite3

from opc_mis.domain.case_workflow_models import CaseWorkflowRun, WorkflowNodeState
from opc_mis.domain.enums import WorkflowStatus
from opc_mis.domain.workflow import WorkflowRunState
from opc_mis.infrastructure.persistence.sqlite_database import SQLiteDatabase


class SQLiteWorkflowStateRepository:
    """Persist the existing per-component workflow state contract."""

    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database

    async def save(self, state: WorkflowRunState) -> None:
        def operation(connection: sqlite3.Connection) -> None:
            connection.execute(
                """
                INSERT INTO workflow_states(workflow_run_id, model_json) VALUES (?, ?)
                ON CONFLICT(workflow_run_id) DO UPDATE SET model_json = excluded.model_json
                """,
                (state.workflow_run_id, state.model_dump_json()),
            )

        await self._database.run(operation)

    async def get(self, workflow_run_id: str) -> WorkflowRunState | None:
        def operation(connection: sqlite3.Connection) -> str | None:
            row = connection.execute(
                "SELECT model_json FROM workflow_states WHERE workflow_run_id = ?",
                (workflow_run_id,),
            ).fetchone()
            return None if row is None else str(row["model_json"])

        encoded = await self._database.run(operation)
        return None if encoded is None else WorkflowRunState.model_validate_json(encoded)


class SQLiteCaseWorkflowRepository:
    """Persist automatic workflow runs and one state record per node."""

    _RECOVERABLE = (WorkflowStatus.PENDING.value, WorkflowStatus.RUNNING.value)

    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database

    async def save_run(self, run: CaseWorkflowRun) -> None:
        def operation(connection: sqlite3.Connection) -> None:
            connection.execute(
                """
                INSERT INTO case_workflow_runs(workflow_run_id, status, model_json)
                VALUES (?, ?, ?)
                ON CONFLICT(workflow_run_id) DO UPDATE SET
                    status = excluded.status,
                    model_json = excluded.model_json
                """,
                (run.workflow_run_id, run.status.value, run.model_dump_json()),
            )

        await self._database.run(operation)

    async def get_run(self, workflow_run_id: str) -> CaseWorkflowRun | None:
        def operation(connection: sqlite3.Connection) -> str | None:
            row = connection.execute(
                "SELECT model_json FROM case_workflow_runs WHERE workflow_run_id = ?",
                (workflow_run_id,),
            ).fetchone()
            return None if row is None else str(row["model_json"])

        encoded = await self._database.run(operation)
        return None if encoded is None else CaseWorkflowRun.model_validate_json(encoded)

    async def list_recoverable(
        self, dataset_id: str, dataset_snapshot_hash: str
    ) -> tuple[CaseWorkflowRun, ...]:
        def operation(connection: sqlite3.Connection) -> tuple[str, ...]:
            rows = connection.execute(
                """
                SELECT model_json FROM case_workflow_runs
                WHERE status IN (?, ?) ORDER BY workflow_run_id
                """,
                self._RECOVERABLE,
            ).fetchall()
            return tuple(str(row["model_json"]) for row in rows)

        encoded = await self._database.run(operation)
        runs = tuple(CaseWorkflowRun.model_validate_json(item) for item in encoded)
        return tuple(
            run
            for run in runs
            if run.dataset_id == dataset_id
            and run.dataset_snapshot_hash == dataset_snapshot_hash
        )

    async def save_node(self, node: WorkflowNodeState) -> None:
        def operation(connection: sqlite3.Connection) -> None:
            connection.execute(
                """
                INSERT INTO workflow_node_states(workflow_run_id, node, model_json)
                VALUES (?, ?, ?)
                ON CONFLICT(workflow_run_id, node) DO UPDATE SET
                    model_json = excluded.model_json
                """,
                (node.workflow_run_id, node.node.value, node.model_dump_json()),
            )

        await self._database.run(operation)

    async def get_node(
        self, workflow_run_id: str, node: str
    ) -> WorkflowNodeState | None:
        def operation(connection: sqlite3.Connection) -> str | None:
            row = connection.execute(
                """
                SELECT model_json FROM workflow_node_states
                WHERE workflow_run_id = ? AND node = ?
                """,
                (workflow_run_id, node),
            ).fetchone()
            return None if row is None else str(row["model_json"])

        encoded = await self._database.run(operation)
        return None if encoded is None else WorkflowNodeState.model_validate_json(encoded)

    async def list_nodes(self, workflow_run_id: str) -> tuple[WorkflowNodeState, ...]:
        def operation(connection: sqlite3.Connection) -> tuple[str, ...]:
            rows = connection.execute(
                """
                SELECT model_json FROM workflow_node_states
                WHERE workflow_run_id = ? ORDER BY rowid
                """,
                (workflow_run_id,),
            ).fetchall()
            return tuple(str(row["model_json"]) for row in rows)

        encoded = await self._database.run(operation)
        return tuple(WorkflowNodeState.model_validate_json(item) for item in encoded)
