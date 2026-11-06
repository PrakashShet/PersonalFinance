"""Main window - sidebar navigation, quick add, theme switch, save status."""
from __future__ import annotations

from PyQt6.QtCore import QSize, Qt, QTimer
from PyQt6.QtGui import QAction, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from config.settings import settings
from services.app_context import AppContext
from ui import navigation
from ui.theme import icons, theme
from ui.views.accounts_view import AccountsView
from ui.views.budgets_view import BudgetsView
from ui.views.dashboard_view import DashboardView
from ui.views.goals_view import GoalsView
from ui.views.income_view import IncomeView
from ui.views.investments_view import InvestmentsView
from ui.views.liabilities_view import LiabilitiesView
from ui.views.projections_view import ProjectionsView
from ui.views.settings_view import SettingsView
from ui.views.transactions_view import TransactionsView
from ui.widgets import toast as toast_module
from ui.widgets.common import button, label, refresh_button_icon, repolish
from ui.widgets.toast import Toast

# (key, label, icon, view class) - list order is sidebar order.
NAV = [
    ("dashboard", "Dashboard", "dashboard", DashboardView),
    ("accounts", "Accounts", "accounts", AccountsView),
    ("transactions", "Transactions", "transactions", TransactionsView),
    ("budgets", "Budgets", "budget", BudgetsView),
    ("income", "Income", "income", IncomeView),
    ("investments", "Investments", "investments", InvestmentsView),
    ("liabilities", "Liabilities", "liabilities", LiabilitiesView),
    ("goals", "Goals", "goals", GoalsView),
    ("projections", "Projections", "projections", ProjectionsView),
    ("settings", "Settings", "settings", SettingsView),
]
NAV_ITEMS = [(text, cls) for _key, text, _icon, cls in NAV]


def nav_shortcut(index: int) -> str:
    """Ctrl+1 ... Ctrl+9, then Ctrl+0 for the tenth page; none after that."""
    return f"Ctrl+{(index + 1) % 10}" if index < 10 else ""
_THEME_BUTTONS = [("system", "monitor", "Match Windows"), ("light", "sun", "Light"), ("dark", "moon", "Dark")]


