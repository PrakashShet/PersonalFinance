"""Business logic for account operations.

Balances are owned by the ledger (``services/ledger.py``):

* Creating an account with money in it posts an **Opening balance**
  adjustment, so the account's history starts from that figure.
* Editing an account's balance by hand posts a **Balance adjustment** for the
  difference instead of overwriting the number - the change is visible and
  reversible in Transactions, and later edits to old entries stay correct.
* :meth:`reconciliation_report` lists accounts whose balance the ledger no
  longer explains (e.g. a store file edited by hand); :meth:`reconcile`
  records the difference.

Neither kind of adjustment is income or spending.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Callable, Optional

from models.account import Account
from repositories.account_repo import AccountRepository
from services import ledger

if TYPE_CHECKING:
    from repositories.category_repo import CategoryRepository
    from services.fx_service import FxService
    from services.transaction_service import TransactionService


@dataclass
class Mismatch:
    account: Account
    ledger_balance: float
    stored_balance: float

    @property
    def difference(self) -> float:
        return round(self.stored_balance - self.ledger_balance, 2)


class AccountService:
    def __init__(
        self,
        repo: AccountRepository,
        txn_service: Optional["TransactionService"] = None,
        category_repo: Optional["CategoryRepository"] = None,
        on_change: Callable[[str], None] | None = None,
        fx_service: Optional["FxService"] = None,
    ) -> None:
        self.repo = repo
        self._txn_service = txn_service
        self._category_repo = category_repo
        self._on_change = on_change
        self._fx = fx_service

    def _changed(self) -> None:
        if self._on_change is not None:
            self._on_change("accounts")

    # ------------------------------------------------------------- create
    def create_account(self, account: Account) -> int:
        if not (account.name or "").strip():
            raise ValueError("Account name is required")
        account.name = account.name.strip()
        balance = round(float(account.current_balance or account.opening_balance or 0.0), 2)
        account.opening_balance = balance

        if self._txn_service is None:
            account.current_balance = balance
            account_id = self.repo.insert(account)
        else:
            # The ledger entry applies the balance; start from zero.
            account.current_balance = 0.0
            account_id = self.repo.insert(account)
            if abs(balance) >= ledger.CENT:
                self._txn_service.create_adjustment(
                    account_id, balance, f"Opening balance: {account.name}",
                    tags=ledger.OPENING_TAG,
                )
        self._changed()
        return account_id

    # ------------------------------------------------------------- update
    def update_account(self, account: Account) -> None:
        """Persist edits. A changed balance becomes a Balance adjustment."""
        if account.id is None:
            raise ValueError("Cannot update an account without an id")
        if not (account.name or "").strip():
            raise ValueError("Account name is required")
        account.name = account.name.strip()
        old = self.repo.get_by_id(account.id)
        wanted = round(float(account.current_balance or 0.0), 2)
        if old is not None:
            account.current_balance = old.current_balance   # ledger moves it
            account.opening_balance = old.opening_balance
        account.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.repo.update(account)

        delta = round(wanted - (old.current_balance if old else wanted), 2)
        if old is not None and abs(delta) >= ledger.CENT:
            if self._txn_service is not None:
                self._txn_service.create_adjustment(
                    account.id, delta, f"Balance adjustment: {account.name}",
                )
            else:
                self.repo.update_balance(account.id, delta)
        self._changed()

    def set_balance(self, account_id: int, new_balance: float) -> float:
        """"What's in this account today?" - records the difference as a
        Balance adjustment. Returns the difference applied."""
        acct = self.repo.get_by_id(account_id)
        if acct is None:
            raise ValueError("Account not found")
        delta = round(float(new_balance) - acct.current_balance, 2)
        acct.current_balance = float(new_balance)
        self.update_account(acct)
        return delta

    # --------------------------------------------------------- archiving
    def archive_account(self, account_id: int) -> None:
        account = self.repo.get_by_id(account_id)
        if account is None:
            return
        account.is_active = 0
        account.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.repo.update(account)
        self._changed()

    def restore_account(self, account_id: int) -> None:
        account = self.repo.get_by_id(account_id)
        if account is None:
            return
        account.is_active = 1
        account.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.repo.update(account)
        self._changed()

    # ------------------------------------------------------------- reads
    def get_account(self, account_id: int) -> Account | None:
        return self.repo.get_by_id(account_id)

    def get_all_active(self) -> list[Account]:
        return self.repo.list_active()

    def get_all(self, include_archived: bool = False) -> list[Account]:
        """All accounts; active-only by default."""
        if include_archived:
            return self.repo.list_all("1 = 1 ORDER BY is_active DESC, id")
        return self.repo.list_active()

    def get_total_liquid_balance(self) -> float:
        """Cash + bank in INR, excluding credit cards (liabilities)."""
        total, _missing = self._liquid_in_base()
        return total

    def _liquid_in_base(self) -> tuple[float, dict[str, float]]:
        total = 0.0
        unconverted: dict[str, float] = {}
        for ccy, amount in self.repo.balances_by_currency().items():
            converted = self._fx.convert(amount, ccy) if self._fx else (
                amount if ccy == "INR" else None)
            if converted is None:
                unconverted[ccy] = amount
            else:
                total += converted
        return total, unconverted

    def account_summary(self) -> dict[str, object]:
        """Headline numbers for the Accounts view KPI strip."""
        active = self.repo.list_active()
        liquid, unconverted = self._liquid_in_base()
        return {
            "count": len(active),
            "liquid_balance": liquid,
            "unconverted": unconverted,
            "credit_card_outstanding": sum(
                a.current_balance for a in active if a.account_type == "credit_card"
            ),
        }

    def adjust_balance(self, account_id: int, delta: float) -> None:
        self.repo.update_balance(account_id, delta)

    # ----------------------------------------------------- reconciliation
    def reconciliation_report(self) -> list[Mismatch]:
        """Active accounts whose stored balance the ledger does not explain."""
        if self._txn_service is None:
            return []
        implied = self._txn_service.ledger_balances()
        out = []
        for a in self.repo.list_active():
            lb = round(implied.get(a.id, 0.0), 2)
            if abs(round(a.current_balance, 2) - lb) >= 0.01:
                out.append(Mismatch(a, lb, round(a.current_balance, 2)))
        return out

    def mismatch_for(self, account_id: int) -> Optional[Mismatch]:
        return next((m for m in self.reconciliation_report() if m.account.id == account_id), None)

    def reconcile(self, account_id: int) -> float:
        """Record the unexplained difference; the balance itself is unchanged."""
        m = self.mismatch_for(account_id)
        if m is None or self._txn_service is None:
            return 0.0
        self._txn_service.record_reconciliation(account_id, m.difference)
        self._changed()
        return m.difference
