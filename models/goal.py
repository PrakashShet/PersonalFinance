from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from models.base import BaseModel


@dataclass
class Goal(BaseModel):
    id: Optional[int] = None
    name: str = ""
    target_amount: float = 0.0
    current_amount: float = 0.0
    target_date: Optional[str] = None
    priority: int = 3
    expected_return: float = 0.10
    inflation_rate: float = 0.06
    status: str = "active"
    notes: Optional[str] = None
    created_at: Optional[str] = None

    @property
    def progress_pct(self) -> float:
        if self.target_amount <= 0:
            return 0.0
        return min(100.0, (self.current_amount / self.target_amount) * 100.0)
