"""Normalization helpers at the Excel boundary."""

from contextlib import suppress
from datetime import date, datetime
from decimal import Decimal
from math import isfinite
from typing import Any

import pandas as pd

IDENTIFIER_FIELDS = {
    "account_id",
    "alert_id",
    "company_id",
    "contract_id",
    "credit_case_id",
    "customer_id",
    "invoice_id",
    "order_id",
    "service_id",
    "txn_id",
}


def json_safe(value: Any) -> Any:
    """Convert pandas/numpy values into deterministic JSON-safe Python values."""
    if value is None:
        return None
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if isinstance(value, (set, frozenset)):
        normalized = [json_safe(item) for item in value]
        return sorted(normalized, key=repr)
    if isinstance(value, pd.DataFrame):
        return json_safe(value.to_dict(orient="records"))
    if isinstance(value, pd.Series):
        return json_safe(value.to_list())
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime().isoformat()
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if hasattr(value, "item") and not isinstance(value, (str, bytes, dict, list, tuple)):
        with suppress(TypeError, ValueError):
            value = value.item()
            return json_safe(value)
    if isinstance(value, float) and not isfinite(value):
        return None
    if isinstance(value, Decimal):
        return float(value)
    return value


def normalize_value(field: str, value: Any) -> Any:
    """Normalize whitespace and identifiers without inventing missing values."""
    normalized = json_safe(value)
    if isinstance(normalized, str):
        normalized = " ".join(normalized.split())
        if field in IDENTIFIER_FIELDS:
            normalized = normalized.upper()
    return normalized


def display_value(value: Any) -> Any:
    """Keep the original cell value in JSON-safe form for evidence display."""
    return json_safe(value)
