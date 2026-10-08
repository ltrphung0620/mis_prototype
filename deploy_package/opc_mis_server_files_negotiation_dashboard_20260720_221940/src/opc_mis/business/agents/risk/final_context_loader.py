"""Load the exact validated Internal Decision Package for Final Risk."""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import ValidationError

from opc_mis.domain.artifacts import ArtifactEnvelope
from opc_mis.domain.components import ExecutionContext
from opc_mis.domain.enums import ArtifactType, ValidationStatus
from opc_mis.domain.internal_decision_package_models import InternalDecisionPackage
from opc_mis.ports.artifact_repository import ArtifactRepository

_VALID_STATUSES = {ValidationStatus.VALID, ValidationStatus.VALID_WITH_WARNINGS}


class FinalRiskContextError(RuntimeError):
    """Raised when Final Risk cannot establish exact validated input lineage."""


@dataclass(frozen=True)
class FinalRiskContext:
    """Parsed immutable package and the exact envelope that carried it."""

    package_artifact: ArtifactEnvelope
    package: InternalDecisionPackage


class FinalRiskContextLoader:
    """Resolve one authoritative package without dataset or external-system reads."""

    def __init__(self, *, artifacts: ArtifactRepository) -> None:
        self._artifacts = artifacts

    async def load(self, context: ExecutionContext) -> FinalRiskContext:
        if context.evaluation_case_id is None:
            raise FinalRiskContextError("Final Risk requires evaluation_case_id.")
        if len(context.input_artifact_ids) != 1:
            raise FinalRiskContextError(
                "Final Risk requires exactly one Internal Decision Package artifact."
            )
        artifact_id = context.input_artifact_ids[0]
        artifact = await self._artifacts.get(artifact_id)
        if artifact is None:
            raise FinalRiskContextError(
                f"Final Risk received an unknown artifact: {artifact_id}."
            )
        if artifact.artifact_type is not ArtifactType.INTERNAL_DECISION_PACKAGE:
            raise FinalRiskContextError(
                "Final Risk accepts only an Internal Decision Package artifact."
            )
        if artifact.validation_status not in _VALID_STATUSES:
            raise FinalRiskContextError(
                "Final Risk received an Internal Decision Package that was not validated."
            )
        if artifact.evaluation_case_id != context.evaluation_case_id:
            raise FinalRiskContextError(
                "Final Risk package belongs to another evaluation case."
            )
        try:
            package = InternalDecisionPackage.model_validate(artifact.payload)
        except ValidationError as exc:
            raise FinalRiskContextError(
                f"Final Risk received an invalid Internal Decision Package: {exc}"
            ) from exc
        if package.evaluation_case_id != context.evaluation_case_id:
            raise FinalRiskContextError(
                "Final Risk package payload belongs to another evaluation case."
            )
        if package.dataset_id != context.dataset_id:
            raise FinalRiskContextError(
                "Final Risk package payload belongs to another dataset."
            )
        if package.source_artifact_ids != artifact.input_artifact_ids:
            raise FinalRiskContextError(
                "Final Risk package lineage differs from its persisted envelope."
            )
        if package.evidence_ids != tuple(
            evidence.evidence_id for evidence in artifact.evidence_refs
        ):
            raise FinalRiskContextError(
                "Final Risk package evidence differs from its persisted envelope."
            )
        return FinalRiskContext(package_artifact=artifact, package=package)
