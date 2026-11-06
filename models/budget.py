from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from models.base import BaseModel


@dataclass
class Budget(BaseModel):
    """A spending limit for one expense category, per month or per year."""

    id: Optional[int] = None
    category_id: Optional[int] = None
    period: str = "monthly"            # monthly | yearly
    amount: float = 0.0                # the limit, in rupees per period
    notes: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
