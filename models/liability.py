from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from models.base import BaseModel


@dataclass
class Liability(BaseModel):
    id: Optional[int] = None
    name: str = ""
    liability_type: str = ""
    lender: Optional[str] = None
    principal: float = 0.0
    outstanding: float = 0.0
    interest_rate: Optional[float] = None
    emi_amount: Optional[float] = None
    tenure_months: Optional[int] = None
    remaining_months: Optional[int] = None
    start_date: Optional[str] = None
    next_due_date: Optional[str] = None
    # Account this liability is paid from / associated with (nullable)
    account_id: Optional[int] = None
    notes: Optional[str] = None
    is_active: int = 1
    created_at: Optional[str] = None
