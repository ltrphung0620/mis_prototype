"""Port for bounded, evidence-grounded Decision analysis composition."""

from typing import Protocol

from opc_mis.domain.decision_models import (
    AIDecisionComposition,
    DecisionScenarioPacket,
)


class DecisionAnalysisPort(Protocol):
    """Propose a Decision analysis from an exact deterministic scenario packet."""

    async def compose(self, payload: DecisionScenarioPacket) -> AIDecisionComposition:
        """Return a guarded model proposal or a conservative deterministic fallback."""
        ...
