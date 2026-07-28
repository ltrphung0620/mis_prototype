"""Durable Risk checkpoint repository backed by SQLite."""

import sqlite3

from opc_mis.domain.risk_models import RiskRunState
from opc_mis.infrastructure.persistence.sqlite_database import SQLiteDatabase


class SQLiteRiskStateRepository:
    """Persist the latest resumable Risk checkpoint for each evaluation case."""

    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database

    async def save(self, state: RiskRunState) -> None:
        def operation(connection: sqlite3.Connection) -> None:
            connection.execute(
                """
                INSERT INTO risk_run_states(evaluation_case_id, model_json) VALUES (?, ?)
                ON CONFLICT(evaluation_case_id) DO UPDATE SET model_json = excluded.model_json
                """,
                (state.evaluation_case_id, state.model_dump_json()),
            )

        await self._database.run(operation)

    async def get_by_case(self, evaluation_case_id: str) -> RiskRunState | None:
        def operation(connection: sqlite3.Connection) -> str | None:
            row = connection.execute(
                "SELECT model_json FROM risk_run_states WHERE evaluation_case_id = ?",
                (evaluation_case_id,),
            ).fetchone()
            return None if row is None else str(row["model_json"])

        encoded = await self._database.run(operation)
        return None if encoded is None else RiskRunState.model_validate_json(encoded)
