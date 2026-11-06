"""Investments tab - holdings list, KPIs, type-specific detail panel, allocation."""
from __future__ import annotations

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
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from config.constants import ASSET_BUCKETS, HoldingType
from models.holding import Holding
from services.app_context import AppContext
from ui.theme.badges import FALLBACK_BADGE, HOLDING_TYPE_BADGE
from ui.dialogs.holding_dialog import HoldingDialog
from ui.widgets.holding_tile import HoldingTile
from ui.widgets.kpi_card import KpiCard
from utils.formatters import fmt_inr, fmt_pct, fmt_date


# --------------------------------------------------------------------------
# Constants
# --------------------------------------------------------------------------

HOLDING_LABELS: dict[str, str] = {
    HoldingType.STOCK.value:          "Stock",
    HoldingType.ETF.value:            "ETF",
    HoldingType.SIP.value:            "SIP",
    HoldingType.MUTUAL_FUND.value:    "Mutual Fund",
    HoldingType.FD.value:             "Fixed Deposit",
    HoldingType.PPF.value:            "PPF",
    HoldingType.EPF.value:            "EPF",
    HoldingType.NPS.value:            "NPS",
    HoldingType.BOND.value:           "Bond",
    HoldingType.GOLD_COIN.value:      "Gold Coin",
    HoldingType.GOLD_JEWELRY.value:   "Gold Jewellery",
    HoldingType.TERM_INSURANCE.value: "Term Insurance",
    HoldingType.CRYPTO.value:         "Crypto",
    HoldingType.REAL_ESTATE.value:    "Real Estate",
}

BUCKET_LABELS: dict[str, str] = {
    "all":       "All",
    "equity":    "Equity",
    "debt":      "Debt",
    "gold":      "Gold",
    "alt":       "Alternatives",
    "insurance": "Insurance",
}

BUCKET_ORDER = ["all", "equity", "debt", "gold", "alt", "insurance"]

BUCKET_TYPES: dict[str, set[str]] = {"all": set(HOLDING_LABELS.keys())}
for _bkt, _types in ASSET_BUCKETS.items():
    BUCKET_TYPES[_bkt] = {t.value for t in _types}

_STOCK_TYPES = {HoldingType.STOCK.value, HoldingType.ETF.value, HoldingType.CRYPTO.value}
_MF_TYPES    = {HoldingType.SIP.value, HoldingType.MUTUAL_FUND.value}
_FD_TYPES    = {HoldingType.FD.value, HoldingType.BOND.value,
                HoldingType.PPF.value, HoldingType.EPF.value, HoldingType.NPS.value}
_GOLD_TYPES  = {HoldingType.GOLD_COIN.value, HoldingType.GOLD_JEWELRY.value}
_INS_TYPES   = {HoldingType.TERM_INSURANCE.value}

ALLOC_COLOURS: dict[str, str] = {
    "equity":    "#3b82f6",
    "debt":      "#f59e0b",
    "gold":      "#eab308",
    "alt":       "#8b5cf6",
    "insurance": "#ec4899",
    "other":     "#9ca3af",
}


# --------------------------------------------------------------------------
# Main view
# --------------------------------------------------------------------------

