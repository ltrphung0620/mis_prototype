"""Process-local Risk checkpoint adapter used by the prototype runtime."""

from opc_mis.domain.risk_models import RiskRunState


class InMemoryRiskStateRepository:
    """Keep resumable Risk states behind the workflow persistence port."""

    def __init__(self) -> None:
        self._states: dict[str, RiskRunState] = {}

    async def save(self, state: RiskRunState) -> None:
        """Persist the latest checkpoint for one case."""
        self._states[state.evaluation_case_id] = state

    async def get_by_case(self, evaluation_case_id: str) -> RiskRunState | None:
        """Return the current checkpoint, if Risk has started."""
        return self._states.get(evaluation_case_id)
