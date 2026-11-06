"""Per-month actual income logged against an income source."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from models.base import BaseModel


@dataclass
class IncomeEntry(BaseModel):
    id: Optional[int] = None
    income_source_id: int = 0
    period_month: str = ""           # 'YYYY-MM'
    expected_amount: Optional[float] = None
    actual_amount: float = 0.0
    received_date: Optional[str] = None  # 'YYYY-MM-DD'
    account_id: Optional[int] = None
    transaction_id: Optional[int] = None
    notes: Optional[str] = None
    created_at: Optional[str] = None
