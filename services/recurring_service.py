"""What needs attention: recurring payments that are due, and one-step logging.

``due_items()`` gathers, from data the app already has:

* **SIPs** - holdings with a monthly ``sip_amount``; due on ``sip_day_of_month``
  (default the 1st) until this month's instalment is logged.
* **EMIs** - liabilities with an ``emi_amount`` and a ``next_due_date``.
* **Premiums** - term-insurance holdings with a ``premium_amount`` and
  ``premium_due_date`` (annual).
* **Income** - recurring monthly income sources not yet recorded this month.
* **Maturities** - FDs / bonds maturing soon (information only).
* **Reminders** - open rows in the reminders table.

``log()`` posts the ledger transaction *and* updates the source record in one
step: a SIP adds to the holding's invested amount and value; an EMI reduces the
loan's outstanding by its principal part and moves the due date a month; a
premium moves the due date a year. Each logged entry carries a tag
(``sip:<id>:<YYYY-MM>``, ``emi:<id>:<YYYY-MM>``, ``premium:<id>:<date>``) so the
same instalment is never offered twice.
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Callable, Optional

from models.holding import Holding
from models.liability import Liability
from models.reminder import Reminder
from models.transaction import Transaction
from repositories.category_repo import CategoryRepository
from repositories.holding_repo import HoldingRepository
from repositories.liability_repo import LiabilityRepository
from repositories.reference_repos import ReminderRepository
from services.transaction_service import TransactionService

KIND_SIP = "sip"
KIND_EMI = "emi"
KIND_PREMIUM = "premium"
KIND_INCOME = "income"
KIND_MATURITY = "maturity"
KIND_REMINDER = "reminder"

ACTION_LOG = "log"          # post a transaction (LogPaymentDialog)
ACTION_RECORD = "record"    # record income (RecordIncomeDialog)
ACTION_DONE = "done"        # mark a reminder done
ACTION_INFO = "info"        # nothing to post


@dataclass
class DueItem:
    key: str
    kind: str
    title: str
    due_date: str                    # ISO date
    amount: float
    account_id: Optional[int]
    ref_id: Optional[int]
    action: str
    overdue: bool = False
    note: str = ""

    @property
    def is_payment(self) -> bool:
        return self.kind in (KIND_SIP, KIND_EMI, KIND_PREMIUM)


def add_months(d: date, months: int) -> date:
    index = d.year * 12 + (d.month - 1) + months
    y, m = divmod(index, 12)
    day = min(d.day, calendar.monthrange(y, m + 1)[1])
    return date(y, m + 1, day)


def _parse(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


class RecurringService:
    def __init__(
        self,
        txn_service: TransactionService,
        holding_repo: HoldingRepository,
        liability_repo: LiabilityRepository,
        reminder_repo: ReminderRepository,
        category_repo: CategoryRepository,
        income_source_service=None,
        on_change: Callable[[str], None] | None = None,
    ) -> None:
        self.txn = txn_service
        self.holdings = holding_repo
        self.liabilities = liability_repo
        self.reminders = reminder_repo
        self.categories = category_repo
        self.income_sources = income_source_service
        self._on_change = on_change

    def _changed(self, *topics: str) -> None:
        if self._on_change is not None:
            for t in topics:
                self._on_change(t)

    # ------------------------------------------------------------- query
    def due_items(self, today: Optional[date] = None, horizon_days: int = 14) -> list[DueItem]:
        today = today or date.today()
        horizon = today + timedelta(days=horizon_days)
        items: list[DueItem] = []
        items += self._due_sips(today, horizon)
        items += self._due_emis(today, horizon)
        items += self._due_premiums(today, horizon)
        items += self._pending_income(today)
        items += self._maturities(today, today + timedelta(days=30))
        items += self._open_reminders(today, horizon)
        rank = {True: 0, False: 1}
        return sorted(items, key=lambda i: (rank[i.overdue], i.due_date, i.title))

    def _due_sips(self, today: date, horizon: date) -> list[DueItem]:
        out = []
        for h in self.holdings.list_active():
            if not h.sip_amount or h.sip_amount <= 0:
                continue
            start = _parse(h.purchase_date)
            if start and start > today:
                continue
            last_day = calendar.monthrange(today.year, today.month)[1]
            due = date(today.year, today.month, min(max(1, h.sip_day_of_month or 1), last_day))
            tag = f"sip:{h.id}:{today:%Y-%m}"
            if due > horizon or self.txn.has_tag(tag):
                continue
            out.append(DueItem(
                key=tag, kind=KIND_SIP, title=f"SIP - {h.name}", due_date=due.isoformat(),
                amount=float(h.sip_amount), account_id=h.linked_account_id, ref_id=h.id,
                action=ACTION_LOG, overdue=due < today,
            ))
        return out

    def _due_emis(self, today: date, horizon: date) -> list[DueItem]:
        out = []
        for lb in self.liabilities.list_active():
            due = _parse(lb.next_due_date)
            if not lb.emi_amount or lb.emi_amount <= 0 or due is None or due > horizon:
                continue
            if (lb.outstanding or 0) <= 0:
                continue
            out.append(DueItem(
                key=f"emi:{lb.id}:{due:%Y-%m}", kind=KIND_EMI, title=f"EMI - {lb.name}",
                due_date=due.isoformat(), amount=float(lb.emi_amount),
                account_id=lb.account_id, ref_id=lb.id, action=ACTION_LOG,
                overdue=due < today,
            ))
        return out

    def _due_premiums(self, today: date, horizon: date) -> list[DueItem]:
        out = []
        for h in self.holdings.list_active():
            if h.holding_type != "term_insurance":
                continue
            due = _parse(h.premium_due_date)
            if not h.premium_amount or h.premium_amount <= 0 or due is None or due > horizon:
                continue
            out.append(DueItem(
                key=f"premium:{h.id}:{due.isoformat()}", kind=KIND_PREMIUM,
                title=f"Premium - {h.name}", due_date=due.isoformat(),
                amount=float(h.premium_amount), account_id=h.linked_account_id,
                ref_id=h.id, action=ACTION_LOG, overdue=due < today,
            ))
        return out

    def _pending_income(self, today: date) -> list[DueItem]:
        if self.income_sources is None:
            return []
        period = today.strftime("%Y-%m")
        out = []
        for s in self.income_sources.pending_sources(
            self.income_sources.list_active(), period
        ):
            out.append(DueItem(
                key=f"income:{s.id}:{period}", kind=KIND_INCOME,
                title=f"Income - {s.name}", due_date=f"{period}-01",
                amount=float(self.income_sources.net_monthly(s) or 0.0),
                account_id=s.deposit_account_id, ref_id=s.id, action=ACTION_RECORD,
                note="Not recorded this month yet",
            ))
        return out

    def _maturities(self, today: date, horizon: date) -> list[DueItem]:
        out = []
        for h in self.holdings.list_active():
            if h.holding_type not in ("fd", "bond"):
                continue
            due = _parse(h.maturity_date)
            if due is None or due > horizon or due < today - timedelta(days=30):
                continue
            out.append(DueItem(
                key=f"maturity:{h.id}", kind=KIND_MATURITY, title=f"Matures - {h.name}",
                due_date=due.isoformat(), amount=float(h.current_value or 0.0),
                account_id=h.linked_account_id, ref_id=h.id, action=ACTION_INFO,
                note="Renew it or move the money" if due <= today else "",
            ))
        return out

    def _open_reminders(self, today: date, horizon: date) -> list[DueItem]:
        out = []
        for r in self.reminders.list_open():
            due = _parse(r.due_date)
            if due is None or due > horizon:
                continue
            out.append(DueItem(
                key=f"reminder:{r.id}", kind=KIND_REMINDER, title=r.title,
                due_date=due.isoformat(), amount=float(r.amount or 0.0),
                account_id=None, ref_id=r.id, action=ACTION_DONE, overdue=due < today,
                note=r.notes or "",
            ))
        return out

    # -------------------------------------------------------------- act
    def log(self, item: DueItem, amount: float, txn_date: str, account_id: int) -> int:
        """Post the payment for ``item`` and update its source record."""
        if not account_id:
            raise ValueError("Choose the account the money left from")
        if amount <= 0:
            raise ValueError("Amount must be greater than zero")
        if item.kind == KIND_SIP:
            return self._log_sip(item, amount, txn_date, account_id)
        if item.kind == KIND_EMI:
            return self._log_emi(item, amount, txn_date, account_id)
        if item.kind == KIND_PREMIUM:
            return self._log_premium(item, amount, txn_date, account_id)
        raise ValueError(f"{item.kind} items can't be logged as a payment")

    def _log_sip(self, item: DueItem, amount: float, txn_date: str, account_id: int) -> int:
        h: Holding | None = self.holdings.get_by_id(item.ref_id)
        if h is None:
            raise ValueError("That investment no longer exists")
        txn_id = self.txn.create_transaction(Transaction(
            txn_date=txn_date, txn_type="investment_buy", amount=amount,
            account_id=account_id, holding_id=h.id,
            description=f"SIP - {h.name}", tags=item.key,
        ))
        h.invested_amount = round((h.invested_amount or 0.0) + amount, 2)
        h.current_value = round((h.current_value or 0.0) + amount, 2)
        if h.current_price and h.current_price > 0 and h.quantity is not None:
            h.quantity = round(h.quantity + amount / h.current_price, 4)
        if not h.linked_account_id:
            h.linked_account_id = account_id
        self.holdings.update(h)
        self._changed("holdings")
        return txn_id

    def _log_emi(self, item: DueItem, amount: float, txn_date: str, account_id: int) -> int:
        lb: Liability | None = self.liabilities.get_by_id(item.ref_id)
        if lb is None:
            raise ValueError("That loan no longer exists")
        txn_id = self.txn.create_transaction(Transaction(
            txn_date=txn_date, txn_type="expense", amount=amount, account_id=account_id,
            category_id=self.categories.ensure("EMI", "expense"),
            description=f"EMI - {lb.name}", tags=item.key,
        ))
        interest = (lb.outstanding or 0.0) * (lb.interest_rate or 0.0) / 1200.0
        principal = max(0.0, amount - interest)
        lb.outstanding = round(max(0.0, (lb.outstanding or 0.0) - principal), 2)
        if lb.remaining_months:
            lb.remaining_months = max(0, lb.remaining_months - 1)
        due = _parse(lb.next_due_date) or _parse(txn_date) or date.today()
        lb.next_due_date = None if lb.outstanding <= 0 else add_months(due, 1).isoformat()
        if not lb.account_id:
            lb.account_id = account_id
        self.liabilities.update(lb)
        self._changed("liabilities")
        return txn_id

    def _log_premium(self, item: DueItem, amount: float, txn_date: str, account_id: int) -> int:
        h: Holding | None = self.holdings.get_by_id(item.ref_id)
        if h is None:
            raise ValueError("That policy no longer exists")
        txn_id = self.txn.create_transaction(Transaction(
            txn_date=txn_date, txn_type="expense", amount=amount, account_id=account_id,
            category_id=self.categories.ensure("Insurance Premium", "expense"),
            description=f"Premium - {h.name}", tags=item.key,
        ))
        due = _parse(h.premium_due_date) or _parse(txn_date) or date.today()
        h.premium_due_date = add_months(due, 12).isoformat()
        if not h.linked_account_id:
            h.linked_account_id = account_id
        self.holdings.update(h)
        self._changed("holdings")
        return txn_id

    # --------------------------------------------------------- reminders
    def add_reminder(self, title: str, due_date: str, amount: Optional[float] = None,
                     notes: Optional[str] = None) -> int:
        if not (title or "").strip():
            raise ValueError("Give the reminder a title")
        if _parse(due_date) is None:
            raise ValueError("Choose a valid date")
        rid = self.reminders.insert(Reminder(
            title=title.strip(), due_date=due_date, amount=amount, notes=notes))
        self._changed("reminders")
        return rid

    def complete_reminder(self, reminder_id: int) -> None:
        r = self.reminders.get_by_id(reminder_id)
        if r is None:
            return
        r.is_done = 1
        self.reminders.update(r)
        self._changed("reminders")
