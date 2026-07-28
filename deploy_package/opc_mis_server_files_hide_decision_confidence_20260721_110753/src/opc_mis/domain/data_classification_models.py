"""Infrastructure-neutral data-classification policy contracts."""

from __future__ import annotations

from enum import StrEnum

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictStr,
    field_validator,
    model_validator,
)


class DataClassification(StrEnum):
    """Sensitivity classes used at outbound trust boundaries."""

    PUBLIC = "PUBLIC"
    INTERNAL = "INTERNAL"
    CONFIDENTIAL = "CONFIDENTIAL"
    RESTRICTED = "RESTRICTED"
    RESTRICTED_SECRET = "RESTRICTED_SECRET"
    CONTEXT_DEPENDENT = "CONTEXT_DEPENDENT"


class DataClassificationRule(BaseModel):
    """One exact, server-owned field classification rule."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    rule_id: StrictStr = Field(min_length=1)
    field_name: StrictStr = Field(
        min_length=1,
        pattern=r"^[A-Za-z][A-Za-z0-9_]*$",
    )
    classification: DataClassification
    policy_reference: StrictStr = Field(min_length=1)
    source_evidence_ids: tuple[StrictStr, ...] = ()

    @field_validator("source_evidence_ids")
    @classmethod
    def require_unique_evidence_ids(
        cls,
        value: tuple[str, ...],
    ) -> tuple[str, ...]:
        """Reject ambiguous duplicate evidence references."""
        if len(set(value)) != len(value):
            raise ValueError("source_evidence_ids must be unique")
        return value

    @model_validator(mode="after")
    def reject_unsubstantiated_team_pack_reference(self) -> DataClassificationRule:
        """Do not label a server rule as TeamPack evidence without exact lineage."""
        if self.policy_reference.startswith("TEAM_PACK:") and not self.source_evidence_ids:
            raise ValueError(
                "TEAM_PACK policy_reference requires exact source_evidence_ids"
            )
        return self


class ClassificationDecision(BaseModel):
    """Auditable classification selected by exact field-name lookup."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    decision_id: StrictStr = Field(min_length=1)
    field_name: StrictStr = Field(min_length=1)
    classification: DataClassification
    rule_id: StrictStr = Field(min_length=1)
    policy_reference: StrictStr = Field(min_length=1)
    source_evidence_ids: tuple[StrictStr, ...] = ()
