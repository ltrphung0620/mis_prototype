"""Port for deterministic contextual tokenization at trust boundaries."""

from typing import Protocol

from opc_mis.domain.masking_models import TokenizationContext


class TokenizationService(Protocol):
    """Create a non-reversible token without exposing secret key material."""

    def tokenize(self, value: str, context: TokenizationContext) -> str:
        """Tokenize one exact value within an explicit provider-purpose namespace."""
        ...

