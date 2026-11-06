"""End to end: the New menu, every dialog's validation, one-click logging from
the Dashboard, reconciling, tracking an account's loan, and the backup copy
folder - through the real window, on the demo household."""
from __future__ import annotations

import sys

import pytest
from PyQt6.QtWidgets import QApplication, QPushButton

from config.account_fields import SECTIONS
from models.account import Account
from services.recurring_service import KIND_EMI, KIND_SIP
from tests.conftest import PROJECT_ROOT
from tests.test_smoke.test_e2e_user_session import Robot, _open, cancel, pick, save

pytestmark = pytest.mark.smoke


@pytest.fixture
def demo(tmp_path, qtbot, isolated_app_db):
    from ui.main_window import MainWindow

    sys.path.insert(0, str(PROJECT_ROOT / "tools"))
    from make_demo_store import build

    database, prefs, storage, ctx = _open(tmp_path / "data")
    build(ctx)
    window = MainWindow(ctx)
    qtbot.addWidget(window)
    yield ctx, window, storage
    window.deleteLater()
    QApplication.processEvents()
    database.close()


def test_every_new_menu_entry_opens_its_form(monkeypatch, demo):
    _ctx, window, _storage = demo
    robot = Robot(monkeypatch, QApplication.instance())
    opened = []

    def note(d):
        kind = getattr(d, "_current_type", None)
        opened.append((type(d).__name__, kind() if kind else None))
        cancel(d)

    for act, _icon in window._menu_actions:
        robot.then(note)
        act.trigger()
    assert opened == [
        ("TransactionDialog", "expense"), ("TransactionDialog", "income"),
        ("TransactionDialog", "transfer"), ("TransactionDialog", "investment_buy"),
        ("SectionEditDialog", None), ("HoldingDialog", None), ("LiabilityDialog", None),
        ("GoalDialog", None), ("BudgetDialog", None), ("IncomeDialog", None),
        ("ReminderDialog", None),
    ]
    robot.check()


def test_every_form_explains_what_is_missing(monkeypatch, demo):
    ctx, window, _storage = demo
    robot = Robot(monkeypatch, QApplication.instance())
    expense = {name: cid for cid, name in ctx.expense_categories()}
    bank = ctx.account_options_active()[0][0]

    def expect_refusal(fill):
        def handler(d):
            fill(d)
            before = len(robot.messages)
            save(d)
            QApplication.processEvents()
            assert d.isVisible(), f"{type(d).__name__} accepted bad input"
            assert len(robot.messages) == before + 1, f"{type(d).__name__} refused silently"
            cancel(d)
        return handler

    def expense_zero(d):
        pick(d.account_combo, bank)

    def transfer_to_itself(d):
        d.type_seg._buttons["transfer"].click()
        d.amount_spin.setValue(100)
        pick(d.account_combo, bank)
        pick(d.counter_combo, bank)

    cases = [
        (lambda: window.quick_add("expense"), expense_zero),
        (lambda: window.quick_add("transfer"), transfer_to_itself),
        (window.pages["accounts"].on_add, lambda d: None),                 # no name
        (window.pages["budgets"].on_add,
         lambda d: pick(d.category_combo, expense["Healthcare"])),        # no limit
        (window.pages["investments"].on_add,
         lambda d: d.invested_spin.setValue(1_000)),                      # no name
        (window.pages["investments"].on_add,
         lambda d: (d.name_edit.setText("Fund"))),                        # nothing invested
        (window.pages["investments"].on_add,
         lambda d: (d.name_edit.setText("Term plan"),
                    pick(d.type_combo, "term_insurance"))),               # no cover amount
        (window.pages["liabilities"].on_add,
         lambda d: d.name_edit.setText("Loan")),                          # nothing owed
        (window.pages["income"].on_add, lambda d: None),                  # no name
        (window.pages["goals"].on_add, lambda d: None),                   # no name
    ]
    for open_form, fill in cases:
        robot.then(expect_refusal(fill))
        open_form()
    assert all(kind == "warning" for kind, _t, _x in robot.messages), robot.messages
    assert not robot.problems and not robot.handlers


