"""Liabilities tab - loan/credit list, KPIs, repayment detail panel, CRUD."""
from __future__ import annotations

from datetime import date
from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from config.constants import LiabilityType
from models.liability import Liability
from services.app_context import AppContext
from ui.theme.badges import FALLBACK_BADGE, LIABILITY_TYPE_BADGE
from ui.dialogs.liability_dialog import LiabilityDialog
from ui.widgets.liability_tile import LiabilityTile
from ui.widgets.kpi_card import KpiCard
from utils.calculators import emi as calc_emi
from utils.formatters import fmt_inr, fmt_pct, fmt_date


LIABILITY_LABELS = {
    LiabilityType.HOME_LOAN.value:      "Home Loan",
    LiabilityType.CAR_LOAN.value:       "Car Loan",
    LiabilityType.PERSONAL_LOAN.value:  "Personal Loan",
    LiabilityType.EDUCATION_LOAN.value: "Education Loan",
    LiabilityType.CREDIT_CARD.value:    "Credit Card",
    LiabilityType.BNPL.value:           "BNPL",
}

_EMI_TYPES = {
    LiabilityType.HOME_LOAN.value,
    LiabilityType.CAR_LOAN.value,
    LiabilityType.PERSONAL_LOAN.value,
    LiabilityType.EDUCATION_LOAN.value,
}


def _months_label(months: Optional[int]) -> str:
    if not months:
        return ""
    y, m = divmod(months, 12)
    parts = []
    if y:
        parts.append(f"{y}y")
    if m:
        parts.append(f"{m}m")
    return " ".join(parts)


def _is_overdue(due: Optional[str]) -> bool:
    if not due:
        return False
    try:
        return date.fromisoformat(due) < date.today()
    except ValueError:
        return False


