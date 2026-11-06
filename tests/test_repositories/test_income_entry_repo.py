"""Repository tests for monthly income entries."""
from __future__ import annotations

from models.income import IncomeSource
from models.income_entry import IncomeEntry
from repositories.income_entry_repo import IncomeEntryRepository
from repositories.income_repo import IncomeRepository


def test_income_entry_repo_list_and_lookup(temp_db):
    source_repo = IncomeRepository(temp_db)
    source_id = source_repo.insert(IncomeSource(name="Salary", source_type="salary"))

    entry_repo = IncomeEntryRepository(temp_db)
    entry_repo.insert(IncomeEntry(income_source_id=source_id, period_month="2026-04", actual_amount=70_000.0))
    entry_repo.insert(IncomeEntry(income_source_id=source_id, period_month="2026-05", actual_amount=75_000.0))

    entries = entry_repo.list_for_source(source_id)
    assert len(entries) == 2
    assert entries[0].period_month == "2026-05"  # ORDER BY period_month DESC

    may_entry = entry_repo.get_for_period(source_id, "2026-05")
    assert may_entry is not None
    assert may_entry.actual_amount == 75_000.0

    assert entry_repo.total_received("2026-05") == 75_000.0
    assert entry_repo.get_for_period(source_id, "2026-06") is None
