"""Dataset snapshot port."""

from typing import Protocol

from opc_mis.domain.dataset import DatasetSnapshot


class DatasetNotFoundError(LookupError):
    """Raised when a workflow references an unknown dataset snapshot."""


class DatasetPort(Protocol):
    """Retrieve immutable resolved snapshots by dataset ID."""

    async def get_snapshot(self, dataset_id: str) -> DatasetSnapshot:
        """Return the current resolved snapshot for a dataset."""
        ...


class DatasetRepository(DatasetPort, Protocol):
    """Dataset port that can register ingestion results."""

    async def register(self, snapshot: DatasetSnapshot) -> None:
        """Register the current resolved snapshot for a dataset."""
        ...
