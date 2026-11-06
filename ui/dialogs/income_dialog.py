"""Add / Edit Income Source dialog."""
from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from models.income import IncomeSource


SOURCE_TYPES = [
    ("salary",    "Salary"),
    ("web_app",   "Web App / SaaS"),
    ("trading",   "Trading P&L"),
    ("rental",    "Rental Income"),
    ("freelance", "Freelance"),
    ("dividend",  "Dividend"),
    ("interest",  "Interest"),
    ("other",     "Other"),
]

FREQUENCIES = [
    ("monthly",   "Monthly"),
    ("quarterly", "Quarterly"),
    ("annual",    "Annual"),
    ("irregular", "Irregular"),
    ("one_time",  "One-time"),
]


class IncomeDialog(QDialog):
    """Modal dialog for creating or editing an IncomeSource."""

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        source: Optional[IncomeSource] = None,
        accounts: Optional[list] = None,   # list of (id, name)
    ) -> None:
        super().__init__(parent)
        self._source = source
        self._accounts = accounts or []
        self._editing = source is not None
        self.setWindowTitle("Edit Income Source" if self._editing else "Add Income Source")
        self.setMinimumWidth(480)
        self.setModal(True)

        self._build()
        if self._editing:
            self._populate(source)  # type: ignore[arg-type]

    # ------------------------------------------------------------------
    # Build UI
    # ------------------------------------------------------------------

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(12)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(scroll.Shape.NoFrame)
        inner = QWidget()
        form_layout = QVBoxLayout(inner)
        form_layout.setSpacing(16)
        scroll.setWidget(inner)

        # ---- Basic info ----
        basic_group = QGroupBox("Basic Info")
        basic_form = QFormLayout(basic_group)
        basic_form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("e.g. Monthly Salary, SaaS MRR …")
        basic_form.addRow("Name *", self.name_edit)

        self.type_combo = QComboBox()
        for key, label in SOURCE_TYPES:
            self.type_combo.addItem(label, key)
        basic_form.addRow("Source Type", self.type_combo)

        self.employer_edit = QLineEdit()
        self.employer_edit.setPlaceholderText("Company / payer name")
        basic_form.addRow("Employer / Payer", self.employer_edit)

        self.account_combo = QComboBox()
        self.account_combo.addItem("— Not linked —", None)
        for aid, name in self._accounts:
            self.account_combo.addItem(name, aid)
        basic_form.addRow("Deposited into", self.account_combo)

        self.freq_combo = QComboBox()
        for key, label in FREQUENCIES:
            self.freq_combo.addItem(label, key)
        basic_form.addRow("Frequency", self.freq_combo)

        self.amount_spin = QDoubleSpinBox()
        self.amount_spin.setRange(0, 1_00_00_00_000)
        self.amount_spin.setDecimals(2)
        self.amount_spin.setSingleStep(1000)
        self.amount_spin.setGroupSeparatorShown(True)
        self.amount_spin.setPrefix("₹ ")
        basic_form.addRow("Expected Amount", self.amount_spin)

        self.recurring_check = QCheckBox("Recurring income")
        self.recurring_check.setChecked(True)
        basic_form.addRow("", self.recurring_check)

        self.active_check = QCheckBox("Active")
        self.active_check.setChecked(True)
        basic_form.addRow("", self.active_check)

        form_layout.addWidget(basic_group)

        # ---- Salary breakdown ----
        self.salary_group = QGroupBox("Salary Breakdown (optional)")
        sal_form = QFormLayout(self.salary_group)
        sal_form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)

        def _spin(max_val: float = 10_00_000) -> QDoubleSpinBox:
            s = QDoubleSpinBox()
            s.setRange(0, max_val)
            s.setDecimals(2)
            s.setSingleStep(500)
            s.setGroupSeparatorShown(True)
            s.setPrefix("₹ ")
            s.setSpecialValueText("—")
            return s

        self.basic_spin       = _spin()
        self.hra_spin         = _spin()
        self.special_spin     = _spin()
        self.pf_emp_spin      = _spin()
        self.pf_er_spin       = _spin()
        self.pt_spin          = _spin(5000)
        self.tds_spin         = _spin()

        sal_form.addRow("Basic",               self.basic_spin)
        sal_form.addRow("HRA",                 self.hra_spin)
        sal_form.addRow("Special Allowance",   self.special_spin)
        sal_form.addRow("PF (Employee)",       self.pf_emp_spin)
        sal_form.addRow("PF (Employer)",       self.pf_er_spin)
        sal_form.addRow("Professional Tax",    self.pt_spin)
        sal_form.addRow("TDS",                 self.tds_spin)

        # net take-home preview
        self._net_label = QLabel("Net Take-Home: —")
        self._net_label.setObjectName("kpiValue")
        sal_form.addRow("", self._net_label)

        form_layout.addWidget(self.salary_group)

        # ---- Notes ----
        notes_group = QGroupBox("Notes")
        notes_layout = QVBoxLayout(notes_group)
        self.notes_edit = QTextEdit()
        self.notes_edit.setMaximumHeight(80)
        self.notes_edit.setPlaceholderText("Optional notes …")
        notes_layout.addWidget(self.notes_edit)
        form_layout.addWidget(notes_group)

        root.addWidget(scroll)

        # ---- Buttons ----
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        # Signals
        self.type_combo.currentIndexChanged.connect(self._on_type_changed)
        for sp in (self.basic_spin, self.hra_spin, self.special_spin,
                   self.pf_emp_spin, self.pt_spin, self.tds_spin):
            sp.valueChanged.connect(self._update_net_preview)

        self._on_type_changed()  # set initial visibility

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_type_changed(self) -> None:
        is_salary = self.type_combo.currentData() == "salary"
        self.salary_group.setVisible(is_salary)
        self.adjustSize()

    def _update_net_preview(self) -> None:
        gross = self.basic_spin.value() + self.hra_spin.value() + self.special_spin.value()
        deductions = self.pf_emp_spin.value() + self.pt_spin.value() + self.tds_spin.value()
        net = gross - deductions
        self._net_label.setText(f"Net Take-Home: ₹{net:,.0f}")

    def _on_accept(self) -> None:
        name = self.name_edit.text().strip()
        if not name:
            self.name_edit.setFocus()
            self.name_edit.setPlaceholderText("⚠ Name is required")
            return
        self.accept()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def _populate(self, s: IncomeSource) -> None:
        self.name_edit.setText(s.name or "")
        self.employer_edit.setText(s.employer or "")

        aidx = self.account_combo.findData(s.deposit_account_id)
        self.account_combo.setCurrentIndex(aidx if aidx >= 0 else 0)

        idx = self.type_combo.findData(s.source_type)
        if idx >= 0:
            self.type_combo.setCurrentIndex(idx)

        idx2 = self.freq_combo.findData(s.frequency or "monthly")
        if idx2 >= 0:
            self.freq_combo.setCurrentIndex(idx2)

        if s.expected_amount:
            self.amount_spin.setValue(s.expected_amount)

        self.recurring_check.setChecked(bool(s.is_recurring))
        self.active_check.setChecked(bool(s.is_active))

        for spin, val in [
            (self.basic_spin,   s.basic),
            (self.hra_spin,     s.hra),
            (self.special_spin, s.special_allow),
            (self.pf_emp_spin,  s.pf_employee),
            (self.pf_er_spin,   s.pf_employer),
            (self.pt_spin,      s.professional_tax),
            (self.tds_spin,     s.tds),
        ]:
            if val is not None:
                spin.setValue(val)

        if s.notes:
            self.notes_edit.setPlainText(s.notes)

        self._on_type_changed()
        self._update_net_preview()

    def get_source(self) -> IncomeSource:
        """Return a populated IncomeSource from dialog values."""
        is_salary = self.type_combo.currentData() == "salary"

        def _val(spin: QDoubleSpinBox) -> Optional[float]:
            v = spin.value()
            return v if v > 0 else None

        return IncomeSource(
            id=self._source.id if self._editing else None,
            name=self.name_edit.text().strip(),
            source_type=self.type_combo.currentData(),
            is_recurring=int(self.recurring_check.isChecked()),
            expected_amount=_val(self.amount_spin),
            frequency=self.freq_combo.currentData(),
            employer=self.employer_edit.text().strip() or None,
            basic=_val(self.basic_spin)        if is_salary else None,
            hra=_val(self.hra_spin)            if is_salary else None,
            special_allow=_val(self.special_spin) if is_salary else None,
            pf_employee=_val(self.pf_emp_spin) if is_salary else None,
            pf_employer=_val(self.pf_er_spin)  if is_salary else None,
            professional_tax=_val(self.pt_spin) if is_salary else None,
            tds=_val(self.tds_spin)            if is_salary else None,
            notes=self.notes_edit.toPlainText().strip() or None,
            is_active=int(self.active_check.isChecked()),
            deposit_account_id=self.account_combo.currentData(),
        )
