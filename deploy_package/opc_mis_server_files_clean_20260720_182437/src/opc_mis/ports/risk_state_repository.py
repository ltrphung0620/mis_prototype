"""Risk checkpoint persistence port owned by workflow orchestration."""

from typing import Protocol

from opc_mis.domain.risk_models import RiskRunState


class RiskStateRepository(Protocol):
    """Store the latest resumable state for each evaluation case."""

    async def save(self, state: RiskRunState) -> None:
        """Persist or replace the current Risk checkpoint."""
        ...

    async def get_by_case(self, evaluation_case_id: str) -> RiskRunState | None:
        """Return the latest checkpoint for an evaluation case."""
        ...
