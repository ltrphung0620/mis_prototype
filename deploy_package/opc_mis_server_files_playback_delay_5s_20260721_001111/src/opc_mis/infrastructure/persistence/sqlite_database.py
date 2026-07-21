"""Small transactional SQLite foundation shared by durable repository adapters."""

import asyncio
import sqlite3
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

T = TypeVar("T")


_SCHEMA = """
CREATE TABLE IF NOT EXISTS artifacts (
    artifact_id TEXT PRIMARY KEY,
    evaluation_case_id TEXT NOT NULL,
    artifact_type TEXT NOT NULL,
    version INTEGER NOT NULL,
    input_hash TEXT NOT NULL,
    model_json TEXT NOT NULL,
    UNIQUE(evaluation_case_id, artifact_type, version)
);
CREATE INDEX IF NOT EXISTS idx_artifacts_case
    ON artifacts(evaluation_case_id, artifact_id);

CREATE TABLE IF NOT EXISTS workflow_states (
    workflow_run_id TEXT PRIMARY KEY,
    model_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS risk_run_states (
    evaluation_case_id TEXT PRIMARY KEY,
    model_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS approval_requests (
    request_id TEXT PRIMARY KEY,
    evaluation_case_id TEXT NOT NULL,
    model_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_approval_requests_case
    ON approval_requests(evaluation_case_id, request_id);

CREATE TABLE IF NOT EXISTS case_workflow_runs (
    workflow_run_id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    model_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_case_workflow_status
    ON case_workflow_runs(status, workflow_run_id);

CREATE TABLE IF NOT EXISTS workflow_node_states (
    workflow_run_id TEXT NOT NULL,
    node TEXT NOT NULL,
    model_json TEXT NOT NULL,
    PRIMARY KEY(workflow_run_id, node)
);

CREATE TABLE IF NOT EXISTS runtime_events (
    workflow_run_id TEXT NOT NULL,
    sequence INTEGER NOT NULL,
    event_id TEXT NOT NULL UNIQUE,
    model_json TEXT NOT NULL,
    PRIMARY KEY(workflow_run_id, sequence)
);
"""


class SQLiteDatabase:
    """Serialize access to one SQLite connection and commit each repository operation."""

    def __init__(self, path: Path | str) -> None:
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).resolve().parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(
            self.path,
            check_same_thread=False,
            isolation_level=None,
        )
        self._connection.row_factory = sqlite3.Row
        self._lock = asyncio.Lock()
        self._closed = False

    async def initialize(self) -> None:
        """Create durable tables and enable safe SQLite pragmas."""

        def operation(connection: sqlite3.Connection) -> None:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA busy_timeout = 5000")
            connection.executescript(_SCHEMA)

        await self.run(operation)

    async def run(self, operation: Callable[[sqlite3.Connection], T]) -> T:
        """Execute one callback inside a serialized `BEGIN IMMEDIATE` transaction."""
        if self._closed:
            raise RuntimeError("SQLite database is closed.")
        async with self._lock:
            return await asyncio.to_thread(self._run_sync, operation)

    def _run_sync(self, operation: Callable[[sqlite3.Connection], T]) -> T:
        self._connection.execute("BEGIN IMMEDIATE")
        try:
            result = operation(self._connection)
        except Exception:
            self._connection.rollback()
            raise
        self._connection.commit()
        return result

    async def close(self) -> None:
        """Close the connection after background workflow tasks have stopped."""
        if self._closed:
            return
        async with self._lock:
            await asyncio.to_thread(self._connection.close)
            self._closed = True
