"""Create versioned artifact envelopes after governance validation."""

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime

from opc_mis.domain.artifacts import ArtifactDraft, ArtifactEnvelope
from opc_mis.domain.components import ExecutionContext
from opc_mis.domain.enums import ArtifactStatus
from opc_mis.domain.lineage import deterministic_id
from opc_mis.domain.serialization import json_safe
from opc_mis.domain.validation_reports import ValidationReport


def artifact_input_hash(draft: ArtifactDraft, context: ExecutionContext) -> str:
    """Hash every explicit upstream dependency and deterministic draft payload."""
    payload = {
        "dataset_id": context.dataset_id,
        "input_artifact_ids": context.input_artifact_ids,
        "artifact_type": draft.artifact_type,
        "business_inputs": (
            draft.identity_inputs if draft.identity_inputs is not None else draft.payload
        ),
        "evidence_ids": tuple(item.evidence_id for item in draft.evidence_refs),
    }
    encoded = json.dumps(
        json_safe(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class ArtifactFactory:
    """Attach workflow-owned identity, version, validation, and creation time."""

    def __init__(self, clock: Callable[[], datetime] | None = None) -> None:
        self._clock = clock or (lambda: datetime.now(UTC))

    def create(
        self,
        *,
        draft: ArtifactDraft,
        context: ExecutionContext,
        validation_report: ValidationReport,
        version: int,
    ) -> ArtifactEnvelope:
        """Create a persistable artifact envelope from a validated draft."""
        input_hash = artifact_input_hash(draft, context)
        return ArtifactEnvelope(
            artifact_id=deterministic_id(
                "ART",
                draft.evaluation_case_id,
                draft.artifact_type,
                input_hash,
            ),
            artifact_type=draft.artifact_type,
            evaluation_case_id=draft.evaluation_case_id,
            producer=draft.producer,
            version=version,
            status=ArtifactStatus.CREATED,
            payload=draft.payload,
            evidence_refs=draft.evidence_refs,
            input_artifact_ids=context.input_artifact_ids,
            input_hash=input_hash,
            validation_status=validation_report.status,
            validation_notes=validation_report.warnings,
            created_at=self._clock(),
        )
