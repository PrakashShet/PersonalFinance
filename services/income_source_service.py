"""CRUD for income sources; monthly entries delegate to IncomeService."""
from __future__ import annotations

from typing import Callable

from models.income import IncomeSource
from models.income_entry import IncomeEntry
from repositories.income_entry_repo import IncomeEntryRepository
from repositories.income_repo import IncomeRepository
from services.income_service import IncomeService


class IncomeSourceService:
    def __init__(
        self,
        source_repo: IncomeRepository,
        entry_repo: IncomeEntryRepository,
        income_service: IncomeService,
        on_change: Callable[[str], None] | None = None,
    ) -> None:
        self._source_repo = source_repo
        self._entry_repo = entry_repo
        self._income = income_service
        self._on_change = on_change

    def list_active(self) -> list[IncomeSource]:
        return self._source_repo.list_active()

    def list_all(self, include_inactive: bool = False) -> list[IncomeSource]:
        if include_inactive:
            return self._source_repo.list_all("1 = 1 ORDER BY is_active DESC, id")
        return self._source_repo.list_active()

    def get(self, source_id: int) -> IncomeSource | None:
        return self._source_repo.get_by_id(source_id)

    def create(self, source: IncomeSource) -> int:
        if not source.name.strip():
            raise ValueError("Income source name is required")
        new_id = self._source_repo.insert(source)
        if self._on_change is not None:
            self._on_change("income_sources")
        return new_id

    def update(self, source: IncomeSource) -> None:
        if source.id is None:
            raise ValueError("Cannot update an income source without an id")
        if not source.name.strip():
            raise ValueError("Income source name is required")
        self._source_repo.update(source)
        if self._on_change is not None:
            self._on_change("income_sources")

    def delete(self, source_id: int) -> None:
        self._source_repo.delete(source_id)
        if self._on_change is not None:
            self._on_change("income_sources")

    def toggle_active(self, source: IncomeSource) -> None:
        source.is_active = 0 if source.is_active else 1
        self._source_repo.update(source)
        if self._on_change is not None:
            self._on_change("income_sources")

    # --- entries (delegate) -------------------------------------------------
    def list_entries(self, source_id: int) -> list[IncomeEntry]:
        return self._income.list_entries(source_id)

    def record_month(self, source: IncomeSource, **kwargs) -> IncomeEntry:
        entry = self._income.record_month(source, **kwargs)
        if self._on_change is not None:
            self._on_change("income_entries")
            self._on_change("transactions")
            self._on_change("accounts")
        return entry

    def delete_entry(self, entry_id: int) -> None:
        self._income.delete_entry(entry_id)
        if self._on_change is not None:
            self._on_change("income_entries")
            self._on_change("transactions")
            self._on_change("accounts")

    def expected_this_month(self, sources: list[IncomeSource]) -> float:
        return self._income.expected_this_month(sources)

    def pending_sources(
        self, sources: list[IncomeSource], period_month: str
    ) -> list[IncomeSource]:
        return self._income.pending_sources(sources, period_month)

    def net_monthly(self, source: IncomeSource) -> float:
        return self._income.net_monthly(source)

    def gross_monthly(self, source: IncomeSource) -> float:
        return self._income.gross_monthly(source)

    def deductions_monthly(self, source: IncomeSource) -> float:
        return self._income.deductions_monthly(source)

    def total_received(self, period_month: str) -> float:
        return self._income.total_received(period_month)

    def has_logged(self, source_id: int, period_month: str) -> bool:
        return self._income.has_logged(source_id, period_month)

    def is_recurring_monthly(self, source: IncomeSource) -> bool:
        return self._income.is_recurring_monthly(source)