class InvestmentsView(QWidget):
    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self.ctx = ctx
        self._topics = {"holdings", "accounts"}
        self._dirty = True
        self._svc = ctx.investment_service
        self._holdings: list[Holding] = []
        self._tiles: list[HoldingTile] = []
        self._accounts: list[tuple] = []
        self._account_names: dict[int, str] = {}
        self._active_bucket = "all"
        self._selected_id: Optional[int] = None

        self.ctx.events.changed.connect(self._on_data_changed)
        self._build()
        self.refresh()

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(14)

        # Header
        hdr = QHBoxLayout()
        title = QLabel("Investments")
        title.setObjectName("pageTitle")
        hdr.addWidget(title)
        hdr.addStretch()
        self.add_btn = QPushButton("  Add Holding")
        self.add_btn.setObjectName("primaryBtn")
        self.add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.add_btn.clicked.connect(self._on_add)
        hdr.addWidget(self.add_btn)
        root.addLayout(hdr)

        # KPI row
        kpi_grid = QGridLayout()
        kpi_grid.setSpacing(12)
        self.kpi_invested = KpiCard("Total Invested",  "")
        self.kpi_value    = KpiCard("Portfolio Value", "")
        self.kpi_pnl      = KpiCard("Unrealized P&L",  "")
        self.kpi_return   = KpiCard("Overall Return",  "")
        self.kpi_count    = KpiCard("Holdings",        "")
        for i, w in enumerate([self.kpi_invested, self.kpi_value,
                                self.kpi_pnl, self.kpi_return, self.kpi_count]):
            kpi_grid.addWidget(w, 0, i)
        root.addLayout(kpi_grid)

        # Allocation bar
        self.alloc_bar = _AllocationBar()
        root.addWidget(self.alloc_bar)

        # Filter pills
        pill_row = QHBoxLayout()
        pill_row.setSpacing(6)
        self._pills: dict[str, QPushButton] = {}
        for key in BUCKET_ORDER:
            btn = QPushButton(BUCKET_LABELS[key])
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setProperty("filterPill", True)
            btn.clicked.connect(lambda _checked, k=key: self._on_filter(k))
            pill_row.addWidget(btn)
            self._pills[key] = btn
        self._pills["all"].setChecked(True)
        pill_row.addStretch()
        root.addLayout(pill_row)

        # Splitter: tile list (left) | detail panel (right)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        # Scrollable list of holding tiles
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

        self.empty_label = QLabel('No holdings here. Click "Add Holding" to create one.')
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

        # Right: placeholder until a holding is selected, then the detail panel
        self.detail_stack = QStackedWidget()
        placeholder = QLabel("Select a holding to see its details.")
        placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        placeholder.setObjectName("tileFlags")
        placeholder.setWordWrap(True)
        self.detail_stack.addWidget(placeholder)
        self.detail = _HoldingDetailPanel()
        self.detail_stack.addWidget(self.detail)
        splitter.addWidget(self.detail_stack)

        splitter.setSizes([520, 520])
        root.addWidget(splitter, 1)

    # ------------------------------------------------------------------
    # Data
    # ------------------------------------------------------------------

    def _on_data_changed(self, topic: str) -> None:
        if topic in self._topics:
            self._dirty = True

    def ensure_fresh(self) -> None:
        if self._dirty:
            self.refresh()

    def refresh(self) -> None:
        self._accounts = self.ctx.account_options_active()
        self._account_names = self.ctx.account_name_map()
        self._holdings = self._svc.list_active()
        self._refresh_tiles()
        self._refresh_kpis()
        self.alloc_bar.load(self._svc.asset_allocation())
        self._dirty = False

    def _visible(self) -> list[Holding]:
        if self._active_bucket == "all":
            return self._holdings
        allowed = BUCKET_TYPES.get(self._active_bucket, set())
        return [h for h in self._holdings if h.holding_type in allowed]

    def _refresh_tiles(self) -> None:
        # Tear down existing tiles
        for t in self._tiles:
            self.tile_layout.removeWidget(t)
            t.deleteLater()
        self._tiles = []
        while self.tile_layout.count():
            self.tile_layout.takeAt(0)

        visible = self._visible()
        for h in visible:
            bg, fg = HOLDING_TYPE_BADGE.get(h.holding_type, FALLBACK_BADGE)
            ret = h.return_pct
            tile = HoldingTile(
                h,
                type_label=HOLDING_LABELS.get(h.holding_type, h.holding_type),
                type_bg=bg,
                type_fg=fg,
                institution=h.institution,
                value_text=fmt_inr(h.current_value, compact=True),
                return_text=("+" if ret >= 0 else "") + fmt_pct(ret),
                positive=ret >= 0,
                selected=(h.id == self._selected_id),
                on_click=self._on_tile_clicked,
                on_activate=self._on_tile_activated,
                parent=self.tile_container,
            )
            self._tiles.append(tile)
            self.tile_layout.addWidget(tile)
        self.tile_layout.addStretch(1)

        self.empty_label.setVisible(not visible)
        self.scroll.setVisible(bool(visible))
        self._update_buttons()

        # Keep the right-hand detail in sync with the current selection
        sel = self._selected_holding()
        if sel is not None and any(t.holding.id == sel.id for t in self._tiles):
            self.detail.load(sel, self._account_names.get(sel.linked_account_id))
            self.detail_stack.setCurrentIndex(1)
        else:
            self.detail_stack.setCurrentIndex(0)

    def _refresh_kpis(self) -> None:
        hs = self._holdings
        invested = sum(h.invested_amount for h in hs)
        value    = sum(h.current_value   for h in hs)
        pnl      = value - invested
        ret      = (pnl / invested * 100) if invested > 0 else 0.0

        self.kpi_invested.set_value(fmt_inr(invested, compact=True))
        self.kpi_value.set_value(fmt_inr(value, compact=True))
        sign = "+" if pnl >= 0 else ""
        self.kpi_pnl.set_value(sign + fmt_inr(abs(pnl), compact=True))
        self.kpi_return.set_value(("+" if ret >= 0 else "") + fmt_pct(ret))
        self.kpi_count.set_value(str(len(hs)))

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_filter(self, bucket: str) -> None:
        self._active_bucket = bucket
        for k, btn in self._pills.items():
            btn.setChecked(k == bucket)
        self._selected_id = None
        self.detail_stack.setCurrentIndex(0)
        self._refresh_tiles()

    def _update_buttons(self) -> None:
        h = self._selected_holding()
        has_sel = h is not None
        self.edit_btn.setEnabled(has_sel)
        self.delete_btn.setEnabled(has_sel)
        self.toggle_btn.setEnabled(has_sel)
        if h is not None:
            self.toggle_btn.setText("Deactivate" if h.is_active else "Activate")

    def _on_tile_clicked(self, holding: Holding) -> None:
        self._selected_id = holding.id
        for t in self._tiles:
            t.set_selected(t.holding.id == holding.id)
        self._update_buttons()
        self.detail.load(holding, self._account_names.get(holding.linked_account_id))
        self.detail_stack.setCurrentIndex(1)

    def _on_tile_activated(self, holding: Holding) -> None:
        """Double-click a tile → select and open the edit dialog."""
        self._on_tile_clicked(holding)
        self._on_edit()

    def _selected_holding(self) -> Optional[Holding]:
        if self._selected_id is None:
            return None
        return next((h for h in self._holdings if h.id == self._selected_id), None)

    def _on_add(self) -> None:
        dlg = HoldingDialog(self, accounts=self._accounts)
        if dlg.exec() == HoldingDialog.DialogCode.Accepted:
            self._svc.add_holding(dlg.get_holding())
            self.refresh()

    def _on_edit(self) -> None:
        h = self._selected_holding()
        if h is None:
            return
        dlg = HoldingDialog(self, h, accounts=self._accounts)
        if dlg.exec() == HoldingDialog.DialogCode.Accepted:
            self._svc.update_holding(dlg.get_holding())
            self.refresh()

    def _on_toggle(self) -> None:
        h = self._selected_holding()
        if h is None:
            return
        self._svc.toggle_active(h)
        self.refresh()

    def _on_delete(self) -> None:
        h = self._selected_holding()
        if h is None:
            return
        ans = QMessageBox.question(
            self,
            "Delete Holding",
            f"Delete '{h.name}'?\nThis cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        )
        if ans == QMessageBox.StandardButton.Yes:
            self._svc.delete_holding(h.id)  # type: ignore[arg-type]
            self._selected_id = None
            self.refresh()


# --------------------------------------------------------------------------
# Allocation bar
# --------------------------------------------------------------------------

class _AllocationBar(QFrame):
    """Proportional horizontal bar + legend for asset allocation."""

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("allocBar")
        self.setFixedHeight(52)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 4)
        layout.setSpacing(4)

        self._bar_row = QHBoxLayout()
        self._bar_row.setSpacing(2)
        layout.addLayout(self._bar_row)

        self._legend_row = QHBoxLayout()
        self._legend_row.setSpacing(16)
        layout.addLayout(self._legend_row)

    def load(self, allocation: dict[str, float]) -> None:
        for layout in (self._bar_row, self._legend_row):
            while layout.count():
                item = layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()

        total = sum(allocation.values()) or 1.0
        for bucket, value in allocation.items():
            if value <= 0:
                continue
            pct = value / total
            colour = ALLOC_COLOURS.get(bucket, "#9ca3af")

            seg = QFrame()
            seg.setFixedHeight(10)
            seg.setStyleSheet(
                f"background: {colour}; border-radius: 3px;")
            seg.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            self._bar_row.addWidget(seg, max(1, int(pct * 100)))

            label_text = (
                BUCKET_LABELS.get(bucket, bucket).title()
                + f"  {pct * 100:.0f}%"
            )
            dot = QLabel(label_text)
            dot.setStyleSheet(
                f"color: {colour}; font-size: 11px; font-weight: bold;")
            self._legend_row.addWidget(dot)

        self._legend_row.addStretch()


