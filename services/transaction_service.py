"""Business logic for transactions.

A transaction is a ledger entry that also moves money. Creating one adjusts the
linked account balance(s); editing reverses the old effect and applies the new;
deleting reverses the effect. Balance rules live in ``services/ledger.py``:

  income            -> +amount
  investment_sell   -> +amount
  expense           -> -amount
  investment_buy    -> -amount
  transfer          -> -amount on account, +amount on counter_account
  adjustment        -> +amount (signed) - opening balances, corrections and
                       reconciliations; never counted as income or spending
"""
from __future__ import annotations

from datetime import date
from typing import Callable, Optional

from models.transaction import Transaction
from repositories.account_repo import AccountRepository
from repositories.transaction_repo import TransactionRepository
from services import ledger


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

    def _changed(self) -> None:
        if self._on_change is not None:
            self._on_change("transactions")
            self._on_change("accounts")

    # ------------------------------------------------------------- balances
    def _apply_balance(self, txn: Transaction, sign: int) -> None:
        """Apply (sign=+1) or reverse (sign=-1) a transaction's balance effect."""
        for account_id, delta in ledger.effects(txn):
            if account_id:
                self.account_repo.update_balance(account_id, delta * sign)

    # --------------------------------------------------------------- CRUD
    @staticmethod
    def _validate(txn: Transaction) -> None:
        if not txn.txn_date:
            raise ValueError("Transaction date is required")
        if txn.txn_type not in ledger.ALL_TYPES:
            raise ValueError(f"Unknown transaction type: {txn.txn_type!r}")
        if txn.txn_type == ledger.ADJUSTMENT:
            if abs(txn.amount or 0.0) < ledger.CENT:
                raise ValueError("An adjustment must change the balance")
        elif (txn.amount or 0.0) <= 0:
            raise ValueError("Amount must be greater than zero")
        if not txn.account_id:
            raise ValueError("An account is required")
        if txn.txn_type == ledger.TRANSFER:
            if not txn.counter_account_id:
                raise ValueError("A destination account is required for transfers")
            if txn.counter_account_id == txn.account_id:
                raise ValueError("Transfer accounts must be different")

    def create_transaction(self, txn: Transaction) -> int:
        self._validate(txn)
        if txn.txn_type != ledger.TRANSFER:
            txn.counter_account_id = None
        new_id = self.repo.insert(txn)
        txn.id = new_id
        self._apply_balance(txn, +1)
        self._changed()
        return new_id

    def update_transaction(self, txn: Transaction) -> None:
        if txn.id is None:
            raise ValueError("Cannot update a transaction without an id")
        self._validate(txn)
        if txn.txn_type != ledger.TRANSFER:
            txn.counter_account_id = None
        old = self.repo.get_by_id(txn.id)
        if old is not None:
            self._apply_balance(old, -1)   # reverse previous effect
        self.repo.update(txn)
        self._apply_balance(txn, +1)       # apply new effect
        self._changed()

    def delete_transaction(self, txn_id: int) -> None:
        old = self.repo.get_by_id(txn_id)
        if old is not None:
            self._apply_balance(old, -1)
        self.repo.delete(txn_id)
        self._changed()

    def get_transaction(self, txn_id: int):
        return self.repo.get_by_id(txn_id)

    # ---------------------------------------------------------- adjustments
    def create_adjustment(
        self,
        account_id: int,
        delta: float,
        description: str,
        tags: str = ledger.ADJUST_TAG,
        txn_date: Optional[str] = None,
    ) -> int:
        """Move an account's balance by ``delta`` with an auditable entry."""
        return self.create_transaction(Transaction(
            txn_date=txn_date or date.today().isoformat(),
            txn_type=ledger.ADJUSTMENT,
            amount=round(float(delta), 2),
            account_id=account_id,
            description=description,
            tags=tags,
        ))

    def record_reconciliation(self, account_id: int, difference: float) -> int:
        """Write down a difference the balance *already* contains.

        Unlike :meth:`create_adjustment` this does not move the balance: the
        stored balance is the truth (e.g. it was edited by hand), and the entry
        makes the ledger explain it again.
        """
        if abs(difference) < ledger.CENT:
            raise ValueError("Nothing to reconcile")
        new_id = self.repo.insert(Transaction(
            txn_date=date.today().isoformat(),
            txn_type=ledger.ADJUSTMENT,
            amount=round(float(difference), 2),
            account_id=account_id,
            description="Balance reconciliation",
            tags=ledger.RECONCILE_TAG,
        ))
        self._changed()
        return new_id

    def ledger_balances(self) -> dict[int, float]:
        return self.repo.ledger_balances()

    # --------------------------------------------------------------- reads
    def list(self, **filters) -> list:
        return self.repo.list_filtered(**filters)

    def recent(self, limit: int = 6) -> list:
        return self.repo.list_filtered(limit=limit)

    def years(self) -> list[str]:
        return self.repo.distinct_years()

    def has_tag(self, tag: str) -> bool:
        return self.repo.exists_with_tag(tag)

    def summary(self, year=None, month=None, date_from=None, date_to=None) -> dict:
        """Income / expense / investments / net for a period.

        Investments are kept separate from expenses. Net = income - expense -
        net invested. Transfers move money between your own accounts and
        adjustments correct balances, so neither counts here.
        """
        s = self.repo.period_summary(year, month, date_from, date_to)
        income = s.get("income", 0.0)
        expense = s.get("expense", 0.0)
        invested = s.get("investment_buy", 0.0) - s.get("investment_sell", 0.0)
        return {
            "income": income,
            "expense": expense,
            "invested": invested,
            "net": income - expense - invested,
        }

    def monthly_expense(self, year: str, month: str, exclude_emi: bool = False) -> float:
        return self.repo.expense_total(year, month, "emi:" if exclude_emi else None)

    @staticmethod
    def signed_amount(txn_type: str, amount: float) -> float:
        """Amount with sign reflecting its effect on the primary account."""
        return ledger.signed_amount(txn_type, amount)
