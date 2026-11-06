"""Central wiring for repositories and services - injected into UI views.

Views receive an ``AppContext`` and call services (or the helpers below) only;
they never import ``db`` or ``repositories``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Optional

from PyQt6.QtCore import QObject, pyqtSignal

from db.connection import Database, db
from models.account import Account
from repositories.account_repo import AccountRepository
from repositories.budget_repo import BudgetRepository
from repositories.category_repo import CategoryRepository
from repositories.goal_holding_repo import GoalHoldingRepository
from repositories.goal_repo import GoalRepository
from repositories.holding_repo import HoldingRepository
from repositories.income_entry_repo import IncomeEntryRepository
from repositories.income_repo import IncomeRepository
from repositories.liability_repo import LiabilityRepository
from repositories.reference_repos import (
    FxRateRepository,
    ReminderRepository,
    StockMasterRepository,
)
from repositories.snapshot_repo import SnapshotRepository
from repositories.transaction_repo import TransactionRepository
from services.account_service import AccountService
from services.budget_service import BudgetService
from services.category_service import CategoryService
from services.fx_service import FxService
from services.goal_service import GoalService
from services.income_service import IncomeService
from services.income_source_service import IncomeSourceService
from services.investment_service import InvestmentService
from services.liability_service import LiabilityService
from services.net_worth_service import NetWorthService
from services.preferences_service import PreferencesService
from services.projection_service import ProjectionService
from services.recurring_service import RecurringService
from services.transaction_service import TransactionService

if TYPE_CHECKING:
    from services.storage import Storage


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
    fx_service: FxService = None                      # type: ignore[assignment]
    recurring_service: RecurringService = None        # type: ignore[assignment]
    budget_service: BudgetService = None              # type: ignore[assignment]
    preferences: PreferencesService = field(default_factory=PreferencesService)
    storage: Optional["Storage"] = None
    _holding_repo: HoldingRepository = field(repr=False, compare=False, default=None)
    _goal_holding_repo: GoalHoldingRepository = field(repr=False, compare=False, default=None)
    _income_repo: IncomeRepository = field(repr=False, compare=False, default=None)
    _liability_repo: LiabilityRepository = field(repr=False, compare=False, default=None)

    @classmethod
    def create(
        cls,
        database: Database | None = None,
        preferences: PreferencesService | None = None,
        storage: Optional["Storage"] = None,
    ) -> AppContext:
        database = database or db
        events = DataEvents()
        on_change: Callable[[str], None] = events.changed.emit
        preferences = preferences or PreferencesService(None)

        account_repo = AccountRepository(database)
        category_repo = CategoryRepository(database)
        holding_repo = HoldingRepository(database)
        liability_repo = LiabilityRepository(database)
        goal_repo = GoalRepository(database)
        goal_holding_repo = GoalHoldingRepository(database)
        income_repo = IncomeRepository(database)
        income_entry_repo = IncomeEntryRepository(database)
        transaction_repo = TransactionRepository(database)
        fx_repo = FxRateRepository(database)

        fx_service = FxService(fx_repo, on_change=on_change)
        transaction_service = TransactionService(
            transaction_repo, account_repo, on_change=on_change
        )
        account_service = AccountService(
            account_repo, transaction_service, category_repo,
            on_change=on_change, fx_service=fx_service,
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
        recurring_service = RecurringService(
            transaction_service, holding_repo, liability_repo,
            ReminderRepository(database), category_repo,
            income_source_service=income_source_service, on_change=on_change,
        )
        budget_service = BudgetService(
            BudgetRepository(database), transaction_repo, category_repo,
            fx_service=fx_service, preferences=preferences, on_change=on_change,
        )

        return cls(
            account_service=account_service,
            transaction_service=transaction_service,
            income_service=income_service,
            income_source_service=income_source_service,
            investment_service=InvestmentService(
                holding_repo, on_change=on_change, txn_repo=transaction_repo,
                stock_master=StockMasterRepository(database),
            ),
            liability_service=LiabilityService(liability_repo, on_change=on_change),
            goal_service=goal_service,
            category_service=CategoryService(category_repo),
            net_worth_service=NetWorthService(
                database, account_repo, holding_repo, liability_repo,
                fx_service=fx_service, snapshots=SnapshotRepository(database),
            ),
            projection_service=projection_service,
            events=events,
            fx_service=fx_service,
            recurring_service=recurring_service,
            budget_service=budget_service,
            preferences=preferences,
            storage=storage,
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

    def account_currencies(self) -> dict[int, str]:
        return {
            a.id: (a.currency or "INR")
            for a in self.account_service.get_all(include_archived=True)
            if a.id is not None
        }

    def income_categories(self) -> list[tuple[int, str]]:
        return self.category_service.list_by_kind("income")

    def expense_categories(self) -> list[tuple[int, str]]:
        return self.category_service.list_by_kind("expense")

    def income_source_options(self) -> list[tuple[int, str]]:
        return [(s.id, s.name) for s in self.income_source_service.list_active()]

    def holding_options(self) -> list[tuple[int, str]]:
        return [(h.id, h.name) for h in self.investment_service.investments()]

    def has_mixed_currencies(self) -> bool:
        currencies = {
            a.currency or "INR"
            for a in self.account_service.get_all_active()
        }
        return len(currencies) > 1

    def currencies_missing_rates(self) -> list[str]:
        """Currencies used by active accounts that have no FX rate yet."""
        used = {a.currency or "INR" for a in self.account_service.get_all_active()}
        return sorted(c for c in used if self.fx_service.rate(c) is None)

    @staticmethod
    def account_has_loan_fields(account: Account) -> bool:
        return LiabilityService.account_has_loan(account)

    # --- storage helpers ----------------------------------------------------
    def data_folder(self) -> Optional[Path]:
        return self.storage.store_dir if self.storage else None

    def backup_folder(self) -> Optional[Path]:
        return self.storage.backup_dir if self.storage else None
