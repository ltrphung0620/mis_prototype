"""Infrastructure-neutral dataset snapshot models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from opc_mis.domain.evidence import EvidenceRef

if TYPE_CHECKING:
    from opc_mis.domain.team_pack import SheetDefinition


@dataclass(frozen=True)
class ValidationIssue:
    """A typed finding produced while ingesting or resolving dataset records."""

    code: str
    sheet: str
    record_id: str
    field: str
    reason: str


@dataclass
class DatasetRecord:
    """Normalized record with source display values and optional patch lineage."""

    sheet: str
    row_number: int
    record_id: str
    values: dict[str, Any]
    display_values: dict[str, Any]
    patched_evidence: dict[str, EvidenceRef] = field(default_factory=dict)


@dataclass
class DatasetSnapshot:
    """Indexed, in-memory dataset projection consumed by business components."""

    dataset_id: str
    source_locator: str
    source_hash: str
    snapshot_hash: str
    sheets: dict[str, list[DatasetRecord]]
    headers: dict[str, tuple[str, ...]]
    indexes: dict[str, dict[str, list[DatasetRecord]]]
    duplicate_ids: dict[str, tuple[str, ...]]
    validation_issues: list[ValidationIssue]
    missing_sheets: tuple[str, ...]
    missing_headers: dict[str, tuple[str, ...]]

    @property
    def workbook_hash(self) -> str:
        """Compatibility name for evidence derived from the immutable source hash."""
        return self.source_hash

    def records(self, definition: SheetDefinition) -> list[DatasetRecord]:
        """Return records for a canonical sheet definition."""
        return self.sheets.get(definition.sheet_name, [])

    def lookup(self, definition: SheetDefinition, record_id: str) -> list[DatasetRecord]:
        """Return all exact primary-key matches."""
        return self.indexes.get(definition.sheet_name, {}).get(record_id, [])
