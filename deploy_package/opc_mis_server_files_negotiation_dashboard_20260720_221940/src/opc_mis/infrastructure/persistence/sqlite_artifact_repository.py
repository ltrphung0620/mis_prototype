"""Durable immutable ArtifactRepository backed by SQLite."""

import sqlite3

from opc_mis.domain.artifacts import ArtifactEnvelope
from opc_mis.infrastructure.persistence.sqlite_database import SQLiteDatabase


class SQLiteArtifactRepository:
    """Persist JSON-safe artifact envelopes with stable identity and version constraints."""

    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database

    async def save(self, artifact: ArtifactEnvelope) -> None:
        """Insert an immutable artifact idempotently and reject identity collisions."""

        def operation(connection: sqlite3.Connection) -> None:
            encoded = artifact.model_dump_json()
            existing = connection.execute(
                "SELECT model_json FROM artifacts WHERE artifact_id = ?",
                (artifact.artifact_id,),
            ).fetchone()
            if existing is not None:
                if existing["model_json"] != encoded:
                    raise ValueError(
                        f"Artifact identity collision for {artifact.artifact_id}."
                    )
                return
            connection.execute(
                """
                INSERT INTO artifacts(
                    artifact_id, evaluation_case_id, artifact_type,
                    version, input_hash, model_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    artifact.artifact_id,
                    artifact.evaluation_case_id,
                    artifact.artifact_type.value,
                    artifact.version,
                    artifact.input_hash,
                    encoded,
                ),
            )

        await self._database.run(operation)

    async def get(self, artifact_id: str) -> ArtifactEnvelope | None:
        """Return one immutable artifact by stable ID."""

        def operation(connection: sqlite3.Connection) -> str | None:
            row = connection.execute(
                "SELECT model_json FROM artifacts WHERE artifact_id = ?",
                (artifact_id,),
            ).fetchone()
            return None if row is None else str(row["model_json"])

        encoded = await self._database.run(operation)
        return None if encoded is None else ArtifactEnvelope.model_validate_json(encoded)

    async def list_by_case(self, evaluation_case_id: str) -> tuple[ArtifactEnvelope, ...]:
        """Return case artifacts ordered by stable ID."""

        def operation(connection: sqlite3.Connection) -> tuple[str, ...]:
            rows = connection.execute(
                """
                SELECT model_json FROM artifacts
                WHERE evaluation_case_id = ? ORDER BY artifact_id
                """,
                (evaluation_case_id,),
            ).fetchall()
            return tuple(str(row["model_json"]) for row in rows)

        encoded = await self._database.run(operation)
        return tuple(ArtifactEnvelope.model_validate_json(item) for item in encoded)
