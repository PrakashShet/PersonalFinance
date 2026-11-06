"""UI smoke tests - headless PyQt6 window construction, navigation, theming."""
from __future__ import annotations

import pytest
from PyQt6.QtWidgets import QApplication, QListWidget, QStackedWidget

from models.account import Account
from models.holding import Holding
from models.liability import Liability

pytestmark = pytest.mark.smoke


def test_main_window_loads_all_nav_pages(qtbot, isolated_app_db):
    from ui.main_window import NAV, MainWindow

    window = MainWindow()
    qtbot.addWidget(window)

    assert isinstance(window.sidebar, QListWidget)
    assert isinstance(window.stack, QStackedWidget)
    assert window.sidebar.count() == len(NAV)
    assert window.stack.count() == len(NAV)

    labels = [window.sidebar.item(i).text() for i in range(window.sidebar.count())]
    assert labels[0] == "Dashboard"
    assert "Transactions" in labels
    assert "Accounts" in labels
    assert "Settings" in labels


def test_main_window_nav_switch(qtbot, isolated_app_db):
    from ui.main_window import MainWindow

    window = MainWindow()
    qtbot.addWidget(window)

    window.sidebar.setCurrentRow(2)  # Transactions
    assert window.stack.currentIndex() == 2

    window.sidebar.setCurrentRow(1)  # Accounts
    assert window.stack.currentIndex() == 1


def test_main_window_nav_switch_all_pages(qtbot, isolated_app_db):
    """Every nav page can be switched to without raising."""
    from ui.main_window import MainWindow

    window = MainWindow()
    qtbot.addWidget(window)

    for i in range(window.sidebar.count()):
        window.sidebar.setCurrentRow(i)
        assert window.stack.currentIndex() == i
        assert window.stack.currentWidget() is not None


def test_pages_render_with_data_in_both_themes(qtbot, isolated_app_db):
    """Populate every page, then switch light <-> dark: nothing may raise and the
    stylesheet must have every $token filled."""
    from services.app_context import AppContext
    from ui.main_window import MainWindow
    from ui.theme import theme

    ctx = AppContext.create(isolated_app_db)
    bank = ctx.account_service.create_account(
        Account(name="HDFC Savings", account_type="savings", current_balance=250_000.0))
    ctx.account_service.create_account(
        Account(name="US Brokerage", account_type="savings", currency="USD", current_balance=1_000.0))
    ctx.investment_service.add_holding(Holding(
        name="Index Fund", holding_type="sip", invested_amount=100_000.0, current_value=118_000.0,
        sip_amount=5_000.0, sip_day_of_month=1, linked_account_id=bank, purchase_date="2024-01-10"))
    ctx.investment_service.add_holding(Holding(
        name="Term Plan", holding_type="term_insurance", sum_assured=10_000_000.0,
        premium_amount=18_000.0))
    ctx.liability_service.create(Liability(
        name="Car loan", liability_type="car_loan", principal=600_000.0, outstanding=400_000.0,
        interest_rate=9.5, emi_amount=12_500.0, remaining_months=36, next_due_date="2020-01-05",
        account_id=bank))

    app = QApplication.instance()
    theme.install(app, "light")
    try:
        window = MainWindow(ctx)
        qtbot.addWidget(window)
        for mode in ("dark", "light"):
            theme.set_mode(mode)
            assert "$" not in app.styleSheet()
            for i in range(window.sidebar.count()):
                window.sidebar.setCurrentRow(i)
                QApplication.processEvents()
        dash = window.pages["dashboard"]
        assert dash.attention_list.count() > 0          # overdue EMI + due SIP
        assert "USD" in "".join(
            dash.banners.itemAt(i).widget().text.text() for i in range(dash.banners.count()))
    finally:
        app.setStyleSheet("")
        theme.mode = "system"


def test_nav_shortcuts_cover_ten_pages():
    from ui.main_window import NAV, nav_shortcut

    assert [nav_shortcut(i) for i in (0, 8, 9, 10)] == ["Ctrl+1", "Ctrl+9", "Ctrl+0", ""]
    assert len(NAV) <= 10, "an eleventh page would have no keyboard shortcut"


