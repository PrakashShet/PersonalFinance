"""Repository CRUD smoke tests for income sources."""
from __future__ import annotations

from models.income import IncomeSource
from repositories.income_repo import IncomeRepository


def test_income_repo_insert_and_list_active(temp_db):
    repo = IncomeRepository(temp_db)
    repo.insert(IncomeSource(name="Salary", source_type="salary", is_active=1))
    repo.insert(IncomeSource(name="Old Freelance Gig", source_type="freelance", is_active=0))

    active = repo.list_active()
    assert len(active) == 1
    assert active[0].name == "Salary"
