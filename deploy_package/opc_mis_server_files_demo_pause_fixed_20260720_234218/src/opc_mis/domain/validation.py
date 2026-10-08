"""Infrastructure-neutral validation predicates shared by Planner rules."""

from datetime import date, datetime
from numbers import Real
from typing import Any


def valid_identifier(value: Any) -> bool:
    """Accept non-empty, whitespace-free identifiers without demo-prefix assumptions."""
    return isinstance(value, str) and bool(value) and not any(char.isspace() for char in value)


def valid_numeric(value: Any) -> bool:
    """Accept real numbers but not booleans."""
    return isinstance(value, Real) and not isinstance(value, bool)


def valid_date_like(value: Any) -> bool:
    """Accept ISO dates, datetime values, or positive Excel serial numbers."""
    if isinstance(value, (date, datetime)):
        return True
    if valid_numeric(value):
        return float(value) > 0
    if isinstance(value, str):
        try:
            datetime.fromisoformat(value)
        except ValueError:
            return False
        return True
    return False
