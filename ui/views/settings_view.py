"""Settings - appearance, where your data lives, backups, exchange rates."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QDoubleSpinBox,
    QFileDialog,
    QHBoxLayout,
    QMessageBox,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from config.settings import settings
from services.app_context import AppContext
from services.store_migrations import STORE_VERSION
from ui.helpers.budget_text import YEAR_START_OPTIONS
from ui.theme import theme
from ui.widgets.common import (
    Card,
    PageHeader,
    SegmentedControl,
    StatGrid,
    button,
    clear_layout,
    label,
)
from ui.widgets.toast import notify
from utils.formatters import fmt_date

THEMES = [("system", "Match Windows"), ("light", "Light"), ("dark", "Dark")]


def _open(path: Optional[Path]) -> None:
    if path is not None:
        path.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))


class SettingsView(QWidget):
    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self.ctx = ctx
        self._topics = {"accounts", "fx_rates", "budgets"}
        self._dirty = True
        self.ctx.events.changed.connect(self._on_data_changed)
        self._build()
        self.refresh()

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        page = QWidget()
        root = QVBoxLayout(page)
        root.setContentsMargins(28, 24, 28, 28)
        root.setSpacing(18)
        scroll.setWidget(page)
        outer.addWidget(scroll)
        root.addWidget(PageHeader("Settings", "Appearance, your data and backups."))

        # Appearance
        look = Card("Appearance", "Light, dark, or follow your Windows setting.")
        self.theme_seg = SegmentedControl(THEMES, self.ctx.preferences.get("theme") or "system")
        self.theme_seg.changed.connect(self._set_theme)
        look.body.addWidget(self.theme_seg)
        root.addWidget(look)

        # Budgets
        budgets = Card("Budgets", "Monthly limits follow the calendar month. Choose when the "
                                  "year of a yearly limit begins.")
        self.year_seg = SegmentedControl(YEAR_START_OPTIONS,
                                         str(self.ctx.budget_service.year_start()))
        self.year_seg.changed.connect(self._set_year_start)
        budgets.body.addWidget(self.year_seg)
        root.addWidget(budgets)

        # Data
        self.data_card = Card("Your data", "Plain JSON files you can open in any text editor, "
                                          "now or in 20 years.")
        self.data_stats = StatGrid(2)
        self.data_card.body.addWidget(self.data_stats)
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(button("Open data folder", "secondary", "folder",
                             on_click=lambda: _open(self.ctx.data_folder())))
        row.addStretch(1)
        self.data_card.body.addLayout(row)
        root.addWidget(self.data_card)

        # Backups
        self.backup_card = Card(
            "Backups",
            "A copy is taken every time the app opens and closes. The latest 30 are always "
            "kept; older ones are thinned out to one per day for a month, one per month for "
            "two years, and one per year forever.")
        self.backup_stats = StatGrid(2)
        self.backup_card.body.addWidget(self.backup_stats)
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(button("Back up now", "primary", "save", on_click=self._backup_now))
        row.addWidget(button("Open backups folder", "secondary", "folder",
                             on_click=lambda: _open(self.ctx.backup_folder())))
        row.addStretch(1)
        self.backup_card.body.addLayout(row)

        self.backup_card.body.addWidget(label("Second copy", "cardTitle"))
        self.backup_card.body.addWidget(label(
            "Also copy every backup to another folder - ideally a cloud-synced one such as "
            "OneDrive - so a disk failure can't take your history with it.", "muted", wrap=True))
        mirror_row = QHBoxLayout()
        mirror_row.setSpacing(8)
        self.mirror_label = label("", "statValue", wrap=True, selectable=True)
        mirror_row.addWidget(self.mirror_label, 1)
        mirror_row.addWidget(button("Choose folder...", "secondary", "folder", on_click=self._choose_mirror))
        self.clear_mirror_btn = button("Stop copying", "ghost", on_click=self._clear_mirror)
        mirror_row.addWidget(self.clear_mirror_btn)
        self.backup_card.body.addLayout(mirror_row)
        root.addWidget(self.backup_card)

        # FX
        self.fx_card = Card("Exchange rates",
                            "Accounts in other currencies are converted to rupees with these "
                            "rates. Update them whenever you like.")
        self.fx_rows = QVBoxLayout()
        self.fx_rows.setSpacing(8)
        self.fx_card.body.addLayout(self.fx_rows)
        root.addWidget(self.fx_card)

        # About
        about = Card("About")
        about_stats = StatGrid(3)
        about_stats.set_items([
            ("Version", settings.APP_VERSION),
            ("Data format", f"v{STORE_VERSION}"),
            ("Shortcuts", "Ctrl+N new transaction · Ctrl+1-9 and Ctrl+0 pages"),
        ])
        about.body.addWidget(about_stats)
        root.addWidget(about)
        root.addStretch(1)

    # -------------------------------------------------------------- refresh
    def _on_data_changed(self, topic: str) -> None:
        if topic in self._topics:
            self._dirty = True

    def mark_dirty(self) -> None:
        self._dirty = True

    def ensure_fresh(self) -> None:
        self.refresh()

    def refresh(self) -> None:
        storage = self.ctx.storage
        store = self.ctx.data_folder()
        saved = storage.last_saved_at.strftime("%d %b %Y, %I:%M %p") if storage and storage.last_saved_at else "Not yet this session"
        if storage and storage.last_error:
            saved = f"Last save failed: {storage.last_error}"
        self.data_stats.set_items([
            ("Data folder", str(store) if store else "Not available"),
            ("Last saved", saved, "negative" if storage and storage.last_error else None),
        ])

        latest = storage.latest_backup() if storage else None
        when = "-"
        if latest is not None:
            stamp = latest.name[:15]
            when = f"{fmt_date(stamp[:4] + '-' + stamp[4:6] + '-' + stamp[6:8])} {stamp[9:11]}:{stamp[11:13]}"
        self.backup_stats.set_items([
            ("Backups kept", str(storage.backup_count()) if storage else "-"),
            ("Newest backup", when),
        ])
        self.year_seg.set_current(str(self.ctx.budget_service.year_start()))
        mirror = self.ctx.preferences.get("backup_mirror_dir") or ""
        self.mirror_label.setText(mirror or "Not set")
        self.clear_mirror_btn.setVisible(bool(mirror))
        self._refresh_fx()
        self._dirty = False

    def _refresh_fx(self) -> None:
        clear_layout(self.fx_rows)
        used = {a.currency or "INR" for a in self.ctx.account_service.get_all_active()}
        rates = {r.currency: r for r in self.ctx.fx_service.list_rates()}
        currencies = sorted((used | set(rates)) - {"INR"})
        if not currencies:
            self.fx_rows.addWidget(label("All your accounts are in rupees - nothing to convert.", "muted"))
            return
        for ccy in currencies:
            row = QHBoxLayout()
            row.setSpacing(10)
            row.addWidget(label(f"1 {ccy} =", "rowTitle"))
            spin = QDoubleSpinBox()
            spin.setRange(0.0, 1_000_000.0)
            spin.setDecimals(4)
            spin.setPrefix("₹ ")
            r = rates.get(ccy)
            spin.setValue(r.rate_to_inr if r else 0.0)
            spin.setMinimumWidth(160)
            row.addWidget(spin)
            row.addWidget(button("Save", "secondary", size="small",
                                 on_click=lambda c=ccy, s=spin: self._save_rate(c, s.value())))
            status = (f"Set {fmt_date(r.as_of)}" if r and r.as_of else "No rate yet - not counted in totals")
            row.addWidget(label(status, "small", tone=None if r else "warning"), 1)
            holder = QWidget()
            holder.setLayout(row)
            self.fx_rows.addWidget(holder)

    # --------------------------------------------------------------- actions
    def _set_theme(self, mode: str) -> None:
        self.ctx.preferences.set("theme", mode)
        theme.set_mode(mode)

    def _set_year_start(self, key: str) -> None:
        self.ctx.budget_service.set_year_start(int(key))
        notify("Yearly budgets now run " + ("April to March" if key == "4" else "January to December"))

    def _backup_now(self) -> None:
        storage = self.ctx.storage
        if storage is None:
            return
        try:
            storage.save()
        except Exception as e:
            QMessageBox.warning(self, "Backup", f"Saving failed, so no backup was made:\n{e}")
            return
        path = storage.backup("manual")
        self.refresh()
        notify("Backup created" if path else "Backup failed - see the log")

    def _choose_mirror(self) -> None:
        start = self.ctx.preferences.get("backup_mirror_dir") or str(Path.home())
        folder = QFileDialog.getExistingDirectory(self, "Choose a folder for backup copies", start)
        if not folder:
            return
        target = str(Path(folder) / "PersonalFinanceBackups")
        self.ctx.preferences.set("backup_mirror_dir", target)
        if self.ctx.storage is not None:
            self.ctx.storage.backup("manual")
        self.refresh()
        notify("Backups will also be copied there")

    def _clear_mirror(self) -> None:
        self.ctx.preferences.set("backup_mirror_dir", "")
        self.refresh()

    def _save_rate(self, currency: str, value: float) -> None:
        try:
            self.ctx.fx_service.set_rate(currency, value)
        except ValueError as e:
            QMessageBox.warning(self, "Exchange rate", str(e))
            return
        self.refresh()
        notify(f"{currency} rate saved")

    def sync_theme_choice(self) -> None:
        self.theme_seg.set_current(self.ctx.preferences.get("theme") or "system")
