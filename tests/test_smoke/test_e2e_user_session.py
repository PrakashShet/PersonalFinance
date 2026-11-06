"""End to end: one user's session through the real window and dialogs.

Every dialog's ``exec()`` runs a scripted handler that fills the fields and
clicks the dialog's real Save button - so its own validation runs - exactly as
a person would. Message boxes are recorded; a dialog its handler could not
close is a failure. After the session the store is saved, reopened from the
JSON files in a fresh database, and audited with check_store.py.

Balances are worked out by hand in the comments.
"""
from __future__ import annotations

import os
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest
from PyQt6.QtCore import QDate
from PyQt6.QtGui import QShortcut
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QMessageBox,
)

from config.account_fields import ACCOUNT_SECTION
from config.settings import settings
from db.connection import Database
from services.app_context import AppContext
from services.budget_service import YEARLY, period_bounds, period_label
from services.preferences_service import PreferencesService
from services.storage import Storage
from tests.conftest import PROJECT_ROOT, SCHEMA_PATH

pytestmark = pytest.mark.smoke

TODAY = date.today()


# --------------------------------------------------------------------------
# the robot that answers dialogs
# --------------------------------------------------------------------------

class Robot:
    def __init__(self, monkeypatch, app) -> None:
        self.app = app
        self.handlers: list = []
        self.answers: list = []
        self.messages: list[tuple[str, str, str]] = []
        self.problems: list[str] = []
        self.folder = ""
        monkeypatch.setattr(QDialog, "exec", lambda dlg: self._exec(dlg))
        for kind in ("warning", "information", "critical"):
            monkeypatch.setattr(QMessageBox, kind, self._box(kind))
        monkeypatch.setattr(QMessageBox, "question", self._question)
        monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **k: self.folder)

    def then(self, *handlers) -> "Robot":
        self.handlers.extend(handlers)
        return self

    def _exec(self, dlg) -> int:
        name = f"{type(dlg).__name__} '{dlg.windowTitle()}'"
        if not self.handlers:
            self.problems.append(f"unexpected dialog {name}")
            return 0
        handler = self.handlers.pop(0)
        dlg.show()
        self.app.processEvents()
        before = len(self.messages)
        handler(dlg)
        self.app.processEvents()
        if dlg.isVisible():
            self.problems.append(f"{name} stayed open; messages: {self.messages[before:]}")
            dlg.reject()
        return dlg.result()

    def _box(self, kind):
        def show(parent, title, text, *args, **kwargs):
            self.messages.append((kind, title, text))
            return QMessageBox.StandardButton.Ok
        return show

    def _question(self, parent, title, text, *args, **kwargs):
        self.messages.append(("question", title, text))
        return self.answers.pop(0) if self.answers else QMessageBox.StandardButton.Yes

    def check(self) -> None:
        assert not self.problems, self.problems
        assert not self.handlers, f"{len(self.handlers)} scripted dialog(s) never opened"
        warnings = [m for m in self.messages if m[0] in ("warning", "critical")]
        assert not warnings, warnings


def save(dlg) -> None:
    box = dlg.findChild(QDialogButtonBox)
    btn = (box.button(QDialogButtonBox.StandardButton.Save)
           or box.button(QDialogButtonBox.StandardButton.Ok))
    btn.click()


def cancel(dlg) -> None:
    dlg.reject()


def pick(combo, data) -> None:
    idx = combo.findData(data)
    assert idx >= 0, f"{data!r} is not offered ({[combo.itemData(i) for i in range(combo.count())]})"
    combo.setCurrentIndex(idx)


def qdate(d: date) -> QDate:
    return QDate(d.year, d.month, d.day)


def account_form(name, kind, balance, currency="INR"):
    def fill(d):
        w = d._widgets
        w["name"].setText(name)
        pick(w["account_type"], kind)
        pick(w["currency"], currency)
        w["current_balance"].setValue(balance)
        save(d)
    return fill


def txn_form(kind, amount, account, category=None, to=None, note=None, again=False):
    def fill(d):
        seg = "investment" if kind.startswith("investment") else kind
        d.type_seg._buttons[seg].click()
        if seg == "investment":
            d.invest_seg._buttons[kind].click()
        d.amount_spin.setValue(amount)
        pick(d.account_combo, account)
        if to is not None:
            pick(d.counter_combo, to)
        if category is not None:
            pick(d.category_combo, category)
        if note:
            d.desc_edit.setText(note)
        if again:
            next(b for b in d.buttons.buttons() if "another" in b.text()).click()
        else:
            save(d)
    return fill


