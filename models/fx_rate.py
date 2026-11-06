from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from models.base import BaseModel


@dataclass
class FxRate(BaseModel):
    currency: str = ""            # ISO code, e.g. "USD"
    rate_to_inr: float = 0.0      # 1 unit of currency = this many rupees
    as_of: Optional[str] = None   # YYYY-MM-DD
    updated_at: Optional[str] = None
