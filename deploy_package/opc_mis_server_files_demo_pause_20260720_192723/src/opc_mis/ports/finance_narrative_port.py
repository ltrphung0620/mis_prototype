"""Port for non-authoritative Finance narrative composition."""

from typing import Protocol

from opc_mis.domain.finance_models import FinanceComposerInput, FinanceNarrativeComposition


class FinanceNarrativePort(Protocol):
    """Compose text from verified facts; never calculate or decide business outcomes."""

    async def compose(self, payload: FinanceComposerInput) -> FinanceNarrativeComposition:
        """Return a structured narrative or a deterministic fallback composition."""
        ...