def test_dashboard_logs_a_due_sip_and_emi_in_one_click(monkeypatch, demo):
    ctx, window, _storage = demo
    robot = Robot(monkeypatch, QApplication.instance())
    dash = window.pages["dashboard"]
    salary = next(a for a in ctx.account_service.get_all() if a.name == "Salary Account")
    start = ctx.account_service.get_account(salary.id).current_balance
    items = {i.kind: i for i in ctx.recurring_service.due_items()}
    sip, emi = items[KIND_SIP], items[KIND_EMI]
    loan_before = ctx.liability_service.get(emi.ref_id)
    fund_before = ctx.investment_service.get(sip.ref_id)

    robot.then(save, save)
    dash._log(sip)
    dash._log(emi)

    assert ctx.account_service.get_account(salary.id).current_balance == start - sip.amount - emi.amount
    fund = ctx.investment_service.get(sip.ref_id)
    assert fund.invested_amount == fund_before.invested_amount + sip.amount
    loan = ctx.liability_service.get(emi.ref_id)
    assert loan.outstanding < loan_before.outstanding
    assert loan.remaining_months == loan_before.remaining_months - 1
    keys = {i.key for i in ctx.recurring_service.due_items()}
    assert sip.key not in keys and emi.key not in keys            # offered once
    robot.check()


def test_reconcile_and_track_a_loan_from_the_accounts_page(monkeypatch, demo):
    ctx, window, _storage = demo
    robot = Robot(monkeypatch, QApplication.instance())
    accounts = window.pages["accounts"]
    window.navigate("accounts")
    cash = next(a for a in ctx.account_service.get_all() if a.name == "Cash")

    # A hand-edited balance (as if data/store/accounts.json was changed in Notepad).
    db = ctx.net_worth_service.db
    db.execute("UPDATE accounts SET current_balance = current_balance + 250 WHERE id = ?", (cash.id,))
    db.commit()
    accounts.refresh()
    assert cash.id in accounts._mismatch
    accounts.select(cash.id)
    accounts._reconcile()
    assert ctx.account_service.reconciliation_report() == []

    # Describe a loan on an account, then track it in Liabilities in one click.
    loan_section = next(s for s in SECTIONS if s.key == "loan")
    accounts.select(cash.id)

    def describe_loan(d):
        pick(d._widgets["loan_type"], "personal_loan")
        d._widgets["loan_principal"].setValue(2_00_000)
        d._widgets["loan_outstanding"].setValue(1_50_000)
        d._widgets["loan_emi"].setValue(6_000)
        save(d)
    robot.then(describe_loan)
    accounts._edit_section(loan_section)
    owed_before = ctx.liability_service.total_outstanding()
    accounts.select(cash.id)
    accounts._track_loan()
    linked = ctx.liability_service.for_account(cash.id)
    assert linked is not None and linked.outstanding == 1_50_000
    assert ctx.liability_service.total_outstanding() == owed_before + 1_50_000
    robot.check()


def test_add_budget_from_the_spending_without_a_limit_banner(monkeypatch, demo):
    ctx, window, _storage = demo
    robot = Robot(monkeypatch, QApplication.instance())
    window.navigate("budgets")
    bp = window.pages["budgets"]
    banner = bp.extra_lay.itemAt(bp.extra_lay.count() - 1).widget()
    offered = {}

    def look(d):
        offered["category"] = d.category_combo.currentText()
        d.amount_spin.setValue(30_000)
        save(d)
    robot.then(look)
    next(b for b in banner.findChildren(QPushButton) if b.text() == "Add budget").click()
    assert offered["category"] == "Rent"                    # largest spending without a limit
    assert any(s.category_name == "Rent" for s in ctx.budget_service.statuses())
    robot.check()


