"""End to end: opening a record's Edit dialog and pressing Save without changing
anything must leave the record exactly as it was.

Runs on the demo household (every kind of record, every investment type) and
goes through the real pages and dialogs. A dialog that silently resets a date,
drops a link or rounds a number fails here.
"""
from __future__ import annotations

import sys

import pytest
from PyQt6.QtWidgets import QApplication

from config.account_fields import SECTIONS
from tests.conftest import PROJECT_ROOT
from tests.test_smoke.test_e2e_user_session import Robot, _open, save

pytestmark = pytest.mark.smoke
IGNORED = {"updated_at"}


def _same(before, after) -> dict:
    a, b = before.to_dict(), after.to_dict()
    return {k: (a[k], b[k]) for k in a if k not in IGNORED and a[k] != b[k]}


@pytest.fixture
def demo(tmp_path):
    sys.path.insert(0, str(PROJECT_ROOT / "tools"))
    from make_demo_store import build

    database, prefs, storage, ctx = _open(tmp_path / "data")
    build(ctx)
    yield ctx, tmp_path / "data"
    database.close()


def test_saving_an_unchanged_record_changes_nothing(qtbot, monkeypatch, demo):
    from ui.main_window import MainWindow

    ctx, _home = demo
    robot = Robot(monkeypatch, QApplication.instance())
    window = MainWindow(ctx)
    qtbot.addWidget(window)
    diffs: dict[str, dict] = {}

    def check(label, before, after):
        d = _same(before, after)
        if d:
            diffs[label] = d

    # accounts, every section
    accounts = window.pages["accounts"]
    for a in ctx.account_service.get_all():
        for section in SECTIONS:
            accounts.select(a.id)
            robot.then(save)
            accounts._edit_section(section)
            check(f"account {a.name} / {section.title}", a, ctx.account_service.get_account(a.id))

    # one transaction of every shape
    tx = window.pages["transactions"]
    window.navigate("transactions")
    tx.period_combo.setCurrentIndex(tx.period_combo.findText("All time"))
    shapes = {}
    for r in tx._rows:
        key = (r["txn_type"], (r["tags"] or "").split(":")[0], bool(r["holding_id"]),
               bool(r["income_source_id"]), bool(r["counter_account_id"]))
        shapes.setdefault(key, r["id"])
    for key, txn_id in shapes.items():
        before = ctx.transaction_service.get_transaction(txn_id)
        tx.table.selectRow(next(i for i, r in enumerate(tx._rows) if r["id"] == txn_id))
        robot.then(save)
        tx._on_edit()
        check(f"transaction {key}", before, ctx.transaction_service.get_transaction(txn_id))

    # budgets
    bp = window.pages["budgets"]
    window.navigate("budgets")
    for b in ctx.budget_service.list_all():
        bp.select(b.id)
        robot.then(save)
        bp._edit()
        check(f"budget {b.id}", b, ctx.budget_service.get(b.id))

    # income sources and one recorded month each
    inc = window.pages["income"]
    window.navigate("income")
    for s in ctx.income_source_service.list_active():
        inc.select(s.id)
        robot.then(save)
        inc._edit()
        check(f"income {s.name}", s, ctx.income_source_service.get(s.id))
        entries = ctx.income_source_service.list_entries(s.id)
        if entries:
            inc.select(s.id)
            inc.history_table.selectRow(0)
            first = next(e for e in entries if e.id == inc._selected_entry().id)
            txn_before = ctx.transaction_service.get_transaction(first.transaction_id)
            robot.then(save)
            inc._edit_entry()
            after = next(e for e in ctx.income_source_service.list_entries(s.id)
                         if e.period_month == first.period_month)
            check(f"income month {s.name} {first.period_month}",
                  first.__class__(**{**first.to_dict(), "id": None, "transaction_id": None,
                                     "created_at": None}),
                  after.__class__(**{**after.to_dict(), "id": None, "transaction_id": None,
                                     "created_at": None}))
            txn_after = ctx.transaction_service.get_transaction(after.transaction_id)
            check(f"income month txn {s.name}",
                  txn_before.__class__(**{**txn_before.to_dict(), "id": None, "created_at": None}),
                  txn_after.__class__(**{**txn_after.to_dict(), "id": None, "created_at": None}))

    # every investment type
    inv = window.pages["investments"]
    window.navigate("investments")
    for h in ctx.investment_service.list_all(include_inactive=True):
        inv.select(h.id)
        robot.then(save)
        inv._edit()
        check(f"holding {h.name} ({h.holding_type})", h, ctx.investment_service.get(h.id))

    # liabilities
    lp = window.pages["liabilities"]
    window.navigate("liabilities")
    for lb in ctx.liability_service.list_all(include_inactive=True):
        lp.select(lb.id)
        robot.then(save)
        lp._edit()
        check(f"liability {lb.name}", lb, ctx.liability_service.get(lb.id))

    # goals, with their linked investments
    gp = window.pages["goals"]
    window.navigate("goals")
    gp._on_filter("all")
    for g in ctx.goal_service.list_all():
        links = ctx.goal_service.linked_holding_ids(g.id)
        gp.select(g.id)
        robot.then(save)
        gp._edit()
        check(f"goal {g.name}", g, ctx.goal_service.get(g.id))
        assert sorted(ctx.goal_service.linked_holding_ids(g.id)) == sorted(links), g.name

    window.deleteLater()                            # stop it listening to the theme
    QApplication.processEvents()
    robot.check()
    assert not diffs, "\n".join(f"{k}: {v}" for k, v in diffs.items())
