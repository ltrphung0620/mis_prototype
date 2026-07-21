"""Resolve exact validated Final Risk and Internal Decision Package artifacts."""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import ValidationError

from opc_mis.domain.artifacts import ArtifactEnvelope
from opc_mis.domain.components import ExecutionContext
from opc_mis.domain.enums import ArtifactType, ValidationStatus
from opc_mis.domain.final_risk_models import FinalRiskAssessment
from opc_mis.domain.internal_decision_package_models import InternalDecisionPackage
from opc_mis.ports.artifact_repository import ArtifactRepository

_VALID_STATUSES = {ValidationStatus.VALID, ValidationStatus.VALID_WITH_WARNINGS}


class DecisionAnalysisContextError(RuntimeError):
    """Raised when exact Decision analysis input lineage cannot be established."""


@dataclass(frozen=True)
class DecisionAnalysisContext:
    """Immutable exact input pair for Decision analysis."""

    package_artifact: ArtifactEnvelope
    package: InternalDecisionPackage
    final_risk_artifact: ArtifactEnvelope
    final_risk: FinalRiskAssessment


class DecisionAnalysisContextLoader:
    """Load one current Final Risk and the exact package it references."""

    def __init__(self, *, artifacts: ArtifactRepository) -> None:
        self._artifacts = artifacts

    async def load(self, context: ExecutionContext) -> DecisionAnalysisContext:
        if context.evaluation_case_id is None:
            raise DecisionAnalysisContextError(
                "Decision analysis requires evaluation_case_id."
            )
        if len(context.input_artifact_ids) != 1:
            raise DecisionAnalysisContextError(
                "Decision analysis requires exactly one Final Risk artifact."
            )
        final_risk_artifact = await self._validated_artifact(
            context.input_artifact_ids[0],
            ArtifactType.FINAL_RISK_ASSESSMENT,
            context.evaluation_case_id,
        )
        try:
            final_risk = FinalRiskAssessment.model_validate(
                final_risk_artifact.payload
            )
        except ValidationError as exc:
            raise DecisionAnalysisContextError(
                f"Decision received invalid Final Risk: {exc}"
            ) from exc
        if (
            final_risk.evaluation_case_id != context.evaluation_case_id
            or final_risk.dataset_id != context.dataset_id
        ):
            raise DecisionAnalysisContextError(
                "Final Risk belongs to another case or dataset."
            )
        if final_risk.evidence_ids != tuple(
            item.evidence_id for item in final_risk_artifact.evidence_refs
        ):
            raise DecisionAnalysisContextError(
                "Final Risk evidence differs from its persisted envelope."
            )

        package_artifact = await self._validated_artifact(
            final_risk.internal_decision_package_artifact_id,
            ArtifactType.INTERNAL_DECISION_PACKAGE,
            context.evaluation_case_id,
        )
        if (
            package_artifact.version
            != final_risk.internal_decision_package_artifact_version
            or package_artifact.input_hash
            != final_risk.internal_decision_package_input_hash
            or final_risk_artifact.input_artifact_ids
            != (package_artifact.artifact_id,)
        ):
            raise DecisionAnalysisContextError(
                "Final Risk does not bind the exact persisted Internal Decision Package."
            )
        try:
            package = InternalDecisionPackage.model_validate(package_artifact.payload)
        except ValidationError as exc:
            raise DecisionAnalysisContextError(
                f"Decision received invalid Internal Decision Package: {exc}"
            ) from exc
        if (
            package.package_id != final_risk.internal_decision_package_id
            or package.evaluation_case_id != context.evaluation_case_id
            or package.dataset_id != context.dataset_id
            or package.contract_id != final_risk.contract_id
        ):
            raise DecisionAnalysisContextError(
                "Final Risk and Internal Decision Package identities differ."
            )
        if package.source_artifact_ids != package_artifact.input_artifact_ids:
            raise DecisionAnalysisContextError(
                "Internal Decision Package lineage differs from its envelope."
            )
        if package.evidence_ids != tuple(
            item.evidence_id for item in package_artifact.evidence_refs
        ):
            raise DecisionAnalysisContextError(
                "Internal Decision Package evidence differs from its envelope."
            )
        return DecisionAnalysisContext(
            package_artifact=package_artifact,
            package=package,
            final_risk_artifact=final_risk_artifact,
            final_risk=final_risk,
        )

    async def _validated_artifact(
        self,
        artifact_id: str,
        expected_type: ArtifactType,
        evaluation_case_id: str,
    ) -> ArtifactEnvelope:
        artifact = await self._artifacts.get(artifact_id)
        if artifact is None:
            raise DecisionAnalysisContextError(
                f"Decision received unknown artifact: {artifact_id}."
            )
        if artifact.artifact_type is not expected_type:
            raise DecisionAnalysisContextError(
                f"Decision expected {expected_type.value}, got {artifact.artifact_type.value}."
            )
        if artifact.validation_status not in _VALID_STATUSES:
            raise DecisionAnalysisContextError(
                f"Decision received unvalidated {expected_type.value}."
            )
        if artifact.evaluation_case_id != evaluation_case_id:
            raise DecisionAnalysisContextError(
                f"Decision received cross-case {expected_type.value}."
            )
        return artifact
