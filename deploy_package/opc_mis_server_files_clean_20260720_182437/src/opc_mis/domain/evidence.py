"""Evidence and user overlay models."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from opc_mis.domain.enums import SourceType


class EvidenceRef(BaseModel):
    """Trace a selected or derived value back to its source."""

    model_config = ConfigDict(frozen=True)

    evidence_id: str
    source_type: SourceType
    sheet: str
    row_number: int = Field(ge=0)
    record_id: str
    field: str
    display_value: Any
    source_evidence_ids: tuple[str, ...] = ()


class DataPatch(BaseModel):
    """An in-memory user correction that never writes to the source workbook."""

    model_config = ConfigDict(frozen=True)

    patch_id: str
    source: SourceType = SourceType.USER_INPUT
    target_sheet: str | None = None
    canonical_entity_type: str | None = None
    target_record: str
    field: str
    value: Any
    evidence_note: str

    @model_validator(mode="after")
    def validate_target(self) -> "DataPatch":
        """Require exactly one target naming strategy."""
        if (self.target_sheet is None) == (self.canonical_entity_type is None):
            raise ValueError("exactly one of target_sheet or canonical_entity_type is required")
        if self.source is not SourceType.USER_INPUT:
            raise ValueError("Planner data patches must have USER_INPUT source")
        return self
