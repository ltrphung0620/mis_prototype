"""Validated loader for the server-owned outbound data-protection policy."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from opc_mis.domain.masking_models import (
    MaskingPolicyDocument,
    masking_policy_document_sha256,
)


class MaskingPolicyConfigurationError(ValueError):
    """Raised without exposing secret material when policy loading fails."""


@dataclass(frozen=True)
class LoadedMaskingPolicy:
    """Typed policy plus a canonical, non-secret configuration identity."""

    document: MaskingPolicyDocument
    configuration_hash: str


def canonical_masking_policy_hash(document: MaskingPolicyDocument) -> str:
    """Hash typed semantics independently of source JSON formatting."""
    return masking_policy_document_sha256(document)


class MaskingPolicyLoader:
    """Load and validate one server-selected policy file."""

    def load(self, path: Path) -> LoadedMaskingPolicy:
        """Return a typed fail-closed policy and its canonical hash."""
        resolved = path.resolve()
        if not resolved.is_file():
            raise MaskingPolicyConfigurationError(
                f"Masking policy does not exist: {resolved}"
            )
        try:
            raw: Any = json.loads(resolved.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise MaskingPolicyConfigurationError(
                f"Unable to read the configured masking policy: {type(exc).__name__}."
            ) from exc
        try:
            document = MaskingPolicyDocument.model_validate(raw)
        except ValidationError as exc:
            raise MaskingPolicyConfigurationError(
                "The configured masking policy is invalid."
            ) from exc
        return LoadedMaskingPolicy(
            document=document,
            configuration_hash=canonical_masking_policy_hash(document),
        )
