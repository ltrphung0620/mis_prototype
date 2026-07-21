"""Deterministic evidence lineage construction independent of Excel libraries."""

import hashlib
import json
from typing import Any

from opc_mis.domain.dataset import DatasetRecord
from opc_mis.domain.enums import SourceType
from opc_mis.domain.evidence import DataPatch, EvidenceRef
from opc_mis.domain.serialization import json_safe


def deterministic_id(prefix: str, *parts: Any) -> str:
    """Create a stable identifier from canonical JSON input."""
    encoded = json.dumps(
        json_safe(parts),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:24].upper()
    return f"{prefix}-{digest}"


class LineageFactory:
    """Create TEAM_PACK, USER_INPUT, and DERIVED evidence references."""

    def __init__(self, dataset_id: str, source_hash: str) -> None:
        self._dataset_id = dataset_id
        self._source_hash = source_hash

    def record_field(self, record: DatasetRecord, field: str) -> EvidenceRef:
        """Reference a selected record field, honoring patch provenance."""
        if field in record.patched_evidence:
            return record.patched_evidence[field]
        display = record.display_values.get(field)
        evidence_id = deterministic_id(
            "EVD",
            self._dataset_id,
            self._source_hash,
            SourceType.TEAM_PACK,
            record.sheet,
            record.row_number,
            record.record_id,
            field,
            display,
        )
        return EvidenceRef(
            evidence_id=evidence_id,
            source_type=SourceType.TEAM_PACK,
            sheet=record.sheet,
            row_number=record.row_number,
            record_id=record.record_id,
            field=field,
            display_value=json_safe(display),
        )

    def sheet_headers(self, sheet: str, headers: tuple[str, ...]) -> EvidenceRef:
        """Reference the actual TeamPack header row."""
        evidence_id = deterministic_id(
            "EVD",
            self._dataset_id,
            self._source_hash,
            SourceType.TEAM_PACK,
            sheet,
            1,
            "HEADER",
            "headers",
            headers,
        )
        return EvidenceRef(
            evidence_id=evidence_id,
            source_type=SourceType.TEAM_PACK,
            sheet=sheet,
            row_number=1,
            record_id="HEADER",
            field="headers",
            display_value=list(headers),
        )

    def patch(self, patch: DataPatch, sheet: str) -> EvidenceRef:
        """Create evidence for an in-memory user patch."""
        safe_value = json_safe(patch.value)
        evidence_id = deterministic_id(
            "EVD",
            self._dataset_id,
            self._source_hash,
            SourceType.USER_INPUT,
            patch.patch_id,
            sheet,
            patch.target_record,
            patch.field,
            safe_value,
            patch.evidence_note,
        )
        return EvidenceRef(
            evidence_id=evidence_id,
            source_type=SourceType.USER_INPUT,
            sheet=sheet,
            row_number=0,
            record_id=patch.target_record,
            field=patch.field,
            display_value=safe_value,
        )

    def user_input(
        self,
        *,
        record_id: str,
        field: str,
        display: Any,
    ) -> EvidenceRef:
        """Create evidence for a typed execution input that is not a dataset patch."""
        safe_display = json_safe(display)
        evidence_id = deterministic_id(
            "EVD",
            self._dataset_id,
            self._source_hash,
            SourceType.USER_INPUT,
            record_id,
            field,
            safe_display,
        )
        return EvidenceRef(
            evidence_id=evidence_id,
            source_type=SourceType.USER_INPUT,
            sheet="EXECUTION_INPUT",
            row_number=0,
            record_id=record_id,
            field=field,
            display_value=safe_display,
        )

    def derived(
        self,
        *,
        sheet: str,
        record_id: str,
        field: str,
        display: Any,
        sources: tuple[EvidenceRef, ...],
    ) -> EvidenceRef:
        """Create evidence for a deterministic Planner derivation."""
        safe_display = json_safe(display)
        source_ids = tuple(source.evidence_id for source in sources)
        evidence_id = deterministic_id(
            "EVD",
            self._dataset_id,
            self._source_hash,
            SourceType.DERIVED,
            sheet,
            record_id,
            field,
            safe_display,
            source_ids,
        )
        return EvidenceRef(
            evidence_id=evidence_id,
            source_type=SourceType.DERIVED,
            sheet=sheet,
            row_number=0,
            record_id=record_id,
            field=field,
            display_value=safe_display,
            source_evidence_ids=source_ids,
        )
