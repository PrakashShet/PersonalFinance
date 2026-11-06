from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from models.base import BaseModel


@dataclass
class Transaction(BaseModel):
    id: Optional[int] = None
    txn_date: str = ""
    txn_type: str = "expense"
    amount: float = 0.0
    account_id: int = 0
    counter_account_id: Optional[int] = None
    category_id: Optional[int] = None
    holding_id: Optional[int] = None
    income_source_id: Optional[int] = None
    description: Optional[str] = None
    reference_no: Optional[str] = None
    tags: Optional[str] = None
    created_at: Optional[str] = None
