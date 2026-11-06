"""Shared form validation helpers built on utils.validators."""
from __future__ import annotations

from utils.validators import is_non_empty_str, is_positive_number, is_valid_date


def validation_error(field_label: str, value, *, kind: str = "text") -> str | None:
    """Return an error message, or None if the value is valid."""
    if kind == "text":
        if not is_non_empty_str(value):
            return f"{field_label} is required."
    elif kind == "money":
        if not is_positive_number(value):
            return f"{field_label} must be greater than zero."
    elif kind == "date":
        if not is_valid_date(str(value)):
            return f"{field_label} must be a valid date (YYYY-MM-DD)."
    return None
