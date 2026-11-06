"""Add / Edit Holding dialog — dynamic sections per holding type."""
from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QScrollArea,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from PyQt6.QtCore import QDate

from models.holding import Holding
from config.constants import HoldingType
from ui.widgets.common import style_button_box


# ── option lists ────────────────────────────────────────────────────────────

HOLDING_TYPES: list[tuple[str, str]] = [
    (HoldingType.STOCK.value,          "Stock"),
    (HoldingType.ETF.value,            "ETF"),
    (HoldingType.SIP.value,            "SIP"),
    (HoldingType.MUTUAL_FUND.value,    "Mutual Fund"),
    (HoldingType.FD.value,             "Fixed Deposit"),
    (HoldingType.PPF.value,            "PPF"),
    (HoldingType.EPF.value,            "EPF"),
    (HoldingType.NPS.value,            "NPS"),
    (HoldingType.BOND.value,           "Bond"),
    (HoldingType.GOLD_COIN.value,      "Gold Coin"),
    (HoldingType.GOLD_JEWELRY.value,   "Gold Jewellery"),
    (HoldingType.TERM_INSURANCE.value, "Term Insurance"),
    (HoldingType.CRYPTO.value,         "Crypto"),
    (HoldingType.REAL_ESTATE.value,    "Real Estate"),
]

EXCHANGES = ["NSE", "BSE", "NYSE", "NASDAQ", "Other"]

MARKET_CAPS = [
    ("",           "— Unclassified —"),
    ("large_cap",  "Large Cap"),
    ("mid_cap",    "Mid Cap"),
    ("small_cap",  "Small Cap"),
    ("sme",        "SME"),
]

PAYOUT_FREQS = [
    ("on_maturity", "On Maturity"),
    ("monthly",     "Monthly"),
    ("quarterly",   "Quarterly"),
    ("annual",      "Annual"),
]

GOLD_PURITIES = ["24K", "22K", "18K", "14K", "Other"]

# Holding types that need stock-style fields
_STOCK_TYPES  = {HoldingType.STOCK.value, HoldingType.ETF.value, HoldingType.CRYPTO.value}
_MF_TYPES     = {HoldingType.SIP.value, HoldingType.MUTUAL_FUND.value}
_FD_TYPES     = {HoldingType.FD.value, HoldingType.BOND.value,
                 HoldingType.PPF.value, HoldingType.EPF.value, HoldingType.NPS.value}
_GOLD_TYPES   = {HoldingType.GOLD_COIN.value, HoldingType.GOLD_JEWELRY.value}
_INS_TYPES    = {HoldingType.TERM_INSURANCE.value}


