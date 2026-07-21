"""Pure conversion of supported TeamPack date values into calendar dates."""

from datetime import date, datetime, timedelta
from math import isfinite
from numbers import Real
from typing import Any

EXCEL_EPOCH = datetime(1899, 12, 30)


def normalize_date(value: Any) -> date:
    """Normalize date/datetime, ISO text, or positive Excel serial values."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, bool):
        raise ValueError("boolean is not a supported date value")
    if isinstance(value, Real):
        serial = float(value)
        if not isfinite(serial) or serial <= 0:
            raise ValueError("Excel date serial must be positive and finite")
        return (EXCEL_EPOCH + timedelta(days=serial)).date()
    if isinstance(value, str):
        normalized = value.strip()
        if not normalized:
            raise ValueError("date text must not be blank")
        try:
            return datetime.fromisoformat(normalized.replace("Z", "+00:00")).date()
        except ValueError as exc:
            raise ValueError(f"unsupported ISO date value: {value!r}") from exc
    raise ValueError(f"unsupported date type: {type(value).__name__}")


def inclusive_days(start: date, end: date) -> int:
    """Return inclusive calendar duration and reject reverse intervals."""
    duration = (end - start).days + 1
    if duration < 1:
        raise ValueError("end date must not be before start date")
    return duration
