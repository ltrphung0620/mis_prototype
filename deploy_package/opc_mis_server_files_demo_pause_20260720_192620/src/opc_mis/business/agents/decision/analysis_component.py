"""AI-assisted Decision analysis behind deterministic evidence guardrails."""

from pydantic import ValidationError

from opc_mis.business.agents.decision.analysis_context import (
    DecisionAnalysisContextError,
    DecisionAnalysisContextLoader,
)
from opc_mis.domain.artifacts import ArtifactDraft
from opc_mis.domain.components import ExecutionContext
from opc_mis.domain.decision_analysis import (
    DecisionAnalysisBoundaryError,
    build_decision_scenario_packet,
    guard_ai_decision_composition,
)
from opc_mis.domain.decision_models import (
    DecisionAnalysisComponentResult,
    DecisionAnalysisSource,
    DecisionRecommendation,
)
from opc_mis.domain.enums import ArtifactType, ComponentStatus
from opc_mis.domain.events import RuntimeEvent
from opc_mis.ports.decision_analysis_port import DecisionAnalysisPort


class DecisionAnalysisAgent:
    """Let OpenAI propose while deterministic code owns facts and eligibility."""

    component_id = "DECISION_ANALYSIS_AGENT"

    def __init__(
        self,
        *,
        context_loader: DecisionAnalysisContextLoader,
        composer: DecisionAnalysisPort,
    ) -> None:
        self._context_loader = context_loader
        self._composer = composer

    async def execute(self, context: ExecutionContext) -> DecisionAnalysisComponentResult:
        """Return one guarded analysis draft without approval or workflow effects."""

        try:
            composer_configuration_hash = context.component_input.get(
                "composer_configuration_hash"
            )
            if not isinstance(composer_configuration_hash, str) or not (
                composer_configuration_hash.strip()
            ):
                raise DecisionAnalysisBoundaryError(
                    "Decision analysis requires an exact composer configuration hash."
                )
            analysis_context = await self._context_loader.load(context)
            packet = build_decision_scenario_packet(
                package_artifact=analysis_context.package_artifact,
                package=analysis_context.package,
                final_risk_artifact=analysis_context.final_risk_artifact,
                final_risk=analysis_context.final_risk,
            )
            composition = await self._composer.compose(packet)
            analysis = guard_ai_decision_composition(
                packet=packet,
                composition=composition,
            )
        except (
            DecisionAnalysisBoundaryError,
            DecisionAnalysisContextError,
            ValidationError,
            ValueError,
        ) as exc:
            return self._failed_safe(str(exc))

        evidence_by_id = {
            item.evidence_id: item
            for artifact in (
                analysis_context.package_artifact,
                analysis_context.final_risk_artifact,
            )
            for item in artifact.evidence_refs
        }
        try:
            evidence_refs = tuple(
                evidence_by_id[evidence_id]
                for evidence_id in packet.known_evidence_ids
            )
        except KeyError as exc:
            return self._failed_safe(
                f"Decision packet references unavailable evidence: {exc.args[0]}."
            )
        draft = ArtifactDraft(
            artifact_type=ArtifactType.AI_DECISION_ANALYSIS,
            evaluation_case_id=analysis.evaluation_case_id,
            producer=self.component_id,
            payload=analysis.model_dump(mode="json"),
            evidence_refs=evidence_refs,
            identity_inputs={
                "packet_id": packet.packet_id,
                "internal_decision_package_artifact": (
                    packet.internal_decision_package_artifact.model_dump(mode="json")
                ),
                "final_risk_artifact": packet.final_risk_artifact.model_dump(
                    mode="json"
                ),
                "analysis_source": analysis.source,
                "model": analysis.model,
                "prompt_version": analysis.prompt_version,
                "composer_input_hash": analysis.input_hash,
                "composer_configuration_hash": composer_configuration_hash,
            },
        )
        warnings: list[str] = []
        events: list[RuntimeEvent] = []
        if analysis.source is DecisionAnalysisSource.DETERMINISTIC_FALLBACK:
            warnings.append("DECISION_ANALYSIS_FALLBACK_USED")
            events.append(
                RuntimeEvent(
                    event_type="FALLBACK_USED",
                    message="Decision analysis used the safe deterministic fallback.",
                    metadata={
                        "reason": analysis.fallback_reason or "OPENAI_UNAVAILABLE"
                    },
                )
            )
        if analysis.recommendation is DecisionRecommendation.NOT_EVALUABLE:
            warnings.append("DECISION_NOT_EVALUABLE")
        events.append(
            RuntimeEvent(
                event_type="AI_DECISION_ANALYSIS_CREATED",
                message=(
                    "Decision created an evidence-bound recommendation proposal; no "
                    "approval or external action was requested."
                ),
                metadata={
                    "analysis_id": analysis.analysis_id,
                    "recommendation": analysis.recommendation.value,
                    "condition_count": len(analysis.conditions),
                    "analysis_source": analysis.source.value,
                },
            )
        )
        return DecisionAnalysisComponentResult(
            status=(
                ComponentStatus.COMPLETED_WITH_WARNINGS
                if warnings
                else ComponentStatus.COMPLETED
            ),
            scenario_packet=packet,
            analysis=analysis,
            artifacts=(draft,),
            warnings=tuple(warnings),
            runtime_events=tuple(events),
        )

    @staticmethod
    def _failed_safe(message: str) -> DecisionAnalysisComponentResult:
        return DecisionAnalysisComponentResult(
            status=ComponentStatus.FAILED_SAFE,
            runtime_events=(
                RuntimeEvent(
                    event_type="DECISION_ANALYSIS_FAILED_SAFE",
                    message=message,
                ),
            ),
        )