class LiabilitiesView(QWidget):
    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self.ctx = ctx
        self._topics = {"liabilities", "accounts"}
        self._dirty = True
        self._svc = ctx.liability_service
        self._liabilities: list[Liability] = []
        self._tiles: list[LiabilityTile] = []
        self._accounts: list[tuple] = []
        self._account_names: dict[int, str] = {}
        self._selected_id: Optional[int] = None
        self.ctx.events.changed.connect(self._on_data_changed)
        self._build()
        self.refresh()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(14)

        hdr = QHBoxLayout()
        title = QLabel("Liabilities")
        title.setObjectName("pageTitle")
        hdr.addWidget(title)
        hdr.addStretch()
        self.add_btn = QPushButton("Add Liability")
        self.add_btn.setObjectName("primaryBtn")
        self.add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.add_btn.clicked.connect(self._on_add)
        hdr.addWidget(self.add_btn)
        root.addLayout(hdr)

        kpi_row = QGridLayout()
        kpi_row.setSpacing(12)
        self.kpi_outstanding = KpiCard("Total Outstanding",  "")
        self.kpi_emi         = KpiCard("Monthly EMI Outflow","")
        self.kpi_avg_rate    = KpiCard("Weighted Avg Rate",  "")
        self.kpi_count       = KpiCard("Active Liabilities", "")
        for i, w in enumerate([self.kpi_outstanding, self.kpi_emi,
                                self.kpi_avg_rate, self.kpi_count]):
            kpi_row.addWidget(w, 0, i)
        root.addLayout(kpi_row)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        # Scrollable list of liability tiles
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
        self.scroll.setMinimumHeight(180)

        self.empty_label = QLabel('No liabilities yet. Click "Add Liability" to create one.')
        self.empty_label.setObjectName("tileFlags")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setWordWrap(True)
        self.empty_label.hide()

        action_bar = QHBoxLayout()
        self.edit_btn   = QPushButton("Edit")
        self.edit_btn.setEnabled(False)
        self.edit_btn.clicked.connect(self._on_edit)
        self.toggle_btn = QPushButton("Deactivate")
        self.toggle_btn.setEnabled(False)
        self.toggle_btn.clicked.connect(self._on_toggle)
        self.delete_btn = QPushButton("Delete")
        self.delete_btn.setEnabled(False)
        self.delete_btn.setObjectName("dangerBtn")
        self.delete_btn.clicked.connect(self._on_delete)
        action_bar.addWidget(self.edit_btn)
        action_bar.addWidget(self.toggle_btn)
        action_bar.addWidget(self.delete_btn)
        action_bar.addStretch()

        list_pane = QWidget()
        tp = QVBoxLayout(list_pane)
        tp.setContentsMargins(0, 0, 0, 0)
        tp.setSpacing(6)
        tp.addWidget(self.scroll, 1)
        tp.addWidget(self.empty_label)
        tp.addLayout(action_bar)
        splitter.addWidget(list_pane)

        # Right: placeholder until a liability is selected, then the detail panel
        self.detail_stack = QStackedWidget()
        placeholder = QLabel("Select a liability to see its details.")
        placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        placeholder.setObjectName("tileFlags")
        placeholder.setWordWrap(True)
        self.detail_stack.addWidget(placeholder)
        self.detail = _LiabilityDetailPanel()
        self.detail_stack.addWidget(self.detail)
        splitter.addWidget(self.detail_stack)

        splitter.setSizes([520, 520])
        root.addWidget(splitter, 1)

    def _on_data_changed(self, topic: str) -> None:
        if topic in self._topics:
            self._dirty = True

    def ensure_fresh(self) -> None:
        if self._dirty:
            self.refresh()

    def refresh(self) -> None:
        self._accounts = self.ctx.account_options_active()
        self._account_names = self.ctx.account_name_map()
        self._liabilities = self._svc.list_active()
        self._refresh_tiles()
        self._refresh_kpis()
        self._dirty = False

    def _chip_for(self, lb: Liability) -> tuple[str, bool]:
        """(chip_text, is_danger) — flags overdue, else shows the rate."""
        if _is_overdue(lb.next_due_date):
            return "Overdue", True
        if lb.interest_rate:
            return f"{fmt_pct(lb.interest_rate)} p.a.", False
        return "", False

    def _refresh_tiles(self) -> None:
        for t in self._tiles:
            self.tile_layout.removeWidget(t)
            t.deleteLater()
        self._tiles = []
        while self.tile_layout.count():
            self.tile_layout.takeAt(0)

        for lb in self._liabilities:
            bg, fg = LIABILITY_TYPE_BADGE.get(lb.liability_type, FALLBACK_BADGE)
            chip_text, chip_danger = self._chip_for(lb)
            tile = LiabilityTile(
                lb,
                type_label=LIABILITY_LABELS.get(lb.liability_type, lb.liability_type),
                type_bg=bg,
                type_fg=fg,
                lender=lb.lender,
                outstanding_text=fmt_inr(lb.outstanding, compact=True),
                chip_text=chip_text,
                chip_danger=chip_danger,
                selected=(lb.id == self._selected_id),
                on_click=self._on_tile_clicked,
                on_activate=self._on_tile_activated,
                parent=self.tile_container,
            )
            self._tiles.append(tile)
            self.tile_layout.addWidget(tile)
        self.tile_layout.addStretch(1)

        self.empty_label.setVisible(not self._liabilities)
        self.scroll.setVisible(bool(self._liabilities))
        self._update_buttons()

        sel = self._selected_liability()
        if sel is not None and any(t.liability.id == sel.id for t in self._tiles):
            self.detail.load(sel, self._account_names.get(sel.account_id))
            self.detail_stack.setCurrentIndex(1)
        else:
            self.detail_stack.setCurrentIndex(0)

    def _refresh_kpis(self) -> None:
        total_out = sum(lb.outstanding for lb in self._liabilities)
        total_emi = 0.0
        weighted_rate_sum = 0.0
        for lb in self._liabilities:
            emi_val = lb.emi_amount or (
                calc_emi(lb.outstanding, (lb.interest_rate or 0) / 100,
                         lb.remaining_months)
                if lb.remaining_months and lb.interest_rate else 0
            )
            total_emi += emi_val
            weighted_rate_sum += (lb.interest_rate or 0) * lb.outstanding
        avg_rate = (weighted_rate_sum / total_out) if total_out > 0 else 0.0
        self.kpi_outstanding.set_value(fmt_inr(total_out, compact=True))
        self.kpi_emi.set_value(fmt_inr(total_emi, compact=True))
        self.kpi_avg_rate.set_value(fmt_pct(avg_rate))
        self.kpi_count.set_value(str(len(self._liabilities)))

    def _update_buttons(self) -> None:
        lb = self._selected_liability()
        has_sel = lb is not None
        self.edit_btn.setEnabled(has_sel)
        self.delete_btn.setEnabled(has_sel)
        self.toggle_btn.setEnabled(has_sel)
        if lb is not None:
            self.toggle_btn.setText("Deactivate" if lb.is_active else "Activate")

    def _on_tile_clicked(self, lb: Liability) -> None:
        self._selected_id = lb.id
        for t in self._tiles:
            t.set_selected(t.liability.id == lb.id)
        self._update_buttons()
        self.detail.load(lb, self._account_names.get(lb.account_id))
        self.detail_stack.setCurrentIndex(1)

    def _on_tile_activated(self, lb: Liability) -> None:
        self._on_tile_clicked(lb)
        self._on_edit()

    def _selected_liability(self) -> Optional[Liability]:
        if self._selected_id is None:
            return None
        return next((lb for lb in self._liabilities if lb.id == self._selected_id), None)

    def _on_add(self) -> None:
        dlg = LiabilityDialog(self, accounts=self._accounts)
        if dlg.exec() == LiabilityDialog.DialogCode.Accepted:
            self._svc.create(dlg.get_liability())
            self.refresh()

    def _on_edit(self) -> None:
        lb = self._selected_liability()
        if lb is None:
            return
        dlg = LiabilityDialog(self, lb, accounts=self._accounts)
        if dlg.exec() == LiabilityDialog.DialogCode.Accepted:
            self._svc.update(dlg.get_liability())
            self.refresh()

    def _on_toggle(self) -> None:
        lb = self._selected_liability()
        if lb is None:
            return
        self._svc.toggle_active(lb)
        self.refresh()

    def _on_delete(self) -> None:
        lb = self._selected_liability()
        if lb is None:
            return
        ans = QMessageBox.question(
            self, "Delete Liability",
            f"Delete '{lb.name}'?\nThis cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        )
        if ans == QMessageBox.StandardButton.Yes:
            self._svc.delete(lb.id)
            self._selected_id = None
            self.refresh()


class _LiabilityDetailPanel(QFrame):
    def __init__(self) -> None:
        super().__init__()
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setObjectName("breakdownPanel")
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(8)

        self._header = QLabel("")
        self._header.setObjectName("sectionLabel")
        f = self._header.font()
        f.setBold(True)
        f.setPointSize(f.pointSize() + 1)
        self._header.setFont(f)
        root.addWidget(self._header)

        self._grid_widget = QWidget()
        self._grid = QGridLayout(self._grid_widget)
        self._grid.setHorizontalSpacing(32)
        self._grid.setVerticalSpacing(4)
        root.addWidget(self._grid_widget)
        root.addStretch()

    def load(self, lb: Liability, account_name: Optional[str] = None) -> None:
        while self._grid.count():
            item = self._grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        type_label = LIABILITY_LABELS.get(lb.liability_type, lb.liability_type)
        self._header.setText(f"{lb.name}  -  {type_label}")

        fields = []

        def _add(label, value, colour=""):
            fields.append((label, value, colour))

        if lb.lender:
            _add("Lender", lb.lender)
        if account_name:
            _add("Paid From", account_name)
        _add("Outstanding", fmt_inr(lb.outstanding), "#dc2626")
        if lb.principal:
            paid = lb.principal - lb.outstanding
            _add("Original Principal", fmt_inr(lb.principal))
            _add("Paid So Far",        fmt_inr(paid), "#16a34a")
            pct = (paid / lb.principal * 100) if lb.principal else 0
            _add("% Repaid",           f"{pct:.1f}%", "#16a34a")
        if lb.interest_rate:
            _add("Interest Rate", fmt_pct(lb.interest_rate))

        emi_val = lb.emi_amount
        if not emi_val and lb.remaining_months and lb.interest_rate:
            emi_val = calc_emi(
                lb.outstanding, lb.interest_rate / 100, lb.remaining_months)
        if emi_val:
            _add("EMI / Month", fmt_inr(emi_val))

        if lb.tenure_months:
            _add("Total Tenure", _months_label(lb.tenure_months))
        if lb.remaining_months:
            _add("Remaining", _months_label(lb.remaining_months))
            if emi_val and lb.remaining_months:
                total_pay = emi_val * lb.remaining_months
                interest_cost = total_pay - lb.outstanding
                _add("Interest Cost Left",
                     fmt_inr(max(0, interest_cost)), "#f59e0b")

        if lb.start_date:
            _add("Start Date", fmt_date(lb.start_date))
        if lb.next_due_date:
            colour = "#dc2626" if _is_overdue(lb.next_due_date) else ""
            _add("Next Due", fmt_date(lb.next_due_date), colour)

        if lb.notes:
            _add("Notes", lb.notes)

        COLS = 4
        for i, (label, value, colour) in enumerate(fields):
            r, col = divmod(i, COLS)
            lbl = QLabel(label)
            lbl.setObjectName("kpiTitle")
            val = QLabel(value)
            val.setObjectName("kpiValue")
            vf = val.font()
            vf.setBold(True)
            val.setFont(vf)
            if colour:
                val.setStyleSheet(f"color: {colour};")
            self._grid.addWidget(lbl, r * 2,     col)
            self._grid.addWidget(val, r * 2 + 1, col)
