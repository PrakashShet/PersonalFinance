"""Business logic for account operations."""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Callable, Optional

from models.account import Account
from models.transaction import Transaction
from repositories.account_repo import AccountRepository

if TYPE_CHECKING:
    from repositories.category_repo import CategoryRepository
    from services.transaction_service import TransactionService

_OPENING_BALANCE_CATEGORY = "Opening Balance"


class AccountService:
    def __init__(
        self,
        repo: AccountRepository,
        txn_service: Optional["TransactionService"] = None,
        category_repo: Optional["CategoryRepository"] = None,
        on_change: Callable[[str], None] | None = None,
    ) -> None:
        self.repo = repo
        self._txn_service = txn_service
        self._category_repo = category_repo
        self._on_change = on_change

    def create_account(self, account: Account) -> int:
        if not account.name.strip():
            raise ValueError("Account name is required")
        # Convenience: if no current balance was supplied, start it at the
        # opening balance. An explicitly entered current balance is respected.
        if not account.current_balance:
            account.current_balance = account.opening_balance

        balance = float(account.current_balance or 0.0)
        post_opening = (
            balance > 0
            and account.account_type != "credit_card"
            and self._txn_service is not None
        )
        if post_opening:
            # Balance will be applied by the ledger entry; avoid double-counting.
            account.current_balance = 0.0

        account_id = self.repo.insert(account)

        if post_opening:
            category_id = None
            if self._category_repo is not None:
                category_id = self._category_repo.ensure(
                    _OPENING_BALANCE_CATEGORY, "income", icon="landmark"
                )
            txn = Transaction(
                txn_date=datetime.now().strftime("%Y-%m-%d"),
                txn_type="income",
                amount=balance,
                account_id=account_id,
                category_id=category_id,
                description=f"Opening balance: {account.name}",
                tags="opening-balance",
            )
            self._txn_service.create_transaction(txn)

        if self._on_change is not None:
            self._on_change("accounts")
        return account_id

    def update_account(self, account: Account) -> None:
        """Persist edits to an existing account."""
        if account.id is None:
            raise ValueError("Cannot update an account without an id")
        if not account.name.strip():
            raise ValueError("Account name is required")
        account.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.repo.update(account)
        if self._on_change is not None:
            self._on_change("accounts")

    def archive_account(self, account_id: int) -> None:
        """Soft-delete: keep the row but mark it inactive so history and
        any linked transactions are preserved."""
        account = self.repo.get_by_id(account_id)
        if account is None:
            raise ValueError(f"No account with id {account_id}")
        account.is_active = 0
        account.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.repo.update(account)
        if self._on_change is not None:
            self._on_change("accounts")

    def restore_account(self, account_id: int) -> None:
        """Reactivate a previously archived account."""
        account = self.repo.get_by_id(account_id)
        if account is None:
            raise ValueError(f"No account with id {account_id}")
        account.is_active = 1
        account.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.repo.update(account)
        if self._on_change is not None:
            self._on_change("accounts")

    def get_account(self, account_id: int) -> Account | None:
        return self.repo.get_by_id(account_id)

    def get_all_active(self) -> list[Account]:
        return self.repo.list_active()

    def get_all(self, include_archived: bool = False) -> list[Account]:
        """All accounts; active-only by default."""
        if include_archived:
            return self.repo.list_all()
        return self.repo.list_active()

    def get_total_liquid_balance(self) -> float:
        """Cash + bank, excluding credit cards (liabilities)."""
        return self.repo.total_balance()

    def account_summary(self) -> dict[str, object]:
        """Headline numbers for the Accounts view KPI strip."""
        active = self.repo.list_active()
        return {
            "count": len(active),
            "liquid_balance": self.repo.total_balance(),
            "credit_card_outstanding": sum(
                a.current_balance for a in active if a.account_type == "credit_card"
            ),
        }

    def adjust_balance(self, account_id: int, delta: float) -> None:
        self.repo.update_balance(account_id, delta)
