"""Durable approval request repository backed by SQLite."""

import sqlite3

from opc_mis.domain.approvals import ApprovalRequest
from opc_mis.domain.enums import ApprovalRequestStatus
from opc_mis.infrastructure.persistence.sqlite_database import SQLiteDatabase


class SQLiteApprovalRequestRepository:
    """Persist mutable human approval status with stable request identity."""

    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database

    async def save(self, request: ApprovalRequest) -> None:
        def operation(connection: sqlite3.Connection) -> None:
            connection.execute(
                """
                INSERT INTO approval_requests(request_id, evaluation_case_id, model_json)
                VALUES (?, ?, ?)
                ON CONFLICT(request_id) DO UPDATE SET
                    evaluation_case_id = excluded.evaluation_case_id,
                    model_json = excluded.model_json
                """,
                (
                    request.request_id,
                    request.evaluation_case_id,
                    request.model_dump_json(),
                ),
            )

        await self._database.run(operation)

    async def compare_and_set(
        self,
        request: ApprovalRequest,
        *,
        expected_status: ApprovalRequestStatus,
    ) -> tuple[ApprovalRequest | None, bool]:
        """Atomically transition a request when its persisted status still matches."""

        def operation(
            connection: sqlite3.Connection,
        ) -> tuple[str | None, bool]:
            row = connection.execute(
                "SELECT model_json FROM approval_requests WHERE request_id = ?",
                (request.request_id,),
            ).fetchone()
            if row is None:
                return None, False
            current = ApprovalRequest.model_validate_json(str(row["model_json"]))
            if current.status is not expected_status:
                return current.model_dump_json(), False
            encoded = request.model_dump_json()
            cursor = connection.execute(
                """
                UPDATE approval_requests
                SET evaluation_case_id = ?, model_json = ?
                WHERE request_id = ?
                """,
                (request.evaluation_case_id, encoded, request.request_id),
            )
            if cursor.rowcount != 1:
                return current.model_dump_json(), False
            return encoded, True

        encoded, updated = await self._database.run(operation)
        stored = (
            None if encoded is None else ApprovalRequest.model_validate_json(encoded)
        )
        return stored, updated

    async def get(self, request_id: str) -> ApprovalRequest | None:
        def operation(connection: sqlite3.Connection) -> str | None:
            row = connection.execute(
                "SELECT model_json FROM approval_requests WHERE request_id = ?",
                (request_id,),
            ).fetchone()
            return None if row is None else str(row["model_json"])

        encoded = await self._database.run(operation)
        return None if encoded is None else ApprovalRequest.model_validate_json(encoded)

    async def list_by_case(self, evaluation_case_id: str) -> tuple[ApprovalRequest, ...]:
        def operation(connection: sqlite3.Connection) -> tuple[str, ...]:
            rows = connection.execute(
                """
                SELECT model_json FROM approval_requests
                WHERE evaluation_case_id = ? ORDER BY request_id
                """,
                (evaluation_case_id,),
            ).fetchall()
            return tuple(str(row["model_json"]) for row in rows)

        encoded = await self._database.run(operation)
        return tuple(ApprovalRequest.model_validate_json(item) for item in encoded)