def attention_titles(dash) -> list[str]:
    from ui.widgets.common import ElidedLabel

    out = []
    for i in range(dash.attention_list.count()):
        w = dash.attention_list.itemAt(i).widget()
        if w is not None:
            out += [lbl.full_text() for lbl in w.findChildren(ElidedLabel)]
    return out


# --------------------------------------------------------------------------
# the session
# --------------------------------------------------------------------------

def _open(home: Path):
    database = Database()
    database.connect(":memory:")
    prefs = PreferencesService(home / "user" / "preferences.json")
    storage = Storage(database, home / "store", home / "user" / "backups", settings.SEED_DIR,
                      settings.REFERENCE_DIR, SCHEMA_PATH, app_version="e2e",
                      mirror_dir=lambda: prefs.get("backup_mirror_dir"))
    storage.open()
    return database, prefs, storage, AppContext.create(database, preferences=prefs, storage=storage)


def test_a_full_user_session_survives_a_restart(qtbot, monkeypatch, tmp_path, isolated_app_db):
    # isolated_app_db: windows left by earlier tests listen for theme changes.
    from ui.autosave import AutoSaver
    from ui.main_window import MainWindow
    from ui.theme import theme

    app = QApplication.instance()
    robot = Robot(monkeypatch, app)
    home = tmp_path / "data"
    database, prefs, storage, ctx = _open(home)
    theme.install(app, "light")
    saver = window = None
    try:
        window = MainWindow(ctx)
        qtbot.addWidget(window)
        window.show()
        saver = AutoSaver(storage, ctx.net_worth_service.take_snapshot, 50, 60)
        ctx.events.changed.connect(saver.request)
        expense = {name: cid for cid, name in ctx.expense_categories()}
        income_cat = {name: cid for cid, name in ctx.income_categories()}
        acc = ctx.account_service

        # --- accounts -------------------------------------------------------
        window.navigate("accounts")
        accounts = window.pages["accounts"]
        robot.then(account_form("HDFC Savings", "savings", 50_000))
        accounts.on_add()
        robot.then(account_form("Cash", "cash", 3_000))
        accounts.on_add()
        robot.then(account_form("US Brokerage", "savings", 1_000, currency="USD"))
        accounts.on_add()
        ids = {a.name: a.id for a in acc.get_all()}
        hdfc, cash, usd = ids["HDFC Savings"], ids["Cash"], ids["US Brokerage"]
        assert len(accounts._tiles) == 3

        accounts.select(cash)                                   # 3,000 -> 2,500
        robot.then(lambda d: (d.spin.setValue(2_500), save(d)))
        accounts._update_balance()
        assert acc.get_account(cash).current_balance == 2_500

        accounts.select(hdfc)                                   # rename; balance untouched
        robot.then(lambda d: (d._widgets["name"].setText("HDFC Savings A/c"), save(d)))
        accounts._edit_section(ACCOUNT_SECTION)
        assert acc.get_account(hdfc).name == "HDFC Savings A/c"
        assert acc.get_account(hdfc).current_balance == 50_000

        accounts.select(cash)
        accounts._toggle_archive()                              # confirm -> archived
        assert cash not in [a.id for a in acc.get_all_active()]
        accounts.inactive_check.setChecked(True)
        accounts.select(cash)
        accounts._toggle_archive()                              # restore
        accounts.inactive_check.setChecked(False)
        assert cash in [a.id for a in acc.get_all_active()]

        # --- transactions ---------------------------------------------------
        tx = window.pages["transactions"]
        robot.then(txn_form("expense", 1_200, hdfc, expense["Food & Dining"], note="Dinner"))
        window.quick_add("expense")                             # 50,000 -> 48,800
        robot.then(txn_form("expense", 300, hdfc, expense["Groceries"], note="Vegetables",
                            again=True), cancel)
        window.quick_add("expense")                             # -> 48,500
        robot.then(txn_form("income", 10_000, hdfc, income_cat["Salary"], note="Bonus"))
        window.quick_add("income")                              # -> 58,500
        robot.then(txn_form("transfer", 5_000, hdfc, to=cash, note="ATM"))
        window.quick_add("transfer")                            # 53,500; cash 7,500
        assert acc.get_account(hdfc).current_balance == 53_500
        assert acc.get_account(cash).current_balance == 7_500

        window.navigate("transactions")
        tx.period_combo.setCurrentIndex(tx.period_combo.findText("All time"))
        dinner = next(r["id"] for r in tx._rows if r["description"] == "Dinner")
        tx.table.selectRow(next(i for i, r in enumerate(tx._rows) if r["id"] == dinner))
        robot.then(lambda d: (d.amount_spin.setValue(1_500), save(d)))
        tx._on_edit()                                           # 1,200 -> 1,500: 53,200
        assert acc.get_account(hdfc).current_balance == 53_200

        veg = next(i for i, r in enumerate(tx._rows) if r["description"] == "Vegetables")
        tx.table.selectRow(veg)
        robot.then(save)
        tx._on_duplicate()                                      # another 300: 52,900
        assert acc.get_account(hdfc).current_balance == 52_900
        tx.table.selectRow(0)                                   # newest: the duplicate
        tx._on_delete()                                         # back to 53,200
        assert acc.get_account(hdfc).current_balance == 53_200

        tx.search_edit.setText("Vegetables")
        assert tx.table.rowCount() == 1
        tx.search_edit.clear()

        # --- budgets ----------------------------------------------------------
        window.navigate("budgets")
        bp = window.pages["budgets"]

        def budget_form(category, period, amount):
            def fill(d):
                pick(d.category_combo, category)
                d.period_seg._buttons[period].click()
                d.amount_spin.setValue(amount)
                save(d)
            return fill

        robot.then(budget_form(expense["Food & Dining"], "monthly", 1_000))
        bp.on_add()
        food = ctx.budget_service.for_category(expense["Food & Dining"])[0].id
        assert ctx.budget_service.status(food).state == "over"         # 1,500 of 1,000
        dash = window.pages["dashboard"]
        dash.refresh()
        assert "Food & Dining is over budget" in attention_titles(dash)

        bp.select(food)
        robot.then(lambda d: (d.amount_spin.setValue(5_000), save(d)))
        bp._edit()
        assert ctx.budget_service.status(food).state == "ok"           # 1,500 of 5,000

        robot.then(budget_form(expense["Travel"], "yearly", 50_000))
        bp.on_add()
        travel = ctx.budget_service.for_category(expense["Travel"])[0].id

        hint = {}

        def look_at_hint(d):
            d.type_seg._buttons["expense"].click()
            pick(d.category_combo, expense["Food & Dining"])
            hint["text"] = d.budget_label.text()
            cancel(d)
        robot.then(look_at_hint)
        window.quick_add("expense")
        assert hint["text"] == "Food & Dining has ₹3,500 of ₹5,000 left this month."

        window.navigate("settings")
        window.pages["settings"].year_seg._buttons["4"].click()        # financial year
        fy = period_label(YEARLY, period_bounds(YEARLY, TODAY, 4)[0])
        assert ctx.budget_service.status(travel).label == fy

        window.navigate("budgets")
        bp.select(travel)
        bp._delete()
        assert [b.id for b in ctx.budget_service.list_all()] == [food]

        # --- income -----------------------------------------------------------
        window.navigate("income")
        inc = window.pages["income"]

        def salary_form(d):
            d.name_edit.setText("Salary")
            pick(d.type_combo, "salary")
            pick(d.freq_combo, "monthly")
            pick(d.account_combo, hdfc)
            d.basic_spin.setValue(60_000)
            d.hra_spin.setValue(20_000)
            d.special_spin.setValue(20_000)
            d.pf_emp_spin.setValue(7_200)
            d.pt_spin.setValue(200)
            d.tds_spin.setValue(10_000)
            save(d)
        robot.then(salary_form)
        inc.on_add()
        source = ctx.income_source_service.list_active()[0]
        assert ctx.income_source_service.net_monthly(source) == 82_600   # 1,00,000 - 17,400

        defaults = {}

        def record(d):
            defaults["amount"] = d.amount_spin.value()
            defaults["account"] = d.account_combo.currentData()
            save(d)
        inc.select(source.id)
        robot.then(record)
        inc._record()                                           # 53,200 + 82,600 = 1,35,800
        assert defaults == {"amount": 82_600, "account": hdfc}
        assert acc.get_account(hdfc).current_balance == 1_35_800
        dash.refresh()
        assert "Income - Salary" not in attention_titles(dash)

        # --- investments --------------------------------------------------------
        window.navigate("investments")
        inv = window.pages["investments"]
        sip_day = min(TODAY.day, 28)

        def sip_form(d):
            d.name_edit.setText("Index Fund")
            pick(d.type_combo, "sip")
            d.invested_spin.setValue(50_000)
            d.current_spin.setValue(55_000)
            d.sip_amount_spin.setValue(5_000)
            d.sip_day_spin.setValue(sip_day)
            pick(d.account_combo, hdfc)
            save(d)
        robot.then(sip_form)
        inv.on_add()
        fund = next(h for h in ctx.investment_service.list_active() if h.name == "Index Fund")

        inv.select(fund.id)
        robot.then(save)                                        # pre-filled 5,000 from HDFC
        inv._log_sip()                                          # 1,35,800 - 5,000 = 1,30,800
        fund = ctx.investment_service.get(fund.id)
        assert (fund.invested_amount, fund.current_value) == (55_000, 60_000)
        assert acc.get_account(hdfc).current_balance == 1_30_800

        def term_form(d):
            d.name_edit.setText("Term Plan")
            pick(d.type_combo, "term_insurance")
            d.sum_assured_spin.setValue(1_00_00_000)
            d.premium_spin.setValue(15_000)
            d.premium_due.setDate(qdate(TODAY + timedelta(days=5)))
            pick(d.account_combo, hdfc)
            save(d)                                             # nothing invested: protection
        robot.then(term_form)
        inv.on_add()
        assert any(h.name == "Term Plan" for h in ctx.investment_service.list_active())

        def stock_form(d):
            d.name_edit.setText("Infosys")
            pick(d.type_combo, "stock")
            d.symbol_edit.setText("INFY")
            d.symbol_edit.editingFinished.emit()
            assert d.cap_combo.currentData() == "large_cap" and d.sector_edit.text() == "IT"
            d.qty_spin.setValue(10)
            d.avg_price_spin.setValue(1_500)
            d.cur_price_spin.setValue(1_600)
            assert (d.invested_spin.value(), d.current_spin.value()) == (15_000, 16_000)
            save(d)
        robot.then(stock_form)
        inv.on_add()
        infy = next(h for h in ctx.investment_service.list_active() if h.name == "Infosys")
        inv.select(infy.id)
        inv._toggle()                                           # sold / closed
        assert not ctx.investment_service.get(infy.id).is_active
        inv.inactive_check.setChecked(True)
        inv.select(infy.id)
        inv._delete()
        inv.inactive_check.setChecked(False)
        assert ctx.investment_service.get(infy.id) is None

        # --- liabilities ----------------------------------------------------------
        window.navigate("liabilities")
        lp = window.pages["liabilities"]
        due = TODAY + timedelta(days=3)

        def loan_form(d):
            d.name_edit.setText("Car loan")
            pick(d.type_combo, "car_loan")
            d.lender_edit.setText("Some Bank")
            pick(d.account_combo, hdfc)
            d.principal_spin.setValue(5_00_000)
            d.outstanding_spin.setValue(4_00_000)
            d.rate_spin.setValue(9.0)
            d.emi_spin.setValue(10_000)
            d.tenure_spin.setValue(60)
            d.remaining_spin.setValue(45)
            d.due_date.setDate(qdate(due))
            save(d)
        robot.then(loan_form)
        lp.on_add()
        loan = ctx.liability_service.list_active()[0]
        lp.select(loan.id)
        robot.then(save)
        lp._log_emi()               # interest 4,00,000 x 9 % / 12 = 3,000; principal 7,000
        loan = ctx.liability_service.get(loan.id)
        assert loan.outstanding == 3_93_000 and loan.remaining_months == 44
        assert loan.next_due_date[:7] == (due.replace(day=1) + timedelta(days=32)).strftime("%Y-%m")
        assert acc.get_account(hdfc).current_balance == 1_20_800

        # --- goals --------------------------------------------------------------
        window.navigate("goals")
        gp = window.pages["goals"]

        def goal_form(d):
            d.name_edit.setText("Emergency fund")
            d.target_spin.setValue(3_00_000)
            d.target_date.setDate(qdate(TODAY + timedelta(days=730)))
            d._holding_checks[fund.id].setChecked(True)
            save(d)
        robot.then(goal_form)
        gp.on_add()
        goal = ctx.goal_service.list_all()[0]
        assert goal.current_amount == 60_000                    # the linked fund's value
        gp.select(goal.id)
        gp._toggle()
        assert ctx.goal_service.get(goal.id).status == "paused"
        gp._on_filter("all")
        gp.select(goal.id)
        gp._toggle()
        assert ctx.goal_service.get(goal.id).status == "active"
        gp._delete()
        assert ctx.goal_service.list_all() == []

        # --- dashboard: reminder, premium -------------------------------------------
        window.navigate("dashboard")
        robot.then(lambda d: (d.title.setText("Renew car insurance"),
                              d.amount.setValue(12_000), save(d)))
        dash._add_reminder()
        items = ctx.recurring_service.due_items()
        reminder = next(i for i in items if i.title == "Renew car insurance")
        dash._done(reminder)
        premium = next(i for i in ctx.recurring_service.due_items() if i.kind == "premium")
        robot.then(save)
        dash._log(premium)                                      # 1,20,800 - 15,000 = 1,05,800
        assert acc.get_account(hdfc).current_balance == 1_05_800
        titles = attention_titles(dash)
        assert "Renew car insurance" not in titles and "Premium - Term Plan" not in titles

        # --- settings: exchange rate, theme, backups ------------------------------------
        window.navigate("settings")
        sp = window.pages["settings"]
        assert ctx.currencies_missing_rates() == ["USD"]
        sp._save_rate("USD", 83.0)
        assert ctx.currencies_missing_rates() == []
        bs = ctx.net_worth_service.compute()
        assert bs.cash_and_bank == 1_05_800 + 7_500 + 83_000
        sp.theme_seg._buttons["dark"].click()
        assert prefs.get("theme") == "dark" and theme.is_dark
        sp._backup_now()
        robot.folder = str(tmp_path / "cloud")
        sp._choose_mirror()
        assert any((tmp_path / "cloud" / "PersonalFinanceBackups").iterdir())

        # --- projections: an assumption is remembered ------------------------------------
        window.navigate("projections")
        pp = window.pages["projections"]
        pp.s_age.setValue(34)
        pp._debounce.timeout.emit()
        assert prefs.get("projection")["current_age"] == 34

        # --- keyboard: Ctrl+0 is the tenth page -------------------------------------------
        for sc in window.findChildren(QShortcut):
            if sc.key().toString() == "Ctrl+0":
                sc.activated.emit()
        assert window.stack.currentWidget() is window.pages["settings"]

        # every page still renders in both themes with all this data
        for mode in ("light", "dark"):
            theme.set_mode(mode)
            for i in range(window.sidebar.count()):
                window.sidebar.setCurrentRow(i)
                app.processEvents()

        robot.check()
        qtbot.wait(150)                                         # the debounced autosave ran
        assert storage.last_saved_at is not None and storage.last_error is None
        assert saver.save_now()
        storage.close(ctx.net_worth_service.take_snapshot)
        saver.stop()
    finally:
        if saver is not None:
            saver.stop()
        if window is not None:
            window.deleteLater()                    # stop it listening to the theme
            app.processEvents()
        app.setStyleSheet("")
        theme.mode = "system"
        database.close()

    # --- reopen from the files alone ---------------------------------------------------
    database2, prefs2, storage2, ctx2 = _open(home)
    try:
        a = {x.name: x for x in ctx2.account_service.get_all(include_archived=True)}
        assert a["HDFC Savings A/c"].current_balance == 1_05_800
        assert a["Cash"].current_balance == 7_500 and a["Cash"].is_active == 1
        assert a["US Brokerage"].current_balance == 1_000 and a["US Brokerage"].currency == "USD"
        assert [(b.period, b.amount) for b in ctx2.budget_service.list_all()] == [("monthly", 5_000)]
        holdings = {h.name: h for h in ctx2.investment_service.list_all(include_inactive=True)}
        assert set(holdings) == {"Index Fund", "Term Plan"}
        assert holdings["Index Fund"].current_value == 60_000
        assert ctx2.liability_service.list_active()[0].outstanding == 3_93_000
        assert ctx2.goal_service.list_all() == []
        assert ctx2.fx_service.rate("USD") == 83.0
        assert len(ctx2.income_source_service.list_entries(source.id)) == 1
        assert prefs2.get("theme") == "dark" and prefs2.get("budget_year_start") == 4
        assert prefs2.get("projection")["current_age"] == 34
        assert ctx2.net_worth_service.history(), "the daily snapshot was saved"
        labels = {p.name.split("_", 2)[-1] for p in (home / "user" / "backups").iterdir()}
        assert {"startup", "manual"} <= labels
    finally:
        database2.close()

    audit = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "docs" / "skills" / "data-hygiene" / "check_store.py"),
         "--store", str(home / "store")], capture_output=True, text=True, encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    assert audit.returncode == 0, audit.stdout
