"""Append-only ordered Master Workflow events in SQLite."""

import sqlite3
from datetime import datetime
from typing import Any

from opc_mis.domain.case_workflow_models import WorkflowEvent
from opc_mis.domain.lineage import deterministic_id
from opc_mis.domain.workflow import WorkflowNode
from opc_mis.infrastructure.persistence.sqlite_database import SQLiteDatabase


class SQLiteRuntimeEventRepository:
    """Assign a monotonic per-workflow sequence inside one SQLite transaction."""

    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database

    async def append(
        self,
        *,
        workflow_run_id: str,
        event_type: str,
        node: WorkflowNode | None,
        metadata: dict[str, Any],
        created_at: datetime,
    ) -> WorkflowEvent:
        def operation(connection: sqlite3.Connection) -> WorkflowEvent:
            row = connection.execute(
                """
                SELECT COALESCE(MAX(sequence), 0) + 1 AS next_sequence
                FROM runtime_events WHERE workflow_run_id = ?
                """,
                (workflow_run_id,),
            ).fetchone()
            sequence = int(row["next_sequence"])
            event = WorkflowEvent(
                event_id=deterministic_id(
                    "EVT", workflow_run_id, sequence, event_type, node, metadata
                ),
                workflow_run_id=workflow_run_id,
                sequence=sequence,
                event_type=event_type,
                node=node,
                metadata=metadata,
                created_at=created_at,
            )
            connection.execute(
                """
                INSERT INTO runtime_events(workflow_run_id, sequence, event_id, model_json)
                VALUES (?, ?, ?, ?)
                """,
                (
                    workflow_run_id,
                    sequence,
                    event.event_id,
                    event.model_dump_json(),
                ),
            )
            return event

        return await self._database.run(operation)

    async def list_after(
        self, workflow_run_id: str, after_sequence: int
    ) -> tuple[WorkflowEvent, ...]:
        def operation(connection: sqlite3.Connection) -> tuple[str, ...]:
            rows = connection.execute(
                """
                SELECT model_json FROM runtime_events
                WHERE workflow_run_id = ? AND sequence > ? ORDER BY sequence
                """,
                (workflow_run_id, after_sequence),
            ).fetchall()
            return tuple(str(row["model_json"]) for row in rows)

        encoded = await self._database.run(operation)
        return tuple(WorkflowEvent.model_validate_json(item) for item in encoded)
