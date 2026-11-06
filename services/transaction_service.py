"""Business logic for transactions.

A transaction is a ledger entry that also moves money. Creating one adjusts the
linked account balance(s); editing reverses the old effect and applies the new;
deleting reverses the effect. This keeps account balances consistent with the
ledger.

Balance effect by type (on the primary account):
  income            -> +amount
  investment_sell   -> +amount
  expense           -> -amount
  investment_buy    -> -amount
  transfer          -> -amount on account, +amount on counter_account
"""
from __future__ import annotations

from typing import Callable

from models.transaction import Transaction
from repositories.account_repo import AccountRepository
from repositories.transaction_repo import TransactionRepository

_INFLOW = {"income", "investment_sell"}
_OUTFLOW = {"expense", "investment_buy"}


class TransactionService:
    def __init__(
        self,
        repo: TransactionRepository,
        account_repo: AccountRepository,
        on_change: Callable[[str], None] | None = None,
    ) -> None:
        self.repo = repo
        self.account_repo = account_repo
        self._on_change = on_change

    # ------------------------------------------------------------- balances
    def _apply_balance(self, txn: Transaction, sign: int) -> None:
        """Apply (sign=+1) or reverse (sign=-1) a transaction's balance effect."""
        amt = txn.amount * sign
        t = txn.txn_type
        if t in _INFLOW:
            self.account_repo.update_balance(txn.account_id, amt)
        elif t in _OUTFLOW:
            self.account_repo.update_balance(txn.account_id, -amt)
        elif t == "transfer":
            self.account_repo.update_balance(txn.account_id, -amt)
            if txn.counter_account_id:
                self.account_repo.update_balance(txn.counter_account_id, amt)

    # --------------------------------------------------------------- CRUD
    @staticmethod
    def _validate(txn: Transaction) -> None:
        if not txn.txn_date:
            raise ValueError("Transaction date is required")
        if txn.amount <= 0:
            raise ValueError("Amount must be greater than zero")
        if not txn.account_id:
            raise ValueError("An account is required")
        if txn.txn_type == "transfer":
            if not txn.counter_account_id:
                raise ValueError("A destination account is required for transfers")
            if txn.counter_account_id == txn.account_id:
                raise ValueError("Transfer accounts must be different")

    def create_transaction(self, txn: Transaction) -> int:
        self._validate(txn)
        new_id = self.repo.insert(txn)
        txn.id = new_id
        self._apply_balance(txn, +1)
        if self._on_change is not None:
            self._on_change("transactions")
            self._on_change("accounts")
        return new_id

    def update_transaction(self, txn: Transaction) -> None:
        if txn.id is None:
            raise ValueError("Cannot update a transaction without an id")
        self._validate(txn)
        old = self.repo.get_by_id(txn.id)
        if old is not None:
            self._apply_balance(old, -1)   # reverse previous effect
        self.repo.update(txn)
        self._apply_balance(txn, +1)       # apply new effect
        if self._on_change is not None:
            self._on_change("transactions")
            self._on_change("accounts")

    def delete_transaction(self, txn_id: int) -> None:
        old = self.repo.get_by_id(txn_id)
        if old is not None:
            self._apply_balance(old, -1)
        self.repo.delete(txn_id)
        if self._on_change is not None:
            self._on_change("transactions")
            self._on_change("accounts")

    def get_transaction(self, txn_id: int):
        return self.repo.get_by_id(txn_id)

    # --------------------------------------------------------------- reads
    def list(self, **filters) -> list:
        return self.repo.list_filtered(**filters)

    def years(self) -> list[str]:
        return self.repo.distinct_years()

    def summary(self, year=None, month=None) -> dict:
        """Income / expense / investments / net for a period.

        Investments are kept separate from expenses. Net = income - expense -
        net invested. Transfers are internal moves and excluded from net.
        """
        s = self.repo.period_summary(year, month)
        income = s.get("income", 0.0)
        expense = s.get("expense", 0.0)
        invested = s.get("investment_buy", 0.0) - s.get("investment_sell", 0.0)
        return {
            "income": income,
            "expense": expense,
            "invested": invested,
            "net": income - expense - invested,
        }

    @staticmethod
    def signed_amount(txn_type: str, amount: float) -> float:
        """Amount with sign reflecting its effect on the primary account."""
        if txn_type in _INFLOW:
            return amount
        if txn_type in _OUTFLOW or txn_type == "transfer":
            return -amount
        return amount
