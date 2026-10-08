"""Side-effect-free assembly of the detailed Founder-facing Decision Card."""

from pydantic import ValidationError

from opc_mis.business.agents.decision.card_context import (
    DecisionCardContextError,
    DecisionCardContextLoader,
)
from opc_mis.domain.artifacts import ArtifactDraft
from opc_mis.domain.components import ExecutionContext
from opc_mis.domain.decision_analysis import (
    DecisionAnalysisBoundaryError,
    assemble_decision_card,
)
from opc_mis.domain.decision_models import (
    DecisionCardComponentResult,
    DecisionRecommendation,
)
from opc_mis.domain.enums import ArtifactType, ComponentStatus
from opc_mis.domain.events import RuntimeEvent


class DecisionCardAssembler:
    """Create a detailed Card without requesting approval or executing actions."""

    component_id = "DECISION_CARD_ASSEMBLER"

    def __init__(self, *, context_loader: DecisionCardContextLoader) -> None:
        self._context_loader = context_loader

    async def execute(self, context: ExecutionContext) -> DecisionCardComponentResult:
        try:
            card_context = await self._context_loader.load(context)
            card = assemble_decision_card(
                packet=card_context.packet,
                analysis_artifact=card_context.analysis_artifact,
                analysis=card_context.analysis,
            )
        except (
            DecisionAnalysisBoundaryError,
            DecisionCardContextError,
            ValidationError,
            ValueError,
        ) as exc:
            return self._failed_safe(str(exc))

        draft = ArtifactDraft(
            artifact_type=ArtifactType.DECISION_CARD,
            evaluation_case_id=card.evaluation_case_id,
            producer=self.component_id,
            payload=card.model_dump(mode="json"),
            evidence_refs=card_context.analysis_artifact.evidence_refs,
            identity_inputs={
                "ai_analysis_artifact": card.ai_analysis_artifact.model_dump(
                    mode="json"
                ),
                "ai_analysis_id": card.ai_analysis_id,
                "internal_decision_package_artifact": (
                    card.internal_decision_package_artifact.model_dump(mode="json")
                ),
                "final_risk_artifact": card.final_risk_artifact.model_dump(mode="json"),
            },
        )
        warnings = (
            ("DECISION_NOT_EVALUABLE",)
            if card.recommendation is DecisionRecommendation.NOT_EVALUABLE
            else ()
        )
        return DecisionCardComponentResult(
            status=(
                ComponentStatus.COMPLETED_WITH_WARNINGS
                if warnings
                else ComponentStatus.COMPLETED
            ),
            decision_card=card,
            artifacts=(draft,),
            warnings=warnings,
            runtime_events=(
                RuntimeEvent(
                    event_type="DECISION_CARD_CREATED",
                    message=(
                        "Decision assembled a detailed evidence-bound Card; Founder "
                        "approval and external actions remain separate workflow steps."
                    ),
                    metadata={
                        "decision_card_id": card.decision_card_id,
                        "recommendation": card.recommendation.value,
                        "condition_count": len(card.conditions),
                        "not_evaluable": (
                            card.recommendation is DecisionRecommendation.NOT_EVALUABLE
                        ),
                    },
                ),
            ),
        )

    @staticmethod
    def _failed_safe(message: str) -> DecisionCardComponentResult:
        return DecisionCardComponentResult(
            status=ComponentStatus.FAILED_SAFE,
            runtime_events=(
                RuntimeEvent(
                    event_type="DECISION_CARD_FAILED_SAFE",
                    message=message,
                ),
            ),
        )
