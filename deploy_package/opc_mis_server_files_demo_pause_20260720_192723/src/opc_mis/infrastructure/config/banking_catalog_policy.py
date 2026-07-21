"""Validated loader for the server-owned Banking catalog mapping policy."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from opc_mis.domain.banking_models import (
    BankingCatalogPolicy,
    BankingCatalogPolicyDocument,
)


class BankingCatalogPolicyError(ValueError):
    """Raised when the configured Banking mapping policy is unavailable or invalid."""


def canonical_policy_hash(document: BankingCatalogPolicyDocument) -> str:
    """Hash validated policy semantics independently of JSON formatting and key order."""
    canonical = json.dumps(
        document.model_dump(mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


class BankingCatalogPolicyLoader:
    """Load a typed mapping policy without accepting client-selected paths."""

    def load(self, path: Path) -> BankingCatalogPolicy:
        """Read, validate, and attach a canonical SHA-256 identity to one policy."""
        resolved = path.resolve()
        if not resolved.is_file():
            raise BankingCatalogPolicyError(
                f"Banking catalog policy does not exist: {resolved}"
            )
        try:
            raw: Any = json.loads(resolved.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise BankingCatalogPolicyError(
                f"Unable to read Banking catalog policy {resolved}: {exc}"
            ) from exc
        try:
            document = BankingCatalogPolicyDocument.model_validate(raw)
        except ValidationError as exc:
            raise BankingCatalogPolicyError(
                f"Invalid Banking catalog policy {resolved}: {exc}"
            ) from exc
        return BankingCatalogPolicy(
            **document.model_dump(mode="python"),
            policy_hash=canonical_policy_hash(document),
        )
