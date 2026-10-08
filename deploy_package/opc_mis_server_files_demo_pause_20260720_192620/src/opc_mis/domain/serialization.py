"""Strict canonical JSON conversion for domain hashing and identifiers."""

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from math import isfinite
from typing import Any


def json_safe(value: Any) -> Any:
    """Recursively convert normalized domain values to strict JSON primitives."""
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if isfinite(value) else None
    if isinstance(value, Decimal):
        converted = float(value)
        return converted if isfinite(converted) else None
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Enum):
        return json_safe(value.value)
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if isinstance(value, (set, frozenset)):
        converted = [json_safe(item) for item in value]
        return sorted(converted, key=repr)
    raise TypeError(f"Unsupported domain JSON value: {type(value).__name__}")
