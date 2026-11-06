"""Backward-compatible re-exports — prefer direct module imports in new code."""
from __future__ import annotations

from repositories.goal_holding_repo import GoalHoldingRepository
from repositories.goal_repo import GoalRepository
from repositories.income_entry_repo import IncomeEntryRepository
from repositories.income_repo import IncomeRepository
from repositories.liability_repo import LiabilityRepository

__all__ = [
    "IncomeRepository",
    "IncomeEntryRepository",
    "LiabilityRepository",
    "GoalRepository",
    "GoalHoldingRepository",
]
