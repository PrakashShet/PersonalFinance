from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from models.base import BaseModel


@dataclass
class IncomeSource(BaseModel):
    id: Optional[int] = None
    name: str = ""
    source_type: str = "salary"
    is_recurring: int = 1
    expected_amount: Optional[float] = None
    frequency: Optional[str] = None
    employer: Optional[str] = None
    # salary breakdown
    basic: Optional[float] = None
    hra: Optional[float] = None
    special_allow: Optional[float] = None
    pf_employee: Optional[float] = None
    pf_employer: Optional[float] = None
    professional_tax: Optional[float] = None
    tds: Optional[float] = None
    notes: Optional[str] = None
    is_active: int = 1
    # Account this income is deposited into (nullable)
    deposit_account_id: Optional[int] = None
    created_at: Optional[str] = None
