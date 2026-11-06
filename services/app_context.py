"""Central wiring for repositories and services — injected into UI views."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from PyQt6.QtCore import QObject, pyqtSignal

from db.connection import Database, db
from models.account import Account
from repositories.account_repo import AccountRepository
from repositories.category_repo import CategoryRepository
from repositories.goal_holding_repo import GoalHoldingRepository
from repositories.goal_repo import GoalRepository
from repositories.holding_repo import HoldingRepository
from repositories.income_entry_repo import IncomeEntryRepository
from repositories.income_repo import IncomeRepository
from repositories.liability_repo import LiabilityRepository
from repositories.transaction_repo import TransactionRepository
from services.account_service import AccountService
from services.category_service import CategoryService
from services.goal_service import GoalService
from services.income_service import IncomeService
from services.income_source_service import IncomeSourceService
from services.investment_service import InvestmentService
from services.liability_service import LiabilityService
from services.net_worth_service import NetWorthService
from services.projection_service import ProjectionService
from services.transaction_service import TransactionService


class DataEvents(QObject):
    """Lightweight in-process event bus for cross-tab refresh."""

    changed = pyqtSignal(str)  # topic name, e.g. "accounts", "transactions"


@dataclass
class AppContext:
    account_service: AccountService
    transaction_service: TransactionService
    income_service: IncomeService
    income_source_service: IncomeSourceService
    investment_service: InvestmentService
    liability_service: LiabilityService
    goal_service: GoalService
    category_service: CategoryService
    net_worth_service: NetWorthService
    projection_service: ProjectionService
    events: DataEvents
    _holding_repo: HoldingRepository = field(repr=False, compare=False, default=None)
    _goal_holding_repo: GoalHoldingRepository = field(repr=False, compare=False, default=None)
    _income_repo: IncomeRepository = field(repr=False, compare=False, default=None)
    _liability_repo: LiabilityRepository = field(repr=False, compare=False, default=None)

    @classmethod
    def create(cls, database: Database | None = None) -> AppContext:
        database = database or db
        events = DataEvents()
        on_change: Callable[[str], None] = events.changed.emit

        account_repo = AccountRepository(database)
        category_repo = CategoryRepository(database)
        holding_repo = HoldingRepository(database)
        liability_repo = LiabilityRepository(database)
        goal_repo = GoalRepository(database)
        goal_holding_repo = GoalHoldingRepository(database)
        income_repo = IncomeRepository(database)
        income_entry_repo = IncomeEntryRepository(database)
        transaction_repo = TransactionRepository(database)

        transaction_service = TransactionService(
            transaction_repo, account_repo, on_change=on_change
        )
        account_service = AccountService(
            account_repo, transaction_service, category_repo, on_change=on_change
        )
        income_service = IncomeService(
            income_repo, income_entry_repo, transaction_service
        )
        income_source_service = IncomeSourceService(
            income_repo, income_entry_repo, income_service, on_change=on_change
        )
        projection_service = ProjectionService()
        goal_service = GoalService(
            goal_repo,
            goal_holding_repo,
            holding_repo,
            projection_service,
            on_change=on_change,
        )

        return cls(
            account_service=account_service,
            transaction_service=transaction_service,
            income_service=income_service,
            income_source_service=income_source_service,
            investment_service=InvestmentService(holding_repo, on_change=on_change),
            liability_service=LiabilityService(liability_repo, on_change=on_change),
            goal_service=goal_service,
            category_service=CategoryService(category_repo),
            net_worth_service=NetWorthService(
                database, account_repo, holding_repo, liability_repo
            ),
            projection_service=projection_service,
            events=events,
            _holding_repo=holding_repo,
            _goal_holding_repo=goal_holding_repo,
            _income_repo=income_repo,
            _liability_repo=liability_repo,
        )

    def emit_changed(self, topic: str) -> None:
        self.events.changed.emit(topic)

    def derive_projection_baseline(self):
        return self.projection_service.derive_baseline(
            self.net_worth_service,
            self._holding_repo,
            self._liability_repo,
            self._income_repo,
            self.income_service,
            self.transaction_service,
        )

    def goal_projection_forecasts(self):
        goals = self.goal_service.list_active()
        holdings_by_id = {
            h.id: h for h in self.investment_service.list_active() if h.id is not None
        }
        return self.projection_service.goal_forecasts(
            goals, self._goal_holding_repo, holdings_by_id
        )

    def holdings_by_id(self) -> dict:
        return {
            h.id: h
            for h in self.investment_service.list_active()
            if h.id is not None
        }

    def goal_linked_holding_ids(self, goal_id: int) -> list[int]:
        return self.goal_service.linked_holding_ids(goal_id)

    # --- UI helpers (keeps views free of repository imports) ---------------
    def account_options_active(self) -> list[tuple[int, str]]:
        return [(a.id, a.name) for a in self.account_service.get_all_active()]

    def account_name_map(self) -> dict[int, str]:
        return {
            a.id: a.name
            for a in self.account_service.get_all(include_archived=True)
            if a.id is not None
        }

    def income_categories(self) -> list[tuple[int, str]]:
        return self.category_service.list_by_kind("income")

    def expense_categories(self) -> list[tuple[int, str]]:
        return self.category_service.list_by_kind("expense")

    def income_source_options(self) -> list[tuple[int, str]]:
        return [(s.id, s.name) for s in self.income_source_service.list_active()]

    def has_mixed_currencies(self) -> bool:
        currencies = {
            a.currency or "INR"
            for a in self.account_service.get_all_active()
        }
        return len(currencies) > 1

    @staticmethod
    def account_has_loan_fields(account: Account) -> bool:
        return bool(
            (account.loan_outstanding or 0) > 0
            or (account.loan_principal or 0) > 0
            or account.loan_type
        )
