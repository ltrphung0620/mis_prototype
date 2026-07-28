"""Typed loader for the server-owned final Decision Governance policy."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from opc_mis.domain.decision_governance_models import (
    DecisionGovernancePolicy,
    DecisionGovernancePolicyDocument,
)


class DecisionGovernancePolicyError(ValueError):
    """Raised when the configured final Decision policy is missing or invalid."""


def canonical_decision_governance_hash(
    document: DecisionGovernancePolicyDocument,
) -> str:
    """Hash validated semantics independently of JSON formatting and key order."""
    canonical = json.dumps(
        document.model_dump(mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


class DecisionGovernancePolicyLoader:
    """Load a server-selected policy path; public clients never choose this path."""

    def load(self, path: Path) -> DecisionGovernancePolicy:
        resolved = path.resolve()
        if not resolved.is_file():
            raise DecisionGovernancePolicyError(
                f"Decision Governance policy does not exist: {resolved}"
            )
        try:
            raw: Any = json.loads(resolved.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise DecisionGovernancePolicyError(
                f"Unable to read Decision Governance policy {resolved}: {exc}"
            ) from exc
        try:
            document = DecisionGovernancePolicyDocument.model_validate(raw)
        except ValidationError as exc:
            raise DecisionGovernancePolicyError(
                f"Invalid Decision Governance policy {resolved}: {exc}"
            ) from exc
        return DecisionGovernancePolicy(
            **document.model_dump(mode="python"),
            policy_hash=canonical_decision_governance_hash(document),
        )