def test_tones_show_on_role_labels(qtbot, isolated_app_db):
    """A #role rule outranks a bare [tone] rule; the stylesheet must repeat the
    tones per role or red / green values silently render as plain text.
    (isolated_app_db: windows from earlier tests still listen for theme changes.)"""
    from PyQt6.QtGui import QPalette

    from ui.theme import theme
    from ui.widgets.common import label

    app = QApplication.instance()
    theme.install(app, "light")
    try:
        for role in ("statValue", "kpiValue", "kpiHint", "rowValue", "tileValue", "small", "fieldHint"):
            for tone in ("negative", "positive", "warning"):
                lbl = label("x", role, tone=tone)
                qtbot.addWidget(lbl)
                lbl.ensurePolished()
                shown = lbl.palette().color(QPalette.ColorRole.WindowText).name().lower()
                assert shown == theme.color(tone).lower(), (role, tone)
    finally:
        app.setStyleSheet("")
        theme.mode = "system"


def test_budgets_page_dashboard_alert_and_expense_hint(qtbot, isolated_app_db):
    from datetime import date

    from models.transaction import Transaction
    from services.app_context import AppContext
    from ui.main_window import MainWindow
    from ui.theme import theme
    from ui.widgets.common import ElidedLabel

    from repositories.category_repo import CategoryRepository

    ctx = AppContext.create(isolated_app_db)
    bank = ctx.account_service.create_account(
        Account(name="HDFC Savings", account_type="savings", current_balance=100_000.0))
    repo = CategoryRepository(isolated_app_db)       # the empty test store has none
    cats = {name: repo.ensure(name, "expense") for name in ("Food & Dining", "Groceries", "Travel")}
    today = date.today().isoformat()
    for name, amount in (("Food & Dining", 9_000.0), ("Groceries", 7_000.0), ("Travel", 1_000.0)):
        ctx.transaction_service.create_transaction(Transaction(
            txn_date=today, txn_type="expense", amount=amount, account_id=bank,
            category_id=cats[name]))
    ctx.budget_service.set_limit(cats["Food & Dining"], "monthly", 8_000)   # over
    ctx.budget_service.set_limit(cats["Groceries"], "monthly", 8_000)       # 87.5 % - near
    ctx.budget_service.set_limit(cats["Travel"], "yearly", 50_000)          # fine

    app = QApplication.instance()
    theme.install(app, "light")
    try:
        window = MainWindow(ctx)
        qtbot.addWidget(window)
        window.navigate("budgets")
        page = window.pages["budgets"]
        for mode in ("dark", "light"):
            theme.set_mode(mode)
            QApplication.processEvents()
        assert len(page._tiles) == 3
        assert page.k_over.value_label.text() == "1"

        dash = window.pages["dashboard"]
        dash.refresh()
        titles = [lbl.full_text()
                  for i in range(dash.attention_list.count())
                  if dash.attention_list.itemAt(i).widget() is not None
                  for lbl in dash.attention_list.itemAt(i).widget().findChildren(ElidedLabel)]
        assert "Food & Dining is over budget" in titles
        assert "Groceries is near its limit" in titles

        # "See transactions" opens the ledger filtered to that category and period.
        food = next(s.budget.id for s in page._items if s.category_name == "Food & Dining")
        page.select(food)
        page._open_transactions()
        tx = window.pages["transactions"]
        assert window.stack.currentWidget() is tx
        assert tx.category_combo.currentData() == cats["Food & Dining"]
        assert tx.type_combo.currentData() == "expense"
        assert tx.table.rowCount() == 1

        # The expense dialog says what's left, then what typing an amount would do.
        dlg = tx._dialog(txn_type="expense")
        qtbot.addWidget(dlg)
        dlg.category_combo.setCurrentIndex(dlg.category_combo.findData(cats["Groceries"]))
        assert dlg.budget_label.isVisibleTo(dlg)
        assert "Groceries has ₹1,000 of ₹8,000 left this month." == dlg.budget_label.text()
        dlg.amount_spin.setValue(1_500)
        assert "would be ₹500 over" in dlg.budget_label.text()
        assert dlg.budget_label.property("tone") == "negative"
        dlg.category_combo.setCurrentIndex(0)                                # Uncategorised
        assert not dlg.budget_label.isVisibleTo(dlg)
    finally:
        app.setStyleSheet("")
        theme.mode = "system"
