"""Deterministic exact-identifier and pattern redaction for free text."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Mapping

from opc_mis.domain.masking_models import RedactionFinding, RedactionResult


class RedactionError(ValueError):
    """Raised when text cannot be sanitized without exposing raw contents."""


class DeterministicFreeTextRedactor:
    """Redact known identifiers first, then conservative structured patterns."""

    __slots__ = ("_patterns",)

    algorithm_version = "v1"

    def __init__(self) -> None:
        self._patterns = (
            (
                "SECRET",
                re.compile(
                    r"(?i)\b(?:api[_ -]?key|access[_ -]?token|bearer)\s*[:=]?\s*[^\s,;]+"
                ),
            ),
            (
                "EMAIL",
                re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b"),
            ),
            (
                "PHONE",
                re.compile(r"(?<!\w)(?:\+?84|0)(?:[ .-]?\d){8,10}(?!\w)"),
            ),
            (
                "ACCOUNT",
                re.compile(r"(?i)\b(?:account|acct)[_ -]?[A-Z0-9-]{4,}\b"),
            ),
            (
                "URL",
                re.compile(r"(?i)\b(?:https?|file)://[^\s,;]+"),
            ),
            (
                "WINDOWS_PATH",
                re.compile(r"(?i)(?:[A-Z]:\\|\\\\)[^\s,;]+"),
            ),
            (
                "ABSOLUTE_PATH",
                re.compile(r"(?<!\w)/(?:[^/\s]+/)*[^/\s,;]+"),
            ),
        )

    def redact(
        self,
        text: str,
        *,
        exact_identifiers: Mapping[str, str] | None = None,
    ) -> RedactionResult:
        """Return sanitized text and category counts, never matched raw values."""
        if not isinstance(text, str):
            raise RedactionError("redaction input must be text")
        sanitized = text
        counts: Counter[str] = Counter()
        identifiers = exact_identifiers or {}
        for category, raw_value in sorted(
            identifiers.items(),
            key=lambda item: (-len(item[1]), item[0]),
        ):
            if not isinstance(raw_value, str) or not raw_value:
                raise RedactionError("exact identifier values must be non-empty text")
            pattern = re.compile(re.escape(raw_value), flags=re.IGNORECASE)
            sanitized, count = pattern.subn(f"[{category.upper()}_REDACTED]", sanitized)
            counts[f"EXACT_{category.upper()}"] += count
        for category, pattern in self._patterns:
            sanitized, count = pattern.subn(f"[{category}_REDACTED]", sanitized)
            counts[category] += count
        findings = tuple(
            RedactionFinding(category=category, count=count)
            for category, count in sorted(counts.items())
            if count
        )
        return RedactionResult(
            text=sanitized,
            findings=findings,
            algorithm_version=self.algorithm_version,
        )
