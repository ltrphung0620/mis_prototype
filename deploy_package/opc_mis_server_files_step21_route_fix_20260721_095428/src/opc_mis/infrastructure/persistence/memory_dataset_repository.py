"""Process-local DatasetPort implementation for CLI and tests."""

from opc_mis.domain.dataset import DatasetSnapshot
from opc_mis.ports.dataset_port import DatasetNotFoundError


class InMemoryDatasetRepository:
    """Store resolved snapshots without exposing Excel to business components."""

    def __init__(self) -> None:
        self._snapshots: dict[str, DatasetSnapshot] = {}

    async def register(self, snapshot: DatasetSnapshot) -> None:
        """Register or replace the current snapshot for a dataset ID."""
        self._snapshots[snapshot.dataset_id] = snapshot

    async def get_snapshot(self, dataset_id: str) -> DatasetSnapshot:
        """Return a resolved snapshot or fail explicitly."""
        try:
            return self._snapshots[dataset_id]
        except KeyError as exc:
            raise DatasetNotFoundError(f"Dataset snapshot not found: {dataset_id}") from exc
