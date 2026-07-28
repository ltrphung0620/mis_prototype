"""Shared artifact draft and persisted envelope contracts."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from opc_mis.domain.enums import ArtifactStatus, ArtifactType, ValidationStatus
from opc_mis.domain.evidence import EvidenceRef


class ArtifactDraft(BaseModel):
    """Side-effect-free artifact candidate returned by a business component."""

    model_config = ConfigDict(frozen=True)

    artifact_type: ArtifactType
    evaluation_case_id: str
    producer: str
    payload: dict[str, Any]
    evidence_refs: tuple[EvidenceRef, ...] = ()
    identity_inputs: dict[str, Any] | None = None


class ArtifactEnvelope(BaseModel):
    """Versioned artifact validated and persisted by workflow infrastructure."""

    model_config = ConfigDict(frozen=True)

    artifact_id: str
    artifact_type: ArtifactType
    evaluation_case_id: str
    producer: str
    version: int = Field(ge=1)
    status: ArtifactStatus
    payload: dict[str, Any]
    evidence_refs: tuple[EvidenceRef, ...]
    input_artifact_ids: tuple[str, ...]
    input_hash: str
    validation_status: ValidationStatus
    validation_notes: tuple[str, ...]
    created_at: datetime
