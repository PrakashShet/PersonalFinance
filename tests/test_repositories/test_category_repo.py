"""Repository tests for the (model-less) categories table.

`temp_db` has an empty categories table (no seed data), so every test goes
through `ensure()` to create rows.
"""
from __future__ import annotations

from repositories.category_repo import CategoryRepository


def test_category_repo_ensure_and_lookup(temp_db):
    repo = CategoryRepository(temp_db)
    cat_id = repo.ensure("Groceries", "expense")
    assert cat_id is not None

    # Calling ensure again returns the same id, doesn't duplicate.
    again = repo.ensure("Groceries", "expense")
    assert again == cat_id

    repo.ensure("Salary", "income")

    expense_cats = repo.list_by_kind("expense")
    assert any(r["name"] == "Groceries" for r in expense_cats)

    income_cats = repo.list_by_kind("income")
    assert any(r["name"] == "Salary" for r in income_cats)

    assert repo.get_id_by_name("Groceries", "expense") == cat_id
    assert repo.get_id_by_name("Nonexistent", "expense") is None

    name_map = repo.name_map()
    assert name_map[cat_id] == "Groceries"

    all_labeled = repo.list_all()
    kinds = {(r["name"], r["kind"]) for r in all_labeled}
    assert ("Groceries", "expense") in kinds
    assert ("Salary", "income") in kinds
