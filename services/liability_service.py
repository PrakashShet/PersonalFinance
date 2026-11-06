"""Business logic for liabilities (loans, credit-card debt, BNPL).

The ``liabilities`` table is the single source of truth for debt in net worth.
Accounts may also *describe* a loan (``loan_*`` fields); :meth:`for_account`
tells the UI whether that loan is tracked here, and
:meth:`create_from_account_loan` turns the description into a tracked liability
in one step, linked back to the account so it is never counted twice.
"""
from __future__ import annotations

from typing import Callable, Optional

from models.account import Account
from models.liability import Liability
from repositories.liability_repo import LiabilityRepository

_LOAN_LABELS = {
    "home_loan": "Home loan",
    "car_loan": "Car loan",
    "personal_loan": "Personal loan",
    "education_loan": "Education loan",
    "bnpl": "BNPL",
}


class LiabilityService:
    def __init__(
        self,
        repo: LiabilityRepository,
        on_change: Callable[[str], None] | None = None,
    ) -> None:
        self._repo = repo
        self._on_change = on_change

    def _changed(self) -> None:
        if self._on_change is not None:
            self._on_change("liabilities")

    def list_active(self) -> list[Liability]:
        return self._repo.list_active()

    def list_all(self, include_inactive: bool = False) -> list[Liability]:
        if include_inactive:
            return self._repo.list_all("1 = 1 ORDER BY is_active DESC, id")
        return self._repo.list_active()

    def get(self, liability_id: int) -> Liability | None:
        return self._repo.get_by_id(liability_id)

    def create(self, liability: Liability) -> int:
        if not liability.name.strip():
            raise ValueError("Liability name is required")
        new_id = self._repo.insert(liability)
        self._changed()
        return new_id

    def update(self, liability: Liability) -> None:
        if liability.id is None:
            raise ValueError("Cannot update a liability without an id")
        if not liability.name.strip():
            raise ValueError("Liability name is required")
        self._repo.update(liability)
        self._changed()

    def delete(self, liability_id: int) -> None:
        self._repo.delete(liability_id)
        self._changed()

    def toggle_active(self, liability: Liability) -> None:
        liability.is_active = 0 if liability.is_active else 1
        self._repo.update(liability)
        self._changed()

    def total_outstanding(self) -> float:
        return self._repo.total_outstanding()

    # --------------------------------------------------- account loan link
    def for_account(self, account_id: int) -> Optional[Liability]:
        return self._repo.find_by_account(account_id)

    @staticmethod
    def account_has_loan(account: Account) -> bool:
        return bool(
            (account.loan_outstanding or 0) > 0
            or (account.loan_principal or 0) > 0
            or account.loan_type
        )

    def create_from_account_loan(self, account: Account) -> int:
        """Track the loan described on ``account`` as a liability (once)."""
        if account.id is None:
            raise ValueError("Save the account first")
        existing = self.for_account(account.id)
        if existing is not None:
            return existing.id  # type: ignore[return-value]
        loan_type = account.loan_type or "personal_loan"
        principal = float(account.loan_principal or account.loan_outstanding or 0.0)
        liability = Liability(
            name=f"{_LOAN_LABELS.get(loan_type, 'Loan')} - {account.name}",
            liability_type=loan_type,
            lender=account.institution,
            principal=principal,
            outstanding=float(account.loan_outstanding or principal),
            interest_rate=account.loan_interest_rate or None,
            emi_amount=account.loan_emi or None,
            tenure_months=account.loan_tenure_months or None,
            start_date=account.loan_start_date,
            account_id=account.id,
            notes=(f"Loan account {account.loan_account_number}"
                   if account.loan_account_number else None),
        )
        return self.create(liability)
