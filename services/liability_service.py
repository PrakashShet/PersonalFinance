"""Business logic for liabilities (loans, credit-card debt, BNPL)."""
from __future__ import annotations

from typing import Callable

from models.liability import Liability
from repositories.liability_repo import LiabilityRepository


class LiabilityService:
    def __init__(
        self,
        repo: LiabilityRepository,
        on_change: Callable[[str], None] | None = None,
    ) -> None:
        self._repo = repo
        self._on_change = on_change

    def list_active(self) -> list[Liability]:
        return self._repo.list_active()

    def get(self, liability_id: int) -> Liability | None:
        return self._repo.get_by_id(liability_id)

    def create(self, liability: Liability) -> int:
        if not liability.name.strip():
            raise ValueError("Liability name is required")
        new_id = self._repo.insert(liability)
        if self._on_change is not None:
            self._on_change("liabilities")
        return new_id

    def update(self, liability: Liability) -> None:
        if liability.id is None:
            raise ValueError("Cannot update a liability without an id")
        if not liability.name.strip():
            raise ValueError("Liability name is required")
        self._repo.update(liability)
        if self._on_change is not None:
            self._on_change("liabilities")

    def delete(self, liability_id: int) -> None:
        self._repo.delete(liability_id)
        if self._on_change is not None:
            self._on_change("liabilities")

    def toggle_active(self, liability: Liability) -> None:
        liability.is_active = 0 if liability.is_active else 1
        self._repo.update(liability)
        if self._on_change is not None:
            self._on_change("liabilities")

    def total_outstanding(self) -> float:
        return self._repo.total_outstanding()
