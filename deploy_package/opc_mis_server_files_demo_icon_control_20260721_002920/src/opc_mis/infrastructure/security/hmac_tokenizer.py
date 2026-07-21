"""HMAC-SHA256 contextual tokenization without raw-value persistence."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import unicodedata

from opc_mis.domain.masking_models import TokenizationContext

_SAFE_PREFIX = re.compile(r"[^A-Z0-9]+")


class TokenizationError(ValueError):
    """Raised without echoing the secret key or raw input value."""


class HmacContextualTokenizer:
    """Deterministic pseudonymization scoped by provider, purpose, field, and key."""

    __slots__ = ("__secret_key", "_token_bytes")

    def __init__(self, *, secret_key: bytes, token_bytes: int = 16) -> None:
        if not isinstance(secret_key, bytes) or len(secret_key) < 32:
            raise TokenizationError("tokenization secret_key must contain at least 32 bytes")
        if not isinstance(token_bytes, int) or isinstance(token_bytes, bool):
            raise TokenizationError("token_bytes must be an integer")
        if not 16 <= token_bytes <= hashlib.sha256().digest_size:
            raise TokenizationError("token_bytes must be between 16 and 32")
        self.__secret_key = secret_key
        self._token_bytes = token_bytes

    def __repr__(self) -> str:
        """Return a representation that cannot reveal key material."""
        return (
            f"{type(self).__name__}(algorithm='HMAC-SHA256', "
            f"token_bytes={self._token_bytes})"
        )

    def tokenize(self, value: str, context: TokenizationContext) -> str:
        """Create a stable Base32 token from a length-safe canonical message."""
        if not isinstance(value, str) or not value:
            raise TokenizationError("tokenization input must be a non-empty string")
        canonical_value = unicodedata.normalize("NFC", value)
        namespace = json.dumps(
            [
                context.provider,
                context.purpose,
                context.field_type,
                context.key_version,
            ],
            ensure_ascii=False,
            separators=(",", ":"),
        )
        message = json.dumps(
            [namespace, canonical_value],
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        digest = hmac.new(self.__secret_key, message, hashlib.sha256).digest()
        encoded = base64.b32encode(digest[: self._token_bytes]).decode("ascii").rstrip("=")
        field_prefix = _SAFE_PREFIX.sub("-", context.field_type.upper()).strip("-")
        if not field_prefix:
            field_prefix = "FIELD"
        key_version = _SAFE_PREFIX.sub("-", context.key_version.upper()).strip("-")
        if not key_version:
            raise TokenizationError("key_version must contain an alphanumeric character")
        return f"TOK-{field_prefix}-{key_version}-{encoded}"

