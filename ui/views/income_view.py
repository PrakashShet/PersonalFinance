"""Income tab — master/detail.

Left:  list of income sources (name, type, deposit account, net/month, status).
Right: detail for the selected source — salary breakdown (for salary sources)
       plus a per-source monthly history with controls to record / edit / delete
       what was actually received each month.

Recording a month optionally posts an income transaction into the linked
deposit account so balances stay in sync (handled by IncomeService).
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from models.income import IncomeSource
from models.income_entry import IncomeEntry
from services.app_context import AppContext
from services.income_service import IncomeService
from ui.theme.badges import FALLBACK_BADGE, INCOME_SOURCE_BADGE
from ui.dialogs.income_dialog import IncomeDialog
from ui.dialogs.record_income_dialog import RecordIncomeDialog
from ui.widgets.income_source_tile import IncomeSourceTile
from ui.widgets.kpi_card import KpiCard
from utils.formatters import fmt_inr

# ── label / colour maps ──────────────────────────────────────────────────────

SOURCE_TYPE_LABELS: dict[str, str] = {
    "salary":    "Salary",
    "web_app":   "SaaS / Web App",
    "trading":   "Trading P&L",
    "rental":    "Rental",
    "freelance": "Freelance",
    "dividend":  "Dividend",
    "interest":  "Interest",
    "other":     "Other",
}

FREQ_LABELS: dict[str, str] = {
    "monthly":   "Monthly",
    "quarterly": "Quarterly",
    "annual":    "Annual",
    "irregular": "Irregular",
    "one_time":  "One-time",
}

HISTORY_COLS = ["Month", "Expected", "Actual", "Variance", "Account", "Posted", "Notes"]


# ── view ───────────────────────────────────────────────────────────────────

class IncomeView(QWidget):
    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self.ctx = ctx
        self._topics = {"income_sources", "income_entries", "accounts", "transactions"}
        self._dirty = True
        self._service = ctx.income_source_service

        self._sources: list[IncomeSource] = []
        self._entries: list[IncomeEntry] = []
        self._accounts: list[tuple] = []
        self._account_names: dict[int, str] = {}
        self._selected_id: Optional[int] = None
        self._tiles: list[IncomeSourceTile] = []

        self.ctx.events.changed.connect(self._on_data_changed)
        self._build()
        self.refresh()

    # -----------------------------------------------------------------------
    # Build
    # -----------------------------------------------------------------------

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(16)

        # ── header ──────────────────────────────────────────────────────────
        header = QHBoxLayout()
        title = QLabel("Income")
        title.setObjectName("pageTitle")
        header.addWidget(title)
        header.addStretch()
        self.add_btn = QPushButton("＋  Add Source")
        self.add_btn.setObjectName("primaryBtn")
        self.add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.add_btn.clicked.connect(self._on_add)
        header.addWidget(self.add_btn)
        root.addLayout(header)

        # ── KPI row ─────────────────────────────────────────────────────────
        kpi_row = QGridLayout()
        kpi_row.setSpacing(12)
        self.kpi_gross    = KpiCard("Gross Monthly",     "—")
        self.kpi_net      = KpiCard("Net Take-Home",     "—")
        self.kpi_deduct   = KpiCard("Deductions / Mo",   "—")
        self.kpi_received = KpiCard("Received This Month", "—")
        self.kpi_sources  = KpiCard("Active Sources",    "—")
        for i, w in enumerate(
            [self.kpi_gross, self.kpi_net, self.kpi_deduct, self.kpi_received, self.kpi_sources]
        ):
            kpi_row.addWidget(w, 0, i)
        root.addLayout(kpi_row)

        # ── splitter: sources (master) | detail ─────────────────────────────
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self._build_master())
        splitter.addWidget(self._build_detail())
        splitter.setSizes([520, 520])
        root.addWidget(splitter, 1)

    def _build_master(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # Scrollable list of source tiles
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.tile_container = QWidget()
        self.tile_layout = QVBoxLayout(self.tile_container)
        self.tile_layout.setContentsMargins(0, 4, 6, 4)
        self.tile_layout.setSpacing(10)
        self.tile_layout.addStretch(1)
        self.scroll.setWidget(self.tile_container)
        self.scroll.setMinimumHeight(240)
        layout.addWidget(self.scroll, 1)

        self.empty_label = QLabel('No income sources yet. Click "＋ Add Source" to create one.')
        self.empty_label.setObjectName("tileFlags")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setWordWrap(True)
        self.empty_label.hide()
        layout.addWidget(self.empty_label)

        action_bar = QHBoxLayout()
        self.edit_btn = QPushButton("✏  Edit")
        self.edit_btn.setEnabled(False)
        self.edit_btn.clicked.connect(self._on_edit)
        self.toggle_btn = QPushButton("⏸  Deactivate")
        self.toggle_btn.setEnabled(False)
        self.toggle_btn.clicked.connect(self._on_toggle_active)
        self.delete_btn = QPushButton("🗑  Delete")
        self.delete_btn.setEnabled(False)
        self.delete_btn.setObjectName("dangerBtn")
        self.delete_btn.clicked.connect(self._on_delete)
        action_bar.addWidget(self.edit_btn)
        action_bar.addWidget(self.toggle_btn)
        action_bar.addWidget(self.delete_btn)
        action_bar.addStretch()
        layout.addLayout(action_bar)
        return container

    def _build_detail(self) -> QWidget:
        # Stacked: placeholder when nothing selected, detail otherwise.
        self.detail_stack = QStackedWidget()

        placeholder = QLabel("Select an income source to see details and monthly history.")
        placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        placeholder.setObjectName("tileFlags")
        placeholder.setWordWrap(True)
        self.detail_stack.addWidget(placeholder)

        detail = QWidget()
        d = QVBoxLayout(detail)
        d.setContentsMargins(0, 0, 0, 0)
        d.setSpacing(12)

        self.detail_title = QLabel("—")
        f = self.detail_title.font()
        f.setBold(True)
        f.setPointSize(f.pointSize() + 2)
        self.detail_title.setFont(f)
        d.addWidget(self.detail_title)

        self.detail_subtitle = QLabel("")
        self.detail_subtitle.setObjectName("tileFlags")
        d.addWidget(self.detail_subtitle)

        # Salary breakdown (shown only for salary sources)
        self.breakdown_panel = _SalaryBreakdownPanel()
        self.breakdown_panel.setVisible(False)
        d.addWidget(self.breakdown_panel)

        # Monthly history
        hist_box = QGroupBox("Monthly History")
        hist_layout = QVBoxLayout(hist_box)
        hist_layout.setSpacing(6)

        hist_actions = QHBoxLayout()
        self.record_btn = QPushButton("＋  Record Income")
        self.record_btn.setObjectName("primaryBtn")
        self.record_btn.clicked.connect(self._on_record)
        self.edit_entry_btn = QPushButton("✏  Edit")
        self.edit_entry_btn.setEnabled(False)
        self.edit_entry_btn.clicked.connect(self._on_edit_entry)
        self.delete_entry_btn = QPushButton("🗑  Delete")
        self.delete_entry_btn.setEnabled(False)
        self.delete_entry_btn.setObjectName("dangerBtn")
        self.delete_entry_btn.clicked.connect(self._on_delete_entry)
        hist_actions.addWidget(self.record_btn)
        hist_actions.addStretch()
        hist_actions.addWidget(self.edit_entry_btn)
        hist_actions.addWidget(self.delete_entry_btn)
        hist_layout.addLayout(hist_actions)

        self.history_table = QTableWidget()
        self.history_table.setColumnCount(len(HISTORY_COLS))
        self.history_table.setHorizontalHeaderLabels(HISTORY_COLS)
        self.history_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.history_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.history_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.history_table.setAlternatingRowColors(True)
        self.history_table.verticalHeader().setVisible(False)
        self.history_table.horizontalHeader().setSectionResizeMode(
            len(HISTORY_COLS) - 1, QHeaderView.ResizeMode.Stretch
        )
        for col in range(len(HISTORY_COLS) - 1):
            self.history_table.horizontalHeader().setSectionResizeMode(
                col, QHeaderView.ResizeMode.ResizeToContents
            )
        self.history_table.itemSelectionChanged.connect(self._on_entry_selection_changed)
        self.history_table.doubleClicked.connect(self._on_edit_entry)
        hist_layout.addWidget(self.history_table, 1)
        d.addWidget(hist_box, 1)

        self.detail_stack.addWidget(detail)
        return self.detail_stack

    # -----------------------------------------------------------------------
    # Data
    # -----------------------------------------------------------------------
    def _on_data_changed(self, topic: str) -> None:
        if topic in self._topics:
            self._dirty = True

    def ensure_fresh(self) -> None:
        if self._dirty:
            self.refresh()

    def refresh(self) -> None:
        self._accounts = self.ctx.account_options_active()
        self._account_names = self.ctx.account_name_map()
        self._sources = self._service.list_active()
        self._refresh_tiles()
        self._refresh_kpis()
        self._refresh_detail()
        self._dirty = False

    def _refresh_tiles(self) -> None:
        # Tear down existing tiles
        for t in self._tiles:
            self.tile_layout.removeWidget(t)
            t.deleteLater()
        self._tiles = []
        while self.tile_layout.count():
            self.tile_layout.takeAt(0)

        for s in self._sources:
            bg, fg = INCOME_SOURCE_BADGE.get(s.source_type, FALLBACK_BADGE)
            tile = IncomeSourceTile(
                s,
                type_label=SOURCE_TYPE_LABELS.get(s.source_type, s.source_type),
                type_bg=bg,
                type_fg=fg,
                freq_label=FREQ_LABELS.get(s.frequency or "", s.frequency or "—"),
                account_name=self._account_names.get(s.deposit_account_id),
                net_text=fmt_inr(self._service.net_monthly(s), compact=True),
                month_status=self._month_status(s),
                selected=(s.id == self._selected_id),
                on_click=self._on_tile_clicked,
                on_activate=self._on_tile_activated,
                parent=self.tile_container,
            )
            self._tiles.append(tile)
            self.tile_layout.addWidget(tile)
        self.tile_layout.addStretch(1)

        self.empty_label.setVisible(not self._sources)
        self.scroll.setVisible(bool(self._sources))
        self._update_source_buttons()

    def _month_status(self, s: IncomeSource) -> str:
        """'logged' | 'pending' | 'na' for the current month."""
        if not self._service.is_recurring_monthly(s):
            return "na"
        period = date.today().strftime("%Y-%m")
        return "logged" if self._service.has_logged(s.id, period) else "pending"  # type: ignore[arg-type]

    def _refresh_kpis(self) -> None:
        total_gross = total_net = total_deduct = 0.0
        active_count = 0
        for s in self._sources:
            if not s.is_active:
                continue
            active_count += 1
            total_gross  += self._service.gross_monthly(s)
            total_deduct += self._service.deductions_monthly(s)
            total_net    += self._service.net_monthly(s)

        this_month = date.today().strftime("%Y-%m")
        received = self._service.total_received(this_month)

        self.kpi_gross.set_value(fmt_inr(total_gross, compact=True))
        self.kpi_net.set_value(fmt_inr(total_net, compact=True))
        self.kpi_deduct.set_value(fmt_inr(total_deduct, compact=True))
        self.kpi_received.set_value(fmt_inr(received, compact=True))
        self.kpi_sources.set_value(str(active_count))

    def _refresh_detail(self) -> None:
        source = self._selected_source()
        if source is None:
            self.detail_stack.setCurrentIndex(0)
            self.record_btn.setEnabled(False)
            return

        self.detail_stack.setCurrentIndex(1)
        self.record_btn.setEnabled(True)
        self.detail_title.setText(source.name)

        type_lbl = SOURCE_TYPE_LABELS.get(source.source_type, source.source_type)
        freq_lbl = FREQ_LABELS.get(source.frequency or "", source.frequency or "—")
        acct = self._account_names.get(source.deposit_account_id, "Not linked")
        period = date.today().strftime("%Y-%m")
        if not self._service.is_recurring_monthly(source):
            month_txt = "This month: n/a"
        elif self._service.has_logged(source.id, period):  # type: ignore[arg-type]
            month_txt = "This month: ✓ logged"
        else:
            month_txt = "This month: ⚠ pending"
        self.detail_subtitle.setText(
            f"{type_lbl}  ·  {freq_lbl}  ·  Deposits to: {acct}  ·  {month_txt}"
        )

        if source.source_type == "salary":
            self.breakdown_panel.load(source)
            self.breakdown_panel.setVisible(True)
        else:
            self.breakdown_panel.setVisible(False)

        self._refresh_history(source)

    def _refresh_history(self, source: IncomeSource) -> None:
        self._entries = self._service.list_entries(source.id)  # type: ignore[arg-type]
        self.history_table.blockSignals(True)
        self.history_table.setRowCount(0)
        for e in self._entries:
            row = self.history_table.rowCount()
            self.history_table.insertRow(row)

            month_item = QTableWidgetItem(e.period_month)
            month_item.setData(Qt.ItemDataRole.UserRole, e.id)
            self.history_table.setItem(row, 0, month_item)

            self.history_table.setItem(row, 1, _AmountItem(e.expected_amount or 0.0))
            self.history_table.setItem(row, 2, _AmountItem(e.actual_amount or 0.0))

            # Variance = actual - expected (blank when no expected snapshot)
            self.history_table.setItem(row, 3, _VarianceItem(e.expected_amount, e.actual_amount))

            acct = self._account_names.get(e.account_id, "—")
            self.history_table.setItem(row, 4, QTableWidgetItem(acct))

            posted = "✓" if e.transaction_id else "—"
            posted_item = QTableWidgetItem(posted)
            posted_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if e.transaction_id:
                posted_item.setForeground(QColor("#065f46"))
            self.history_table.setItem(row, 5, posted_item)

            self.history_table.setItem(row, 6, QTableWidgetItem(e.notes or ""))
        self.history_table.blockSignals(False)
        self._on_entry_selection_changed()

    # -----------------------------------------------------------------------
    # Selection helpers
    # -----------------------------------------------------------------------

    def _selected_source(self) -> Optional[IncomeSource]:
        if self._selected_id is None:
            return None
        return next((s for s in self._sources if s.id == self._selected_id), None)

    def _selected_entry(self) -> Optional[IncomeEntry]:
        rows = self.history_table.selectionModel().selectedRows()
        if not rows:
            return None
        item = self.history_table.item(rows[0].row(), 0)
        if item is None:
            return None
        eid = item.data(Qt.ItemDataRole.UserRole)
        return next((e for e in self._entries if e.id == eid), None)

    def _update_source_buttons(self) -> None:
        source = self._selected_source()
        has_sel = source is not None
        self.edit_btn.setEnabled(has_sel)
        self.delete_btn.setEnabled(has_sel)
        self.toggle_btn.setEnabled(has_sel)
        if source is not None:
            lbl = "Deactivate" if source.is_active else "Activate"
            icon = "⏸" if source.is_active else "▶"
            self.toggle_btn.setText(f"{icon}  {lbl}")

    def _on_tile_clicked(self, source: IncomeSource) -> None:
        self._selected_id = source.id
        for t in self._tiles:
            t.set_selected(t.source.id == source.id)
        self._update_source_buttons()
        self._refresh_detail()

    def _on_tile_activated(self, source: IncomeSource) -> None:
        """Double-click a tile → select and open the edit dialog."""
        self._on_tile_clicked(source)
        self._on_edit()

    def _on_entry_selection_changed(self) -> None:
        has = self._selected_entry() is not None
        self.edit_entry_btn.setEnabled(has)
        self.delete_entry_btn.setEnabled(has)

    # -----------------------------------------------------------------------
    # Source CRUD
    # -----------------------------------------------------------------------

    def _on_add(self) -> None:
        dlg = IncomeDialog(self, accounts=self._accounts)
        if dlg.exec() == IncomeDialog.DialogCode.Accepted:
            self._service.create(dlg.get_source())
            self.refresh()

    def _on_edit(self) -> None:
        source = self._selected_source()
        if source is None:
            return
        dlg = IncomeDialog(self, source, accounts=self._accounts)
        if dlg.exec() == IncomeDialog.DialogCode.Accepted:
            self._service.update(dlg.get_source())
            self.refresh()

    def _on_toggle_active(self) -> None:
        source = self._selected_source()
        if source is None:
            return
        self._service.toggle_active(source)
        self.refresh()

    def _on_delete(self) -> None:
        source = self._selected_source()
        if source is None:
            return
        ans = QMessageBox.question(
            self,
            "Delete Income Source",
            f"Delete «{source.name}»?\nIts monthly history will also be removed.\n"
            f"This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        )
        if ans == QMessageBox.StandardButton.Yes:
            self._service.delete(source.id)  # type: ignore[arg-type]
            self._selected_id = None
            self.refresh()

    # -----------------------------------------------------------------------
    # Monthly entry CRUD
    # -----------------------------------------------------------------------

    def _on_record(self) -> None:
        source = self._selected_source()
        if source is None:
            return
        expected = self._service.net_monthly(source)
        dlg = RecordIncomeDialog(source, self._accounts, expected_net=expected, parent=self)
        if dlg.exec() != RecordIncomeDialog.DialogCode.Accepted:
            return
        try:
            self._service.record_month(source, **dlg.get_values())
        except ValueError as exc:
            QMessageBox.warning(self, "Could not record", str(exc))
            return
        self.refresh()

    def _on_edit_entry(self) -> None:
        source = self._selected_source()
        entry = self._selected_entry()
        if source is None or entry is None:
            return
        expected = self._service.net_monthly(source)
        dlg = RecordIncomeDialog(
            source, self._accounts, expected_net=expected, entry=entry, parent=self
        )
        if dlg.exec() != RecordIncomeDialog.DialogCode.Accepted:
            return
        values = dlg.get_values()
        try:
            # If the month was changed, drop the old entry (and its ledger
            # effect) before recording under the new period.
            if values["period_month"] != entry.period_month:
                self._service.delete_entry(entry.id)  # type: ignore[arg-type]
            self._service.record_month(source, **values)
        except ValueError as exc:
            QMessageBox.warning(self, "Could not save", str(exc))
            return
        self.refresh()

    def _on_delete_entry(self) -> None:
        entry = self._selected_entry()
        if entry is None:
            return
        ans = QMessageBox.question(
            self,
            "Delete Income Entry",
            f"Delete the {entry.period_month} entry?\n"
            f"Any linked ledger transaction and its balance effect will be reversed.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        )
        if ans == QMessageBox.StandardButton.Yes:
            self._service.delete_entry(entry.id)  # type: ignore[arg-type]
            self.refresh()


# ── custom table items ──────────────────────────────────────────────────────

class _BadgeItem(QTableWidgetItem):
    def __init__(self, text: str, bg: str, fg: str) -> None:
        super().__init__(f"  {text}  ")
        self.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setBackground(QColor(bg))
        self.setForeground(QColor(fg))
        f = self.font()
        f.setBold(True)
        self.setFont(f)


class _AmountItem(QTableWidgetItem):
    def __init__(self, value: float, negative: bool = False) -> None:
        super().__init__(fmt_inr(value, compact=True) if value else "—")
        self.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        if negative and value > 0:
            self.setForeground(QColor("#dc2626"))


class _VarianceItem(QTableWidgetItem):
    """Actual − expected, coloured green (surplus) / red (shortfall)."""

    def __init__(self, expected, actual) -> None:
        if not expected:
            super().__init__("—")
            self.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.setForeground(QColor("#9ca3af"))
            return
        delta = (actual or 0.0) - expected
        sign = "+" if delta >= 0 else "−"
        super().__init__(f"{sign}{fmt_inr(abs(delta), compact=True)}")
        self.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.setForeground(QColor("#065f46") if delta >= 0 else QColor("#dc2626"))


# ── salary breakdown panel ──────────────────────────────────────────────────

class _SalaryBreakdownPanel(QFrame):
    """Shows a salary-type income source's component breakdown."""

    def __init__(self) -> None:
        super().__init__()
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setObjectName("breakdownPanel")

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(10)

        header = QLabel("Salary Breakdown")
        header.setObjectName("sectionLabel")
        f = header.font()
        f.setBold(True)
        f.setPointSize(f.pointSize() + 1)
        header.setFont(f)
        root.addWidget(header)

        earn_box = QGroupBox("Earnings")
        earn_grid = QGridLayout(earn_box)
        self._earn_labels: dict[str, QLabel] = {}
        for i, key in enumerate(["Basic", "HRA", "Special Allow"]):
            lbl = QLabel(key)
            lbl.setObjectName("kpiTitle")
            val = QLabel("—")
            val.setObjectName("kpiValue")
            earn_grid.addWidget(lbl, 0, i)
            earn_grid.addWidget(val, 1, i)
            self._earn_labels[key] = val
        root.addWidget(earn_box)

        ded_box = QGroupBox("Deductions")
        ded_grid = QGridLayout(ded_box)
        self._ded_labels: dict[str, QLabel] = {}
        for i, key in enumerate(["PF (Employee)", "PF (Employer)", "Prof. Tax", "TDS"]):
            lbl = QLabel(key)
            lbl.setObjectName("kpiTitle")
            val = QLabel("—")
            val.setObjectName("kpiValue")
            val.setStyleSheet("color: #dc2626;")
            ded_grid.addWidget(lbl, 0, i)
            ded_grid.addWidget(val, 1, i)
            self._ded_labels[key] = val
        root.addWidget(ded_box)

        net_row = QHBoxLayout()
        net_title = QLabel("Net Take-Home / Month:")
        net_title.setObjectName("kpiTitle")
        f2 = net_title.font()
        f2.setBold(True)
        net_title.setFont(f2)
        self._net_val = QLabel("—")
        self._net_val.setObjectName("kpiValue")
        f3 = self._net_val.font()
        f3.setBold(True)
        f3.setPointSize(f3.pointSize() + 2)
        self._net_val.setFont(f3)
        self._net_val.setStyleSheet("color: #065f46;")
        net_row.addWidget(net_title)
        net_row.addWidget(self._net_val)
        net_row.addStretch()
        root.addLayout(net_row)

    def load(self, s: IncomeSource) -> None:
        def _f(v: Optional[float]) -> str:
            return fmt_inr(v) if v else "—"

        self._earn_labels["Basic"].setText(_f(s.basic))
        self._earn_labels["HRA"].setText(_f(s.hra))
        self._earn_labels["Special Allow"].setText(_f(s.special_allow))

        self._ded_labels["PF (Employee)"].setText(_f(s.pf_employee))
        self._ded_labels["PF (Employer)"].setText(_f(s.pf_employer))
        self._ded_labels["Prof. Tax"].setText(_f(s.professional_tax))
        self._ded_labels["TDS"].setText(_f(s.tds))

        net = IncomeService.net_monthly(s)  # static calculator on detail sub-panel
        self._net_val.setText(fmt_inr(net))
