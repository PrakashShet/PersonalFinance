from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from models.base import BaseModel


@dataclass
class Reminder(BaseModel):
    id: Optional[int] = None
    title: str = ""
    due_date: str = ""
    amount: Optional[float] = None
    holding_id: Optional[int] = None
    liability_id: Optional[int] = None
    is_done: int = 0
    notes: Optional[str] = None
