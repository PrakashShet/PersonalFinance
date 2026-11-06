"""Input validators used by forms and services."""
from __future__ import annotations

from datetime import datetime


def is_positive_number(value) -> bool:
    try:
        return float(value) > 0
    except (TypeError, ValueError):
        return False


def is_non_negative(value) -> bool:
    try:
        return float(value) >= 0
    except (TypeError, ValueError):
        return False


def is_valid_date(date_str: str, fmt: str = "%Y-%m-%d") -> bool:
    try:
        datetime.strptime(date_str, fmt)
        return True
    except (TypeError, ValueError):
        return False


def is_non_empty_str(value) -> bool:
    return isinstance(value, str) and value.strip() != ""
