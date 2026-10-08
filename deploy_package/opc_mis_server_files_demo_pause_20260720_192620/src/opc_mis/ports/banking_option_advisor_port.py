"""Port for optional, non-authoritative Banking option advice."""

from typing import Protocol

from opc_mis.domain.banking_models import BankingAdviceComposition, BankingAdvisorInput


class BankingOptionAdvisorPort(Protocol):
    """Phrase deterministic options without selecting or executing any option."""

    async def compose(self, payload: BankingAdvisorInput) -> BankingAdviceComposition:
        """Return guarded advisory prose or a safe deterministic composition."""
        ...