# --------------------------------------------------------------------------
# Detail panel
# --------------------------------------------------------------------------

class _HoldingDetailPanel(QFrame):
    """Shows type-specific fields for the selected holding."""

    def __init__(self) -> None:
        super().__init__()
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setObjectName("breakdownPanel")

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(8)

        self._header = QLabel("Details")
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

    def load(self, h: Holding, account_name: Optional[str] = None) -> None:
        # Clear
        while self._grid.count():
            item = self._grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        type_label = HOLDING_LABELS.get(h.holding_type, h.holding_type)
        self._header.setText(f"{h.name}  -  {type_label}")
        self._account_name = account_name

        fields: list[tuple[str, str, str]] = []  # (label, value, colour)
        GREEN = "#16a34a"
        RED   = "#dc2626"

        def _add(label: str, value: str, colour: str = "") -> None:
            fields.append((label, value, colour))

        # Universal
        if h.purchase_date:
            _add("Bought",        fmt_date(h.purchase_date))
        if h.institution:
            _add("Institution",   h.institution)
        if h.folio_or_account:
            _add("Folio / Acct",  h.folio_or_account)
        if account_name:
            _add("Linked Account", account_name)
        _add("Invested",      fmt_inr(h.invested_amount))
        _add("Current Value", fmt_inr(h.current_value))
        pnl = h.unrealized_pnl
        sign = "+" if pnl >= 0 else ""
        _add("Unrealized P&L", sign + fmt_inr(abs(pnl)), GREEN if pnl >= 0 else RED)
        ret = h.return_pct
        _add("Return", ("+" if ret >= 0 else "") + fmt_pct(ret),
             GREEN if ret >= 0 else RED)

        # Stock / ETF / Crypto
        if h.holding_type in _STOCK_TYPES:
            if h.symbol:
                _add("Symbol",   f"{h.symbol} ({h.exchange or ''})")
            if h.quantity:
                _add("Qty",      f"{h.quantity:,.0f}")
            if h.avg_price:
                _add("Avg Price", fmt_inr(h.avg_price))
            if h.current_price:
                _add("CMP",      fmt_inr(h.current_price))
            if h.market_cap:
                _add("Cap",      h.market_cap.replace("_", " ").title())
            if h.sector:
                _add("Sector",   h.sector)

        # SIP / MF
        elif h.holding_type in _MF_TYPES:
            if h.quantity:
                _add("Units",    f"{h.quantity:,.4f}")
            if h.current_price:
                _add("NAV",      fmt_inr(h.current_price))
            if h.sip_amount:
                _add("SIP / mo", fmt_inr(h.sip_amount))
            if h.sip_day_of_month:
                _add("SIP Day",  f"{h.sip_day_of_month}th")

        # FD / Bond / PPF / EPF / NPS
        elif h.holding_type in _FD_TYPES:
            if h.interest_rate:
                _add("Rate",     fmt_pct(h.interest_rate))
            if h.maturity_date:
                _add("Matures",  fmt_date(h.maturity_date))
            if h.payout_frequency:
                _add("Payout",   h.payout_frequency.replace("_", " ").title())
            _add("Auto-Renew",   "Yes" if h.auto_renew else "No")

        # Gold
        elif h.holding_type in _GOLD_TYPES:
            if h.weight_grams:
                _add("Weight",   f"{h.weight_grams:.3f} g")
            if h.purity:
                _add("Purity",   h.purity)
            if h.making_charges:
                _add("Making",   fmt_inr(h.making_charges))

        # Insurance
        elif h.holding_type in _INS_TYPES:
            if h.sum_assured:
                _add("Sum Assured",   fmt_inr(h.sum_assured))
            if h.premium_amount:
                _add("Annual Premium", fmt_inr(h.premium_amount))
            if h.premium_due_date:
                _add("Next Due",      fmt_date(h.premium_due_date))
            if h.policy_term_years:
                _add("Term",          f"{h.policy_term_years} yrs")

        if h.notes:
            _add("Notes", h.notes)

        COLS = 4
        for i, (label, value, colour) in enumerate(fields):
            row, col = divmod(i, COLS)
            lbl = QLabel(label)
            lbl.setObjectName("kpiTitle")
            val = QLabel(value)
            val.setObjectName("kpiValue")
            vf = val.font()
            vf.setBold(True)
            val.setFont(vf)
            if colour:
                val.setStyleSheet(f"color: {colour};")
            self._grid.addWidget(lbl, row * 2,     col)
            self._grid.addWidget(val, row * 2 + 1, col)
