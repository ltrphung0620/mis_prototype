"""Build and register a resolved dataset snapshot from a read-only TeamPack."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from opc_mis.domain.dataset import DatasetSnapshot
from opc_mis.domain.evidence import DataPatch
from opc_mis.domain.lineage import LineageFactory
from opc_mis.infrastructure.excel.normalizers import json_safe
from opc_mis.infrastructure.excel.overlay_store import OverlayStore
from opc_mis.infrastructure.excel.workbook_loader import WorkbookLoader
from opc_mis.ports.dataset_port import DatasetRepository


def _snapshot_hash(source_hash: str, patches: tuple[DataPatch, ...]) -> str:
    encoded = json.dumps(
        json_safe(
            {
                "source_hash": source_hash,
                "patches": [patch.model_dump(mode="json") for patch in patches],
            }
        ),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class ExcelDatasetIngestion:
    """Infrastructure service for source validation, indexing, and overlays."""

    def __init__(
        self,
        repository: DatasetRepository,
        *,
        loader: WorkbookLoader | None = None,
        overlay_store: OverlayStore | None = None,
    ) -> None:
        self._repository = repository
        self._loader = loader or WorkbookLoader()
        self._overlay_store = overlay_store or OverlayStore()

    async def ingest(
        self,
        *,
        dataset_id: str,
        workbook_path: Path,
        patches: tuple[DataPatch, ...] = (),
    ) -> DatasetSnapshot:
        """Load a TeamPack, apply isolated patches, and register its snapshot."""
        source = self._loader.load(dataset_id, workbook_path)
        lineage = LineageFactory(dataset_id, source.source_hash)
        resolved = self._overlay_store.apply(source, patches, lineage)
        resolved.snapshot_hash = _snapshot_hash(source.source_hash, patches)
        self._loader.verify_unchanged(source)
        await self._repository.register(resolved)
        return resolved
