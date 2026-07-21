"""Load and revalidate exact inputs required to assemble a Decision Card."""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import ValidationError

from opc_mis.domain.artifacts import ArtifactEnvelope
from opc_mis.domain.components import ExecutionContext
from opc_mis.domain.decision_analysis import (
    DecisionAnalysisBoundaryError,
    build_decision_scenario_packet,
    guard_ai_decision_composition,
)
from opc_mis.domain.decision_models import (
    AIDecisionAnalysis,
    AIDecisionAttentionPointDraft,
    AIDecisionComposition,
    AIDecisionProposalDraft,
    AIDecisionReasonDraft,
    AIDecisionRecommendedActionDraft,
    DecisionScenarioPacket,
    NegotiationConditionDraft,
)
from opc_mis.domain.enums import ArtifactType, ValidationStatus
from opc_mis.domain.final_risk_models import FinalRiskAssessment
from opc_mis.domain.internal_decision_package_models import InternalDecisionPackage
from opc_mis.ports.artifact_repository import ArtifactRepository

_VALID_STATUSES = {ValidationStatus.VALID, ValidationStatus.VALID_WITH_WARNINGS}


class DecisionCardContextError(RuntimeError):
    """Raised when a Card cannot establish exact validated analysis lineage."""


@dataclass(frozen=True)
class DecisionCardContext:
    """Canonical packet and exact guarded analysis used for Card assembly."""

    package_artifact: ArtifactEnvelope
    package: InternalDecisionPackage
    final_risk_artifact: ArtifactEnvelope
    final_risk: FinalRiskAssessment
    analysis_artifact: ArtifactEnvelope
    analysis: AIDecisionAnalysis
    packet: DecisionScenarioPacket