class MainWindow(QMainWindow):
    def __init__(self, ctx: AppContext | None = None) -> None:
        super().__init__()
        self.ctx = ctx or AppContext.create()
        self.setWindowTitle(settings.APP_NAME)
        self.resize(1360, 860)
        self.setMinimumSize(1080, 700)

        central = QWidget(self)
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._build_sidebar())

        self.stack = QStackedWidget()
        self.stack.setObjectName("content")
        self.pages: dict[str, QWidget] = {}
        for key, _text, _icon, view_cls in NAV:
            page = view_cls(self.ctx)
            self.pages[key] = page
            self.stack.addWidget(page)
        layout.addWidget(self.stack, 1)
        self.setCentralWidget(central)

        self.toast = Toast(central)
        toast_module.register(self.toast.show_message)
        navigation.register(self.navigate)

        # The visible page refreshes itself shortly after any data change
        # (other pages refresh lazily when you open them).
        self._live = QTimer(self)
        self._live.setSingleShot(True)
        self._live.setInterval(60)
        self._live.timeout.connect(self._refresh_current)
        self.ctx.events.changed.connect(lambda _t: self._live.start())

        self.sidebar.currentRowChanged.connect(self._on_nav_changed)
        self.sidebar.setCurrentRow(0)
        self._shortcuts()
        theme.changed.connect(self._on_theme_changed)

    # ------------------------------------------------------------- sidebar
    def _build_sidebar(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("sidebar")
        frame.setFixedWidth(232)
        col = QVBoxLayout(frame)
        col.setContentsMargins(14, 18, 14, 14)
        col.setSpacing(10)

        brand = QHBoxLayout()
        brand.setSpacing(10)
        self.brand_mark = QLabel()
        self.brand_mark.setObjectName("brandMark")
        self.brand_mark.setFixedSize(34, 34)
        self.brand_mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        brand.addWidget(self.brand_mark)
        names = QVBoxLayout()
        names.setSpacing(0)
        names.addWidget(label("Finance", "brandName"))
        names.addWidget(label("Personal finance manager", "brandSub"))
        brand.addLayout(names, 1)
        col.addLayout(brand)
        col.addSpacing(6)

        self.new_btn = button("New", "primary", "plus", tooltip="Add something (Ctrl+N adds an expense)")
        self.new_btn.setMenu(self._new_menu())
        col.addWidget(self.new_btn)
        col.addSpacing(4)

        self.sidebar = QListWidget()
        self.sidebar.setObjectName("nav")
        self.sidebar.setIconSize(QSize(18, 18))
        self.sidebar.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.sidebar.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.sidebar.setCursor(Qt.CursorShape.PointingHandCursor)
        for i, (_key, text, _icon, _cls) in enumerate(NAV):
            item = QListWidgetItem(text)
            item.setSizeHint(QSize(0, 38))
            shortcut = nav_shortcut(i)
            item.setToolTip(f"{text}  ({shortcut})" if shortcut else text)
            self.sidebar.addItem(item)
        col.addWidget(self.sidebar, 1)

        col.addWidget(label("Theme", "navSection"))
        seg = QFrame()
        seg.setObjectName("segmented")
        seg_row = QHBoxLayout(seg)
        seg_row.setContentsMargins(3, 3, 3, 3)
        seg_row.setSpacing(2)
        self._theme_group = QButtonGroup(self)
        self._theme_buttons: dict[str, QPushButton] = {}
        current = self.ctx.preferences.get("theme") or "system"
        for mode, icon_name, tip in _THEME_BUTTONS:
            b = QPushButton()
            b.setObjectName("segment")
            b.setCheckable(True)
            b.setToolTip(tip)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setProperty("iconName", icon_name)
            b.setChecked(mode == current)
            b.clicked.connect(lambda _c=False, m=mode: self.set_theme(m))
            self._theme_group.addButton(b)
            self._theme_buttons[mode] = b
            seg_row.addWidget(b, 1)
        col.addWidget(seg)

        self.save_status = label("All changes saved", "saveStatus", wrap=True)
        col.addWidget(self.save_status)
        self._paint_sidebar_icons()
        return frame

    def _new_menu(self) -> QMenu:
        menu = QMenu(self)
        entries = [
            ("Expense", "arrow_up_right", lambda: self.quick_add("expense")),
            ("Income", "arrow_down_left", lambda: self.quick_add("income")),
            ("Transfer", "transactions", lambda: self.quick_add("transfer")),
            ("Investment purchase", "investments", lambda: self.quick_add("investment_buy")),
            None,
            ("Account", "accounts", lambda: self._add_on("accounts")),
            ("Investment", "investments", lambda: self._add_on("investments")),
            ("Loan or card due", "liabilities", lambda: self._add_on("liabilities")),
            ("Goal", "goals", lambda: self._add_on("goals")),
            ("Budget", "budget", lambda: self._add_on("budgets")),
            ("Income source", "income", lambda: self._add_on("income")),
            ("Reminder", "bell", lambda: self.pages["dashboard"]._add_reminder()),
        ]
        self._menu_actions: list[tuple[QAction, str]] = []
        for entry in entries:
            if entry is None:
                menu.addSeparator()
                continue
            text, icon_name, fn = entry
            act = QAction(text, menu)
            act.triggered.connect(lambda _c=False, f=fn: f())
            menu.addAction(act)
            self._menu_actions.append((act, icon_name))
        return menu

    def _paint_sidebar_icons(self) -> None:
        muted, accent = theme.color("text_muted"), theme.color("accent_text")
        for i, (_key, _text, icon_name, _cls) in enumerate(NAV):
            item = self.sidebar.item(i)
            if item is not None:
                item.setIcon(icons.icon(icon_name, muted, accent))
        self.brand_mark.setPixmap(icons.pixmap("logo", theme.color("on_accent"), 18, 2.4))
        for b in self._theme_buttons.values():
            b.setIcon(icons.icon(b.property("iconName"), theme.color("text_secondary"), size=16))
            b.setIconSize(QSize(16, 16))
        for act, icon_name in getattr(self, "_menu_actions", []):
            act.setIcon(icons.icon(icon_name, theme.color("text_secondary"), size=16))

    # ---------------------------------------------------------- navigation
    def _shortcuts(self) -> None:
        QShortcut(QKeySequence("Ctrl+N"), self, activated=lambda: self.quick_add("expense"))
        for i in range(len(NAV)):
            if nav_shortcut(i):
                QShortcut(QKeySequence(nav_shortcut(i)), self,
                          activated=lambda idx=i: self.sidebar.setCurrentRow(idx))
        QShortcut(QKeySequence("F5"), self, activated=self._force_refresh)

    def _index(self, key: str) -> int:
        return next(i for i, entry in enumerate(NAV) if entry[0] == key)

    def navigate(self, key: str, **kwargs) -> None:
        if key not in self.pages:
            return
        self.sidebar.setCurrentRow(self._index(key))
        page = self.pages[key]
        if kwargs and hasattr(page, "show_with"):
            page.show_with(**kwargs)

    def quick_add(self, txn_type: str) -> None:
        """Add a transaction from anywhere without leaving the current page."""
        self.pages["transactions"].open_add(txn_type)

    def _add_on(self, key: str) -> None:
        self.navigate(key)
        page = self.pages[key]
        if hasattr(page, "on_add"):
            page.on_add()

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

    def _refresh_current(self) -> None:
        page = self.stack.currentWidget()
        ensure_fresh = getattr(page, "ensure_fresh", None)
        if callable(ensure_fresh):
            ensure_fresh()

    def _force_refresh(self) -> None:
        page = self.stack.currentWidget()
        if hasattr(page, "refresh"):
            page.refresh()

    # --------------------------------------------------------------- theme
    def set_theme(self, mode: str) -> None:
        self.ctx.preferences.set("theme", mode)
        theme.set_mode(mode)

    def _on_theme_changed(self) -> None:
        self._paint_sidebar_icons()
        mode = theme.mode
        if mode in self._theme_buttons:
            self._theme_buttons[mode].setChecked(True)
        settings_page = self.pages.get("settings")
        if settings_page is not None and hasattr(settings_page, "sync_theme_choice"):
            settings_page.sync_theme_choice()
        for btn in self.findChildren(QPushButton):
            if btn.property("iconName") and btn.objectName() != "segment":
                refresh_button_icon(btn)
        for page in self.pages.values():
            if hasattr(page, "mark_dirty"):
                page.mark_dirty()
            elif hasattr(page, "_dirty"):
                page._dirty = True
        self._refresh_current()

    # --------------------------------------------------------- save status
    def set_save_status(self, state: str, text: str) -> None:
        self.save_status.setText(text)
        self.save_status.setProperty("tone", "negative" if state == "error" else "")
        repolish(self.save_status)
        storage = self.ctx.storage
        self.save_status.setToolTip(storage.last_error if storage and storage.last_error else "")

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self.toast.isVisible():
            self.toast.show_message(self.toast.text())