def test_backup_copy_folder_can_be_set_and_stopped(monkeypatch, demo, tmp_path):
    ctx, window, storage = demo
    robot = Robot(monkeypatch, QApplication.instance())
    window.navigate("settings")
    sp = window.pages["settings"]
    robot.folder = str(tmp_path / "OneDrive")
    sp._choose_mirror()
    copies = tmp_path / "OneDrive" / "PersonalFinanceBackups"
    assert ctx.preferences.get("backup_mirror_dir") == str(copies)
    assert any(copies.iterdir())
    assert sp.clear_mirror_btn.isVisibleTo(sp)
    sp._clear_mirror()
    assert ctx.preferences.get("backup_mirror_dir") == ""
    count = len(list(copies.iterdir()))
    storage.backup("manual")                                 # no longer copied there
    assert len(list(copies.iterdir())) == count
    robot.check()


def test_a_long_ledger_stays_responsive_through_a_theme_change(qtbot, tmp_path, isolated_app_db):
    """Filling the ledger used to re-fit its columns after every cell - rows x rows
    work that froze the app for minutes after a theme change with a few years of
    history on screen. 3,000 rows must refresh in well under the old ~10 s."""
    import time

    from ui.main_window import MainWindow
    from ui.theme import theme

    database, _prefs, _storage, ctx = _open(tmp_path / "data")
    bank = ctx.account_service.create_account(
        Account(name="Bank", account_type="savings", current_balance=0))
    database.conn.executemany(
        "INSERT INTO transactions (txn_date, txn_type, amount, account_id, description) "
        "VALUES (?, 'expense', ?, ?, ?)",
        [(f"20{10 + i % 15:02d}-{1 + i % 12:02d}-{1 + i % 28:02d}", 100 + i, bank, f"Item {i}")
         for i in range(3_000)])
    database.commit()
    app = QApplication.instance()
    theme.install(app, "light")
    window = MainWindow(ctx)
    qtbot.addWidget(window)
    try:
        window.show()
        window.navigate("transactions")
        tx = window.pages["transactions"]
        tx.period_combo.setCurrentIndex(tx.period_combo.findText("All time"))
        assert tx.table.rowCount() == 3_000
        theme.set_mode("dark")                  # restyles everything; then refill the ledger
        app.processEvents()
        started = time.perf_counter()
        tx.refresh()
        app.processEvents()
        assert time.perf_counter() - started < 4.0
        assert tx.table.rowCount() == 3_000
    finally:
        window.deleteLater()
        app.processEvents()
        app.setStyleSheet("")
        theme.mode = "system"
        database.close()


def test_no_widget_flashes_up_as_a_window_of_its_own(qtbot, monkeypatch, tmp_path, isolated_app_db):
    """A widget made visible before it has a parent opens as its own window for a
    moment - on Windows a visible flicker. Start-up used to show 51 of them."""
    from PyQt6.QtCore import QEvent, QObject
    from PyQt6.QtWidgets import QDialog, QMainWindow, QWidget

    from ui.main_window import MainWindow

    sys.path.insert(0, str(PROJECT_ROOT / "tools"))
    from make_demo_store import build

    shown: list = []

    class Spy(QObject):
        def eventFilter(self, obj, event):  # noqa: N802
            if event.type() == QEvent.Type.Show and isinstance(obj, QWidget) and obj.isWindow():
                shown.append(obj)
            return False

    app = QApplication.instance()
    spy = Spy()
    app.installEventFilter(spy)
    database, _prefs, _storage, ctx = _open(tmp_path / "data")
    try:
        build(ctx)
        window = MainWindow(ctx)
        qtbot.addWidget(window)
        window.show()
        for i in range(window.sidebar.count()):                 # every page ...
            window.sidebar.setCurrentRow(i)
            page = window.stack.currentWidget()
            if hasattr(page, "select"):                          # ... every detail panel
                for tile in list(page._tiles):
                    page.select(tile.key)
            app.processEvents()
        robot = Robot(monkeypatch, app)
        for act, _icon in window._menu_actions:                 # ... every form
            robot.then(cancel)
            act.trigger()
        stray = [type(w).__name__ for w in shown if not isinstance(w, (QDialog, QMainWindow))]
        assert stray == [], stray
    finally:
        app.removeEventFilter(spy)
        database.close()