class DecisionCardContextLoader:
    """Resolve one analysis and recalculate every deterministic dependency."""

    def __init__(self, *, artifacts: ArtifactRepository) -> None:
        self._artifacts = artifacts

    async def load(self, context: ExecutionContext) -> DecisionCardContext:
        if context.evaluation_case_id is None:
            raise DecisionCardContextError("Decision Card requires evaluation_case_id.")
        if len(context.input_artifact_ids) != 1:
            raise DecisionCardContextError(
                "Decision Card requires exactly one AI Decision Analysis artifact."
            )
        analysis_artifact = await self._artifact(
            context.input_artifact_ids[0],
            ArtifactType.AI_DECISION_ANALYSIS,
            context.evaluation_case_id,
        )
        try:
            analysis = AIDecisionAnalysis.model_validate(analysis_artifact.payload)
        except ValidationError as exc:
            raise DecisionCardContextError(
                f"Decision Card received invalid AI analysis: {exc}"
            ) from exc
        if (
            analysis.evaluation_case_id != context.evaluation_case_id
            or analysis.dataset_id != context.dataset_id
        ):
            raise DecisionCardContextError(
                "AI Decision Analysis belongs to another case or dataset."
            )
        final_risk_artifact = await self._exact_ref_artifact(
            analysis.final_risk_artifact,
            context.evaluation_case_id,
        )
        package_artifact = await self._exact_ref_artifact(
            analysis.internal_decision_package_artifact,
            context.evaluation_case_id,
        )
        if analysis_artifact.input_artifact_ids != (final_risk_artifact.artifact_id,):
            raise DecisionCardContextError(
                "AI Decision Analysis envelope does not bind the exact Final Risk."
            )
        try:
            final_risk = FinalRiskAssessment.model_validate(final_risk_artifact.payload)
            package = InternalDecisionPackage.model_validate(package_artifact.payload)
        except ValidationError as exc:
            raise DecisionCardContextError(
                f"Decision Card received invalid upstream payload: {exc}"
            ) from exc
        try:
            packet = build_decision_scenario_packet(
                package_artifact=package_artifact,
                package=package,
                final_risk_artifact=final_risk_artifact,
                final_risk=final_risk,
            )
            canonical = guard_ai_decision_composition(
                packet=packet,
                composition=AIDecisionComposition(
                    proposal=AIDecisionProposalDraft(
                        recommendation=analysis.recommendation,
                        executive_summary=analysis.executive_summary,
                        reasons=tuple(
                            AIDecisionReasonDraft.model_validate(
                                item.model_dump(
                                    exclude={"reason_id", "recommended_action"}
                                )
                            )
                            for item in analysis.reasons
                        ),
                        recommended_actions=tuple(
                            AIDecisionRecommendedActionDraft(
                                reason_code=item.code,
                                action=item.recommended_action,
                                source_reference_ids=item.source_reference_ids,
                                evidence_ids=item.evidence_ids,
                            )
                            for item in analysis.reasons
                            if item.recommended_action is not None
                        ),
                        conditions=tuple(
                            NegotiationConditionDraft.model_validate(
                                item.model_dump(exclude={"condition_id"})
                            )
                            for item in analysis.conditions
                        ),
                        selected_negotiation_strategy_ids=(
                            analysis.selected_negotiation_strategy_ids
                        ),
                        selected_option_ids=analysis.selected_option_ids,
                        confidence=analysis.confidence,
                        human_attention_points=tuple(
                            AIDecisionAttentionPointDraft.model_validate(
                                item.model_dump(exclude={"attention_point_id"})
                            )
                            for item in analysis.human_attention_points
                        ),
                    ),
                    source=analysis.source,
                    model=analysis.model,
                    prompt_version=analysis.prompt_version,
                    input_hash=analysis.input_hash,
                    fallback_reason=analysis.fallback_reason,
                ),
            )
        except (DecisionAnalysisBoundaryError, ValidationError, ValueError) as exc:
            raise DecisionCardContextError(
                f"AI Decision Analysis does not match canonical inputs: {exc}"
            ) from exc
        if canonical != analysis:
            raise DecisionCardContextError(
                "AI Decision Analysis differs from deterministic guard output."
            )
        envelope_evidence_ids = tuple(
            item.evidence_id for item in analysis_artifact.evidence_refs
        )
        if envelope_evidence_ids != packet.known_evidence_ids:
            raise DecisionCardContextError(
                "AI Decision Analysis envelope evidence differs from its packet."
            )
        return DecisionCardContext(
            package_artifact=package_artifact,
            package=package,
            final_risk_artifact=final_risk_artifact,
            final_risk=final_risk,
            analysis_artifact=analysis_artifact,
            analysis=analysis,
            packet=packet,
        )

    async def _exact_ref_artifact(
        self,
        reference,
        evaluation_case_id: str,
    ) -> ArtifactEnvelope:
        artifact = await self._artifact(
            reference.artifact_id,
            reference.artifact_type,
            evaluation_case_id,
        )
        if artifact.version != reference.version or artifact.input_hash != reference.input_hash:
            raise DecisionCardContextError(
                f"Decision Card upstream {reference.artifact_type.value} version changed."
            )
        return artifact

    async def _artifact(
        self,
        artifact_id: str,
        expected_type: ArtifactType,
        evaluation_case_id: str,
    ) -> ArtifactEnvelope:
        artifact = await self._artifacts.get(artifact_id)
        if artifact is None:
            raise DecisionCardContextError(f"Decision Card artifact not found: {artifact_id}.")
        if artifact.artifact_type is not expected_type:
            raise DecisionCardContextError(
                f"Decision Card expected {expected_type.value}."
            )
        if artifact.validation_status not in _VALID_STATUSES:
            raise DecisionCardContextError(
                f"Decision Card received unvalidated {expected_type.value}."
            )
        if artifact.evaluation_case_id != evaluation_case_id:
            raise DecisionCardContextError(
                f"Decision Card received cross-case {expected_type.value}."
            )
        return artifact
