"""Main application window — sidebar navigation + stacked content area."""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QStackedWidget,
    QWidget,
)

from config.settings import settings
from services.app_context import AppContext
from ui.views.accounts_view import AccountsView
from ui.views.dashboard_view import DashboardView
from ui.views.goals_view import GoalsView
from ui.views.income_view import IncomeView
from ui.views.investments_view import InvestmentsView
from ui.views.liabilities_view import LiabilitiesView
from ui.views.projections_view import ProjectionsView
from ui.views.transactions_view import TransactionsView


NAV_ITEMS = [
    ("Dashboard",    DashboardView),
    ("Accounts",     AccountsView),
    ("Transactions", TransactionsView),
    ("Income",       IncomeView),
    ("Investments",  InvestmentsView),
    ("Liabilities",  LiabilitiesView),
    ("Goals",        GoalsView),
    ("Projections",  ProjectionsView),
]


class MainWindow(QMainWindow):
    def __init__(self, ctx: AppContext | None = None) -> None:
        super().__init__()
        self.ctx = ctx or AppContext.create()
        self.setWindowTitle(f"{settings.APP_NAME}  v{settings.APP_VERSION}")
        self.resize(1280, 800)

        # Central layout: sidebar | stacked content
        central = QWidget(self)
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.sidebar = QListWidget()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setFixedWidth(220)

        self.stack = QStackedWidget()

        for label, view_cls in NAV_ITEMS:
            item = QListWidgetItem(label)
            item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            self.sidebar.addItem(item)
            self.stack.addWidget(view_cls(self.ctx))

        self.sidebar.currentRowChanged.connect(self._on_nav_changed)
        self.sidebar.setCurrentRow(0)

        layout.addWidget(self.sidebar)
        layout.addWidget(self.stack, 1)
        self.setCentralWidget(central)

    def _on_nav_changed(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        page = self.stack.currentWidget()
        if page is None:
            return
        ensure_fresh = getattr(page, "ensure_fresh", None)
        if callable(ensure_fresh):
            ensure_fresh()
            return
        refresh = getattr(page, "refresh", None)
        if callable(refresh):
            refresh()
