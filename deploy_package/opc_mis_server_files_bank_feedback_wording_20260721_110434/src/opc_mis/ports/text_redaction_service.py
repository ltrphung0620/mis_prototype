"""Port for deterministic free-text identifier redaction."""

from collections.abc import Mapping
from typing import Protocol

from opc_mis.domain.masking_models import RedactionResult


class TextRedactionService(Protocol):
    """Sanitize free text without returning matched raw values."""

    def redact(
        self,
        text: str,
        *,
        exact_identifiers: Mapping[str, str] | None = None,
    ) -> RedactionResult:
        """Return sanitized text and aggregate finding counts."""
        ...

