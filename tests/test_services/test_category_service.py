"""Tests for CategoryService (thin read-only wrapper over CategoryRepository)."""
from __future__ import annotations

from repositories.category_repo import CategoryRepository
from services.category_service import CategoryService


def test_category_service_wraps_repo(temp_db):
    repo = CategoryRepository(temp_db)
    repo.ensure("Groceries", "expense")
    repo.ensure("Salary", "income")

    svc = CategoryService(repo)

    expense = svc.list_by_kind("expense")
    assert expense[0][1] == "Groceries"

    labeled = svc.list_all_labeled()
    assert ("Groceries", "expense") in [(name, kind) for _, name, kind in labeled]

    name_map = svc.name_map()
    assert "Groceries" in name_map.values()
