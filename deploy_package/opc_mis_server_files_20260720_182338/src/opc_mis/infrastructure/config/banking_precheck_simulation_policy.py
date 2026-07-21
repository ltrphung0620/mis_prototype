"""Validated loader for server-owned Banking precheck simulation scenarios."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from opc_mis.domain.banking_precheck_execution_models import (
    BankingPrecheckSimulationPolicy,
    BankingPrecheckSimulationPolicyDocument,
)


class BankingPrecheckSimulationPolicyError(ValueError):
    """Raised when the simulation configuration is unavailable or invalid."""


def canonical_simulation_policy_hash(
    document: BankingPrecheckSimulationPolicyDocument,
) -> str:
    """Hash typed policy semantics independently of source JSON formatting."""
    canonical = json.dumps(
        document.model_dump(mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


class BankingPrecheckSimulationPolicyLoader:
    """Load a typed deterministic policy from a server-selected path."""

    def load(self, path: Path) -> BankingPrecheckSimulationPolicy:
        """Read, validate, and attach a canonical SHA-256 configuration hash."""
        resolved = path.resolve()
        if not resolved.is_file():
            raise BankingPrecheckSimulationPolicyError(
                f"Banking precheck simulation policy does not exist: {resolved}"
            )
        try:
            raw: Any = json.loads(resolved.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise BankingPrecheckSimulationPolicyError(
                f"Unable to read Banking precheck simulation policy {resolved}: {exc}"
            ) from exc
        try:
            document = BankingPrecheckSimulationPolicyDocument.model_validate(raw)
        except ValidationError as exc:
            raise BankingPrecheckSimulationPolicyError(
                f"Invalid Banking precheck simulation policy {resolved}: {exc}"
            ) from exc
        return BankingPrecheckSimulationPolicy(
            **document.model_dump(mode="python"),
            configuration_hash=canonical_simulation_policy_hash(document),
        )

