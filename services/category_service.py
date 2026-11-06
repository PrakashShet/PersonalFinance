"""Read-only access to transaction categories for the UI layer."""
from __future__ import annotations

from repositories.category_repo import CategoryRepository


class CategoryService:
    def __init__(self, repo: CategoryRepository) -> None:
        self._repo = repo

    def list_by_kind(self, kind: str) -> list[tuple[int, str]]:
        return [(r["id"], r["name"]) for r in self._repo.list_by_kind(kind)]

    def list_all_labeled(self) -> list[tuple[int, str, str]]:
        return [(r["id"], r["name"], r["kind"]) for r in self._repo.list_all()]

    def name_map(self) -> dict[int, str]:
        return self._repo.name_map()
