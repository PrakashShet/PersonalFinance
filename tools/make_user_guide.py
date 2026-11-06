"""Regenerate the user guide's screenshots from the fictional demo household.

Builds the demo store (tools/make_demo_store.py) in a throwaway folder, opens
the real app on it off-screen, and saves every page plus the main dialogs into
docs/user-guide/images/. It never reads your data: PFM_HOME points at the
throwaway folder, and that is checked before anything opens.

    python tools/make_user_guide.py
    python tools/make_user_guide.py --out some/other/folder

Run it after any visible UI change, then look at the images before committing.
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# What the Settings page shows as the data folder: the installed app's real
# default, with a placeholder user name instead of whoever ran this script.
SHOWN_DATA_DIR = r"C:\Users\you\AppData\Roaming\PersonalFinanceManager\data\store"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "docs" / "user-guide" / "images"))
    ap.add_argument("--size", default="1360x860")
    args = ap.parse_args()

    home = Path(tempfile.mkdtemp(prefix="pfm-guide-"))
    os.environ["PFM_HOME"] = str(home)
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / "tools"))
    os.chdir(ROOT)

    from PyQt6.QtWidgets import QApplication

    app = QApplication(sys.argv)

    from config.settings import settings
    from db.connection import db
    from make_demo_store import build
    from services.app_context import AppContext
    from services.recurring_service import KIND_EMI
    from services.storage import Storage
    from ui.dialogs.budget_dialog import BudgetDialog
    from ui.dialogs.quick_dialogs import LogPaymentDialog, UpdateBalanceDialog
    from ui.main_window import NAV, MainWindow
    from ui.theme import theme

    assert Path(settings.STORE_DIR).resolve().is_relative_to(home.resolve()), \
        "refusing to open real data"
    db.connect(":memory:")
    storage = Storage(db, settings.STORE_DIR, settings.BACKUP_DIR, settings.SEED_DIR,
                      settings.REFERENCE_DIR, settings.SCHEMA_PATH, settings.APP_VERSION)
    storage.open()
    ctx = AppContext.create(db, storage=storage)
    build(ctx)
    storage.save()
    ctx.data_folder = lambda: Path(SHOWN_DATA_DIR)          # see SHOWN_DATA_DIR

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    width, height = (int(x) for x in args.size.lower().split("x"))

    def settle() -> None:
        for _ in range(4):
            app.processEvents()

    def save(widget, name: str) -> None:
        widget.show()
        settle()
        path = out / name
        widget.grab().toImage().save(str(path), "PNG", 0)    # 0 = smallest file
        print(path.relative_to(ROOT) if path.is_relative_to(ROOT) else path)

    theme.install(app, "light")
    window = MainWindow(ctx)
    window.resize(width, height)
    window.show()
    cats = {name: cid for cid, name in ctx.expense_categories()}

    def show(key: str) -> None:
        window.navigate(key)
        settle()
        page = window.pages[key]
        if key == "budgets":
            food = next(s.budget.id for s in page._items if s.category_name == "Food & Dining")
            page.select(food)
        settle()

    # Every page, light theme.
    for i, (key, *_rest) in enumerate(NAV):
        show(key)
        save(window, f"{i + 1:02d}-{key}.png")

    # Dialogs.
    tx = window.pages["transactions"]
    tx._reload_accounts()
    dlg = tx._dialog(txn_type="expense")
    dlg.category_combo.setCurrentIndex(dlg.category_combo.findData(cats["Food & Dining"]))
    dlg.amount_spin.setValue(800)
    dlg.desc_edit.setText("Dinner with friends")
    save(dlg, "dialog-add-expense.png")
    dlg.close()

    budgets = window.pages["budgets"]
    dlg = BudgetDialog(ctx.expense_categories(), existing=budgets._existing,
                       suggest=budgets._suggest, year_text=budgets._year_text(),
                       category_id=cats["Utilities"], parent=window)
    save(dlg, "dialog-add-budget.png")
    dlg.close()

    cash = next(a for a in ctx.account_service.get_all_active() if a.name == "Cash")
    dlg = UpdateBalanceDialog(cash.name, cash.current_balance, cash.currency, parent=window)
    dlg.spin.setValue(cash.current_balance - 340)
    save(dlg, "dialog-update-balance.png")
    dlg.close()

    emi = next(i for i in ctx.recurring_service.due_items() if i.kind == KIND_EMI)
    dlg = LogPaymentDialog(emi.title, emi.amount, emi.due_date, ctx.account_options_active(),
                           emi.account_id, parent=window)
    save(dlg, "dialog-log-payment.png")
    dlg.close()

    # The dark theme, for a few pages.
    theme.set_mode("dark")
    for key in ("dashboard", "budgets"):
        show(key)
        index = next(i for i, entry in enumerate(NAV) if entry[0] == key)
        save(window, f"dark-{index + 1:02d}-{key}.png")

    window.close()
    db.close()
    shutil.rmtree(home, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
