"""Business logic for income sources and their monthly actuals.

An income source describes *expected* income (salary breakdown, MRR, etc.).
An income entry records what was *actually* received in a given month. When an
entry is posted to the ledger it also creates an income ``Transaction`` into the
linked deposit account, so account balances stay consistent with reality.

Recording a month is an upsert keyed on (source, period): re-recording the same
month replaces the previous entry and reverses/re-applies any ledger effect.
"""
from __future__ import annotations

from typing import Optional

from models.income import IncomeSource
from models.income_entry import IncomeEntry
from models.transaction import Transaction
from repositories.income_entry_repo import IncomeEntryRepository
from repositories.income_repo import IncomeRepository
from services.transaction_service import TransactionService


# Frequency -> how many times in a typical month the income recurs.
_FREQ_MONTHLY_FACTOR = {
    "monthly": 1.0,
    "quarterly": 1 / 3,
    "annual": 1 / 12,
    "irregular": 0.0,
    "one_time": 0.0,
}


def _salary_gross(s: IncomeSource) -> float:
    return sum(v or 0.0 for v in (s.basic, s.hra, s.special_allow))


def _salary_deductions(s: IncomeSource) -> float:
    return sum(v or 0.0 for v in (s.pf_employee, s.professional_tax, s.tds))


class IncomeService:
    def __init__(
        self,
        income_repo: IncomeRepository,
        entry_repo: IncomeEntryRepository,
        txn_service: TransactionService,
    ) -> None:
        self.income_repo = income_repo
        self.entry_repo = entry_repo
        self.txn_service = txn_service

    # ------------------------------------------------------------- estimates
    @staticmethod
    def gross_monthly(s: IncomeSource) -> float:
        """Expected gross per month for a source."""
        if s.source_type == "salary" and (s.basic or s.hra or s.special_allow):
            return _salary_gross(s)
        if s.expected_amount is None:
            return 0.0
        return s.expected_amount * _FREQ_MONTHLY_FACTOR.get(s.frequency or "monthly", 0.0)

    @staticmethod
    def deductions_monthly(s: IncomeSource) -> float:
        if s.source_type == "salary":
            return _salary_deductions(s)
        return 0.0

    @classmethod
    def net_monthly(cls, s: IncomeSource) -> float:
        """Expected take-home per month (gross minus deductions)."""
        return cls.gross_monthly(s) - cls.deductions_monthly(s)

    # --------------------------------------------------------------- entries
    def list_entries(self, source_id: int) -> list[IncomeEntry]:
        return self.entry_repo.list_for_source(source_id)

    def total_received(self, period_month: str) -> float:
        return self.entry_repo.total_received(period_month)

    def has_logged(self, source_id: int, period_month: str) -> bool:
        """Whether the given source already has an entry for the month."""
        return self.entry_repo.get_for_period(source_id, period_month) is not None

    def expected_this_month(self, sources: list[IncomeSource]) -> float:
        """Sum of expected net monthly income across active sources.

        Irregular / one-time sources contribute 0 (their monthly factor is 0).
        """
        return sum(self.net_monthly(s) for s in sources if s.is_active)

    def is_recurring_monthly(self, s: IncomeSource) -> bool:
        """A source we'd expect to be logged every month."""
        return bool(s.is_active) and self.net_monthly(s) > 0

    def pending_sources(
        self, sources: list[IncomeSource], period_month: str
    ) -> list[IncomeSource]:
        """Active, recurring sources with no entry logged for the month yet."""
        return [
            s for s in sources
            if self.is_recurring_monthly(s) and not self.has_logged(s.id, period_month)  # type: ignore[arg-type]
        ]

    def record_month(
        self,
        source: IncomeSource,
        period_month: str,
        actual_amount: float,
        received_date: Optional[str] = None,
        account_id: Optional[int] = None,
        post_to_ledger: bool = True,
        notes: Optional[str] = None,
    ) -> IncomeEntry:
        """Upsert the actual income for ``period_month``.

        If ``post_to_ledger`` and an account is given, an income transaction is
        created/refreshed so the account balance reflects the receipt.
        """
        if source.id is None:
            raise ValueError("Income source must be persisted before recording")
        if not period_month:
            raise ValueError("A period (YYYY-MM) is required")
        if actual_amount <= 0:
            raise ValueError("Actual amount must be greater than zero")

        existing = self.entry_repo.get_for_period(source.id, period_month)

        # Clear any previous ledger effect so we can re-post cleanly.
        if existing is not None and existing.transaction_id:
            self.txn_service.delete_transaction(existing.transaction_id)

        txn_id: Optional[int] = None
        if post_to_ledger and account_id:
            txn = Transaction(
                txn_date=received_date or f"{period_month}-01",
                txn_type="income",
                amount=float(actual_amount),
                account_id=account_id,
                income_source_id=source.id,
                description=f"Income: {source.name} ({period_month})",
            )
            txn_id = self.txn_service.create_transaction(txn)

        entry = IncomeEntry(
            id=existing.id if existing is not None else None,
            income_source_id=source.id,
            period_month=period_month,
            expected_amount=self.net_monthly(source) or None,
            actual_amount=float(actual_amount),
            received_date=received_date,
            account_id=account_id,
            transaction_id=txn_id,
            notes=notes or None,
        )

        if entry.id is None:
            entry.id = self.entry_repo.insert(entry)
        else:
            self.entry_repo.update(entry)
        return entry

    def delete_entry(self, entry_id: int) -> None:
        """Remove a logged month, reversing its ledger effect if any."""
        entry = self.entry_repo.get_by_id(entry_id)
        if entry is None:
            return
        if entry.transaction_id:
            self.txn_service.delete_transaction(entry.transaction_id)
        self.entry_repo.delete(entry_id)
