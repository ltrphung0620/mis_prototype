"""Port for an authorized Banking precheck submission adapter."""

from typing import Protocol

from opc_mis.domain.banking_precheck_execution_models import (
    AuthorizedActionPermit,
    BankingPrecheckRawResponse,
    BankingPrecheckRequest,
)


class BankingPrecheckAdapter(Protocol):
    """Submit one fully bound request after Governance authorization."""

    @property
    def adapter_id(self) -> str:
        """Return the stable adapter implementation identifier."""
        ...

    @property
    def configuration_hash(self) -> str:
        """Return the canonical server-side configuration identity."""
        ...

    async def submit(
        self,
        request: BankingPrecheckRequest,
        authorization: AuthorizedActionPermit,
    ) -> BankingPrecheckRawResponse:
        """Return one raw provider result without normalizing business meaning."""
        ...

