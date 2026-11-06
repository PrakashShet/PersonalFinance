"""Polymorphic holding — single table for all investment types.

Fields that don't apply to a given type stay None. Service layer
(`investment_service`) handles type-specific calculations.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from models.base import BaseModel


@dataclass
class Holding(BaseModel):
    id: Optional[int] = None
    name: str = ""
    holding_type: str = ""
    institution: Optional[str] = None
    folio_or_account: Optional[str] = None
    purchase_date: Optional[str] = None

    # Universal valuation
    invested_amount: float = 0.0
    current_value: float = 0.0
    quantity: Optional[float] = None
    avg_price: Optional[float] = None
    current_price: Optional[float] = None

    # Stocks / ETFs
    symbol: Optional[str] = None
    exchange: Optional[str] = None
    market_cap: Optional[str] = None
    sector: Optional[str] = None

    # FD
    interest_rate: Optional[float] = None
    maturity_date: Optional[str] = None
    payout_frequency: Optional[str] = None
    auto_renew: int = 0

    # Insurance
    sum_assured: Optional[float] = None
    premium_amount: Optional[float] = None
    premium_due_date: Optional[str] = None
    policy_term_years: Optional[int] = None

    # Gold
    weight_grams: Optional[float] = None
    purity: Optional[str] = None
    making_charges: Optional[float] = None

    # SIP
    sip_amount: Optional[float] = None
    sip_day_of_month: Optional[int] = None

    linked_account_id: Optional[int] = None
    notes: Optional[str] = None
    is_active: int = 1
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    # Computed helpers
    @property
    def unrealized_pnl(self) -> float:
        return self.current_value - self.invested_amount

    @property
    def return_pct(self) -> float:
        if self.invested_amount <= 0:
            return 0.0
        return (self.unrealized_pnl / self.invested_amount) * 100.0