class HoldingDialog(QDialog):
    """Modal dialog for creating or editing a Holding."""

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        holding: Optional[Holding] = None,
        accounts: Optional[list] = None,   # list of (id, name)
        stock_lookup=None,                 # callable(symbol) -> dict | None
    ) -> None:
        super().__init__(parent)
        self._holding = holding
        self._stock_lookup = stock_lookup
        self._accounts = accounts or []
        self._editing = holding is not None
        self.setWindowTitle("Edit Holding" if self._editing else "Add Holding")
        self.setMinimumWidth(500)
        self.setModal(True)
        self._build()
        if self._editing:
            self._populate(holding)  # type: ignore[arg-type]

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(12)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(scroll.Shape.NoFrame)
        inner = QWidget()
        self._form = QVBoxLayout(inner)
        self._form.setSpacing(14)
        scroll.setWidget(inner)

        # ── Core fields ──────────────────────────────────────────────────
        core = QGroupBox("Basic Info")
        cf = QFormLayout(core)
        cf.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("e.g. Reliance Industries, HDFC Flexi Cap …")
        cf.addRow("Name *", self.name_edit)

        self.type_combo = QComboBox()
        for key, label in HOLDING_TYPES:
            self.type_combo.addItem(label, key)
        cf.addRow("Type *", self.type_combo)

        self.institution_edit = QLineEdit()
        self.institution_edit.setPlaceholderText("Broker / AMC / Bank …")
        cf.addRow("Institution", self.institution_edit)

        self.folio_edit = QLineEdit()
        self.folio_edit.setPlaceholderText("Folio / account / policy number")
        cf.addRow("Folio / Account", self.folio_edit)

        self.account_combo = QComboBox()
        self.account_combo.addItem("— Not linked —", None)
        for aid, name in self._accounts:
            self.account_combo.addItem(name, aid)
        cf.addRow("Linked Account", self.account_combo)

        self.purchase_date = QDateEdit()
        self.purchase_date.setCalendarPopup(True)
        self.purchase_date.setDate(QDate.currentDate())
        self.purchase_date.setDisplayFormat("dd MMM yyyy")
        cf.addRow("Purchase Date", self.purchase_date)

        self.invested_spin = _money_spin()
        cf.addRow("Amount Invested *", self.invested_spin)

        self.current_spin = _money_spin()
        cf.addRow("Current Value", self.current_spin)

        self.active_check = QCheckBox("Active")
        self.active_check.setChecked(True)
        cf.addRow("", self.active_check)

        self._form.addWidget(core)

        # ── Stock / ETF / Crypto ─────────────────────────────────────────
        self.stock_group = QGroupBox("Stock / ETF Details")
        sg = QFormLayout(self.stock_group)

        self.symbol_edit = QLineEdit()
        self.symbol_edit.setPlaceholderText("RELIANCE, NIFTYBEES …")
        sg.addRow("Symbol", self.symbol_edit)
        self.symbol_hint = QLabel("")
        self.symbol_hint.setObjectName("fieldHint")
        self.symbol_hint.setVisible(False)
        sg.addRow("", self.symbol_hint)
        self.symbol_edit.editingFinished.connect(self._on_symbol_entered)

        self.exchange_combo = QComboBox()
        for ex in EXCHANGES:
            self.exchange_combo.addItem(ex)
        sg.addRow("Exchange", self.exchange_combo)

        self.qty_spin = _qty_spin()
        sg.addRow("Quantity", self.qty_spin)

        self.avg_price_spin = _money_spin()
        sg.addRow("Avg Buy Price", self.avg_price_spin)

        self.cur_price_spin = _money_spin()
        sg.addRow("Current Price", self.cur_price_spin)

        self.cap_combo = QComboBox()
        for key, label in MARKET_CAPS:
            self.cap_combo.addItem(label, key)
        sg.addRow("Market Cap", self.cap_combo)

        self.sector_edit = QLineEdit()
        self.sector_edit.setPlaceholderText("IT, Energy, FMCG …")
        sg.addRow("Sector", self.sector_edit)

        self._form.addWidget(self.stock_group)

        # ── SIP / Mutual Fund ────────────────────────────────────────────
        self.sip_group = QGroupBox("SIP / Mutual Fund Details")
        mg = QFormLayout(self.sip_group)

        self.units_spin = _qty_spin(decimals=4)
        mg.addRow("Units", self.units_spin)

        self.nav_spin = _money_spin()
        mg.addRow("Current NAV", self.nav_spin)

        self.sip_amount_spin = _money_spin()
        mg.addRow("SIP Amount / mo", self.sip_amount_spin)

        self.sip_day_spin = QSpinBox()
        self.sip_day_spin.setRange(1, 31)
        self.sip_day_spin.setValue(1)
        self.sip_day_spin.setSpecialValueText("—")
        mg.addRow("SIP Day of Month", self.sip_day_spin)

        self._form.addWidget(self.sip_group)

        # ── FD / Bond / PPF / EPF / NPS ──────────────────────────────────
        self.fd_group = QGroupBox("Fixed Income Details")
        fg = QFormLayout(self.fd_group)

        self.rate_spin = QDoubleSpinBox()
        self.rate_spin.setRange(0, 30)
        self.rate_spin.setDecimals(2)
        self.rate_spin.setSuffix(" %")
        fg.addRow("Interest / Return Rate", self.rate_spin)

        self.maturity_date = QDateEdit()
        self.maturity_date.setCalendarPopup(True)
        self.maturity_date.setDate(QDate.currentDate().addYears(1))
        self.maturity_date.setDisplayFormat("dd MMM yyyy")
        fg.addRow("Maturity Date", self.maturity_date)

        self.payout_combo = QComboBox()
        for key, label in PAYOUT_FREQS:
            self.payout_combo.addItem(label, key)
        fg.addRow("Payout Frequency", self.payout_combo)

        self.auto_renew_check = QCheckBox("Auto-renew on maturity")
        fg.addRow("", self.auto_renew_check)

        self._form.addWidget(self.fd_group)

        # ── Gold ─────────────────────────────────────────────────────────
        self.gold_group = QGroupBox("Gold Details")
        gg = QFormLayout(self.gold_group)

        self.weight_spin = QDoubleSpinBox()
        self.weight_spin.setRange(0, 10000)
        self.weight_spin.setDecimals(3)
        self.weight_spin.setSuffix(" g")
        gg.addRow("Weight", self.weight_spin)

        self.purity_combo = QComboBox()
        for p in GOLD_PURITIES:
            self.purity_combo.addItem(p)
        gg.addRow("Purity", self.purity_combo)

        self.making_spin = _money_spin()
        gg.addRow("Making Charges", self.making_spin)

        self._form.addWidget(self.gold_group)

        # ── Term Insurance ───────────────────────────────────────────────
        self.ins_group = QGroupBox("Insurance Details")
        ig = QFormLayout(self.ins_group)

        self.sum_assured_spin = _money_spin(max_val=50_00_00_000)
        ig.addRow("Sum Assured", self.sum_assured_spin)

        self.premium_spin = _money_spin()
        ig.addRow("Annual Premium", self.premium_spin)

        self.premium_due = QDateEdit()
        self.premium_due.setCalendarPopup(True)
        self.premium_due.setDate(QDate.currentDate().addYears(1))
        self.premium_due.setDisplayFormat("dd MMM yyyy")
        ig.addRow("Next Premium Due", self.premium_due)

        self.term_spin = QSpinBox()
        self.term_spin.setRange(1, 50)
        self.term_spin.setSuffix(" yrs")
        ig.addRow("Policy Term", self.term_spin)

        self._form.addWidget(self.ins_group)

        # ── Notes ────────────────────────────────────────────────────────
        notes_group = QGroupBox("Notes")
        nl = QVBoxLayout(notes_group)
        self.notes_edit = QTextEdit()
        self.notes_edit.setMaximumHeight(70)
        self.notes_edit.setPlaceholderText("Optional …")
        nl.addWidget(self.notes_edit)
        self._form.addWidget(notes_group)

        root.addWidget(scroll)

        # ── Buttons ──────────────────────────────────────────────────────
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        style_button_box(buttons)
        root.addWidget(buttons)

        # Signals
        self.type_combo.currentIndexChanged.connect(self._on_type_changed)
        self.qty_spin.valueChanged.connect(self._auto_fill_invested)
        self.avg_price_spin.valueChanged.connect(self._auto_fill_invested)
        self.qty_spin.valueChanged.connect(self._auto_fill_current)
        self.cur_price_spin.valueChanged.connect(self._auto_fill_current)
        self.units_spin.valueChanged.connect(self._auto_fill_current_nav)
        self.nav_spin.valueChanged.connect(self._auto_fill_current_nav)

        self._on_type_changed()

    # ------------------------------------------------------------------
    # Type visibility
    # ------------------------------------------------------------------

    def _on_symbol_entered(self) -> None:
        """Fill market cap / sector / exchange from the bundled stock master."""
        if self._stock_lookup is None:
            return
        info = self._stock_lookup(self.symbol_edit.text().strip())
        if not info:
            self.symbol_hint.setVisible(False)
            return
        self.symbol_edit.setText(str(info.get("symbol") or "").upper())
        if not self.name_edit.text().strip() and info.get("name"):
            self.name_edit.setText(info["name"])
        idx = self.exchange_combo.findText(info.get("exchange") or "")
        if idx >= 0:
            self.exchange_combo.setCurrentIndex(idx)
        cap = self.cap_combo.findData(info.get("market_cap") or "")
        if cap >= 0:
            self.cap_combo.setCurrentIndex(cap)
        if info.get("sector") and not self.sector_edit.text().strip():
            self.sector_edit.setText(info["sector"])
        self.symbol_hint.setText(f"Found {info.get('name') or info.get('symbol')} - details filled in")
        self.symbol_hint.setVisible(True)

    def _on_type_changed(self) -> None:
        t = self.type_combo.currentData()
        self.stock_group.setVisible(t in _STOCK_TYPES)
        self.sip_group.setVisible(t in _MF_TYPES)
        self.fd_group.setVisible(t in _FD_TYPES)
        self.gold_group.setVisible(t in _GOLD_TYPES)
        self.ins_group.setVisible(t in _INS_TYPES)
        self.adjustSize()

    # ------------------------------------------------------------------
    # Auto-fill helpers
    # ------------------------------------------------------------------

    def _auto_fill_invested(self) -> None:
        q, p = self.qty_spin.value(), self.avg_price_spin.value()
        if q > 0 and p > 0:
            self.invested_spin.setValue(round(q * p, 2))

    def _auto_fill_current(self) -> None:
        q, p = self.qty_spin.value(), self.cur_price_spin.value()
        if q > 0 and p > 0:
            self.current_spin.setValue(round(q * p, 2))

    def _auto_fill_current_nav(self) -> None:
        u, nav = self.units_spin.value(), self.nav_spin.value()
        if u > 0 and nav > 0:
            self.current_spin.setValue(round(u * nav, 2))

    # ------------------------------------------------------------------
    # Validation & accept
    # ------------------------------------------------------------------

    def _on_accept(self) -> None:
        if not self.name_edit.text().strip():
            self.name_edit.setFocus()
            return
        if self.invested_spin.value() == 0:
            self.invested_spin.setFocus()
            return
        self.accept()

    # ------------------------------------------------------------------
    # Populate from existing holding
    # ------------------------------------------------------------------

    def _populate(self, h: Holding) -> None:
        self.name_edit.setText(h.name or "")
        idx = self.type_combo.findData(h.holding_type)
        if idx >= 0:
            self.type_combo.setCurrentIndex(idx)
        self.institution_edit.setText(h.institution or "")
        self.folio_edit.setText(h.folio_or_account or "")
        aidx = self.account_combo.findData(h.linked_account_id)
        self.account_combo.setCurrentIndex(aidx if aidx >= 0 else 0)
        if h.purchase_date:
            self.purchase_date.setDate(QDate.fromString(h.purchase_date, "yyyy-MM-dd"))
        self.invested_spin.setValue(h.invested_amount or 0)
        self.current_spin.setValue(h.current_value or 0)
        self.active_check.setChecked(bool(h.is_active))

        # Stock
        self.symbol_edit.setText(h.symbol or "")
        ex_idx = self.exchange_combo.findText(h.exchange or "NSE")
        if ex_idx >= 0:
            self.exchange_combo.setCurrentIndex(ex_idx)
        if h.quantity:
            self.qty_spin.setValue(h.quantity)
        if h.avg_price:
            self.avg_price_spin.setValue(h.avg_price)
        if h.current_price:
            self.cur_price_spin.setValue(h.current_price)
        cap_idx = self.cap_combo.findData(h.market_cap or "")
        if cap_idx >= 0:
            self.cap_combo.setCurrentIndex(cap_idx)
        self.sector_edit.setText(h.sector or "")

        # SIP
        if h.quantity:
            self.units_spin.setValue(h.quantity)
        if h.current_price:
            self.nav_spin.setValue(h.current_price)
        if h.sip_amount:
            self.sip_amount_spin.setValue(h.sip_amount)
        if h.sip_day_of_month:
            self.sip_day_spin.setValue(h.sip_day_of_month)

        # FD
        if h.interest_rate:
            self.rate_spin.setValue(h.interest_rate)
        if h.maturity_date:
            self.maturity_date.setDate(QDate.fromString(h.maturity_date, "yyyy-MM-dd"))
        pf_idx = self.payout_combo.findData(h.payout_frequency or "on_maturity")
        if pf_idx >= 0:
            self.payout_combo.setCurrentIndex(pf_idx)
        self.auto_renew_check.setChecked(bool(h.auto_renew))

        # Gold
        if h.weight_grams:
            self.weight_spin.setValue(h.weight_grams)
        pur_idx = self.purity_combo.findText(h.purity or "22K")
        if pur_idx >= 0:
            self.purity_combo.setCurrentIndex(pur_idx)
        if h.making_charges:
            self.making_spin.setValue(h.making_charges)

        # Insurance
        if h.sum_assured:
            self.sum_assured_spin.setValue(h.sum_assured)
        if h.premium_amount:
            self.premium_spin.setValue(h.premium_amount)
        if h.premium_due_date:
            self.premium_due.setDate(QDate.fromString(h.premium_due_date, "yyyy-MM-dd"))
        if h.policy_term_years:
            self.term_spin.setValue(h.policy_term_years)

        if h.notes:
            self.notes_edit.setPlainText(h.notes)

        self._on_type_changed()

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def get_holding(self) -> Holding:
        t = self.type_combo.currentData()

        def _opt_money(spin: QDoubleSpinBox) -> Optional[float]:
            v = spin.value()
            return v if v > 0 else None

        def _opt_qty(spin: QDoubleSpinBox) -> Optional[float]:
            v = spin.value()
            return v if v > 0 else None

        return Holding(
            id=self._holding.id if self._editing else None,
            name=self.name_edit.text().strip(),
            holding_type=t,
            institution=self.institution_edit.text().strip() or None,
            folio_or_account=self.folio_edit.text().strip() or None,
            purchase_date=self.purchase_date.date().toString("yyyy-MM-dd"),
            invested_amount=self.invested_spin.value(),
            current_value=self.current_spin.value(),
            is_active=int(self.active_check.isChecked()),
            linked_account_id=self.account_combo.currentData(),
            notes=self.notes_edit.toPlainText().strip() or None,
            # Stock / ETF
            symbol=self.symbol_edit.text().strip() or None        if t in _STOCK_TYPES else None,
            exchange=self.exchange_combo.currentText()             if t in _STOCK_TYPES else None,
            quantity=_opt_qty(self.qty_spin)                      if t in _STOCK_TYPES else None,
            avg_price=_opt_money(self.avg_price_spin)             if t in _STOCK_TYPES else None,
            current_price=_opt_money(self.cur_price_spin)         if t in _STOCK_TYPES else None,
            market_cap=self.cap_combo.currentData() or None       if t in _STOCK_TYPES else None,
            sector=self.sector_edit.text().strip() or None        if t in _STOCK_TYPES else None,
            # SIP / MF
            sip_amount=_opt_money(self.sip_amount_spin)           if t in _MF_TYPES else None,
            sip_day_of_month=(self.sip_day_spin.value()
                              if t in _MF_TYPES and self.sip_day_spin.value() > 0 else None),
            # FD / Bond etc
            interest_rate=self.rate_spin.value() or None          if t in _FD_TYPES else None,
            maturity_date=(self.maturity_date.date().toString("yyyy-MM-dd")
                           if t in _FD_TYPES else None),
            payout_frequency=self.payout_combo.currentData()      if t in _FD_TYPES else None,
            auto_renew=int(self.auto_renew_check.isChecked())     if t in _FD_TYPES else 0,
            # Gold
            weight_grams=_opt_qty(self.weight_spin)               if t in _GOLD_TYPES else None,
            purity=self.purity_combo.currentText()                if t in _GOLD_TYPES else None,
            making_charges=_opt_money(self.making_spin)           if t in _GOLD_TYPES else None,
            # Insurance
            sum_assured=_opt_money(self.sum_assured_spin)         if t in _INS_TYPES else None,
            premium_amount=_opt_money(self.premium_spin)          if t in _INS_TYPES else None,
            premium_due_date=(self.premium_due.date().toString("yyyy-MM-dd")
                              if t in _INS_TYPES else None),
            policy_term_years=(self.term_spin.value()
                               if t in _INS_TYPES else None),
            # SIP units / NAV shared with quantity / current_price
            **_sip_overrides(t, self.units_spin, self.nav_spin),
        )


def _sip_overrides(t: str, units_spin, nav_spin) -> dict:
    if t in _MF_TYPES:
        u = units_spin.value()
        nav = nav_spin.value()
        return {
            "quantity":      u if u > 0 else None,
            "current_price": nav if nav > 0 else None,
        }
    return {}


# ── helpers ─────────────────────────────────────────────────────────────────

def _money_spin(max_val: float = 10_00_00_000) -> QDoubleSpinBox:
    s = QDoubleSpinBox()
    s.setRange(0, max_val)
    s.setDecimals(2)
    s.setSingleStep(500)
    s.setGroupSeparatorShown(True)
    s.setPrefix("₹ ")
    return s


def _qty_spin(decimals: int = 2) -> QDoubleSpinBox:
    s = QDoubleSpinBox()
    s.setRange(0, 1_00_00_000)
    s.setDecimals(decimals)
    s.setSingleStep(1)
    return s
