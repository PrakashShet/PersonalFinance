from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from models.base import BaseModel


@dataclass
class NetWorthSnapshot(BaseModel):
    id: Optional[int] = None
    snapshot_date: str = ""
    total_assets: float = 0.0
    total_liabilities: float = 0.0
    net_worth: float = 0.0
    breakdown_json: Optional[str] = None
