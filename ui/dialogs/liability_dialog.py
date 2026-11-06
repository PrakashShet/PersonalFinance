"""Add / Edit Liability dialog."""
from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import QDate, Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QScrollArea,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from config.constants import LiabilityType
from models.liability import Liability
from utils.calculators import emi as calc_emi
from ui.widgets.common import style_button_box


LIABILITY_TYPES: list[tuple[str, str]] = [
    (LiabilityType.HOME_LOAN.value,      "Home Loan"),
    (LiabilityType.CAR_LOAN.value,       "Car Loan"),
    (LiabilityType.PERSONAL_LOAN.value,  "Personal Loan"),
    (LiabilityType.EDUCATION_LOAN.value, "Education Loan"),
    (LiabilityType.CREDIT_CARD.value,    "Credit Card"),
    (LiabilityType.BNPL.value,           "BNPL / Buy Now Pay Later"),
]

# Types that carry EMI / tenure (not revolving)
_EMI_TYPES = {
    LiabilityType.HOME_LOAN.value,
    LiabilityType.CAR_LOAN.value,
    LiabilityType.PERSONAL_LOAN.value,
    LiabilityType.EDUCATION_LOAN.value,
}


def _money_spin(max_val: float = 10_00_00_000) -> QDoubleSpinBox:
    s = QDoubleSpinBox()
    s.setRange(0, max_val)
    s.setDecimals(2)
    s.setSingleStep(1000)
    s.setGroupSeparatorShown(True)
    s.setPrefix("Rs ")
    return s


class LiabilityDialog(QDialog):
    """Modal dialog for creating or editing a Liability."""

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        liability: Optional[Liability] = None,
        accounts: Optional[list] = None,   # list of (id, name)
    ) -> None:
        super().__init__(parent)
        self._liability = liability
        self._accounts = accounts or []
        self._editing = liability is not None
        self.setWindowTitle("Edit Liability" if self._editing else "Add Liability")
        self.setMinimumWidth(480)
        self.setModal(True)
        self._build()
        if self._editing:
            self._populate(liability)  # type: ignore[arg-type]

    # ------------------------------------------------------------------
    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(12)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(scroll.Shape.NoFrame)
        inner = QWidget()
        vbox = QVBoxLayout(inner)
        vbox.setSpacing(14)
        scroll.setWidget(inner)

        # -- Core --
        core = QGroupBox("Basic Info")
        cf = QFormLayout(core)

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("e.g. Home Loan, HDFC Credit Card")
        cf.addRow("Name *", self.name_edit)

        self.type_combo = QComboBox()
        for key, label in LIABILITY_TYPES:
            self.type_combo.addItem(label, key)
        cf.addRow("Type", self.type_combo)

        self.lender_edit = QLineEdit()
        self.lender_edit.setPlaceholderText("Bank / NBFC / lender name")
        cf.addRow("Lender", self.lender_edit)

        self.account_combo = QComboBox()
        self.account_combo.addItem("— Not linked —", None)
        for aid, name in self._accounts:
            self.account_combo.addItem(name, aid)
        cf.addRow("Paid from account", self.account_combo)

        self.outstanding_spin = _money_spin()
        cf.addRow("Outstanding Amount *", self.outstanding_spin)

        self.rate_spin = QDoubleSpinBox()
        self.rate_spin.setRange(0, 100)
        self.rate_spin.setDecimals(2)
        self.rate_spin.setSuffix(" %  p.a.")
        cf.addRow("Interest Rate", self.rate_spin)

        self.active_check = QCheckBox("Active")
        self.active_check.setChecked(True)
        cf.addRow("", self.active_check)

        vbox.addWidget(core)

        # -- Loan-specific --
        self.loan_group = QGroupBox("Loan Details")
        lg = QFormLayout(self.loan_group)

        self.principal_spin = _money_spin()
        lg.addRow("Original Principal", self.principal_spin)

        self.emi_spin = _money_spin(5_00_000)
        lg.addRow("EMI Amount", self.emi_spin)

        # EMI auto-calc preview
        self._emi_preview = QLabel("Calculated EMI: --")
        self._emi_preview.setObjectName("fieldHint")
        lg.addRow("", self._emi_preview)

        self.tenure_spin = QSpinBox()
        self.tenure_spin.setRange(1, 600)
        self.tenure_spin.setSuffix(" months")
        lg.addRow("Total Tenure", self.tenure_spin)

        self.remaining_spin = QSpinBox()
        self.remaining_spin.setRange(0, 600)
        self.remaining_spin.setSuffix(" months")
        lg.addRow("Remaining Months", self.remaining_spin)

        self.start_date = QDateEdit()
        self.start_date.setCalendarPopup(True)
        self.start_date.setDate(QDate.currentDate())
        self.start_date.setDisplayFormat("dd MMM yyyy")
        lg.addRow("Start Date", self.start_date)

        vbox.addWidget(self.loan_group)

        # -- Due date (all types) --
        due_group = QGroupBox("Payment")
        dg = QFormLayout(due_group)

        self.due_date = QDateEdit()
        self.due_date.setCalendarPopup(True)
        self.due_date.setDate(QDate.currentDate().addMonths(1))
        self.due_date.setDisplayFormat("dd MMM yyyy")
        dg.addRow("Next Due Date", self.due_date)

        vbox.addWidget(due_group)

        # -- Notes --
        notes_group = QGroupBox("Notes")
        nl = QVBoxLayout(notes_group)
        self.notes_edit = QTextEdit()
        self.notes_edit.setMaximumHeight(70)
        nl.addWidget(self.notes_edit)
        vbox.addWidget(notes_group)

        root.addWidget(scroll)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        style_button_box(buttons)
        root.addWidget(buttons)

        # Signals
        self.type_combo.currentIndexChanged.connect(self._on_type_changed)
        for widget in (self.outstanding_spin, self.rate_spin, self.remaining_spin):
            widget.valueChanged.connect(self._update_emi_preview)

        self._on_type_changed()

    # ------------------------------------------------------------------
    def _on_type_changed(self) -> None:
        t = self.type_combo.currentData()
        self.loan_group.setVisible(t in _EMI_TYPES)
        self.adjustSize()

    def _update_emi_preview(self) -> None:
        outstanding = self.outstanding_spin.value()
        rate = self.rate_spin.value() / 100.0
        months = self.remaining_spin.value()
        if outstanding > 0 and rate > 0 and months > 0:
            e = calc_emi(outstanding, rate, months)
            self._emi_preview.setText(f"Calculated EMI: Rs {e:,.0f} / month")
        else:
            self._emi_preview.setText("Calculated EMI: --")

    def _on_accept(self) -> None:
        if not self.name_edit.text().strip():
            self.name_edit.setFocus()
            return
        if self.outstanding_spin.value() == 0:
            self.outstanding_spin.setFocus()
            return
        self.accept()

    # ------------------------------------------------------------------
    def _populate(self, lb: Liability) -> None:
        self.name_edit.setText(lb.name or "")
        idx = self.type_combo.findData(lb.liability_type)
        if idx >= 0:
            self.type_combo.setCurrentIndex(idx)
        self.lender_edit.setText(lb.lender or "")
        aidx = self.account_combo.findData(lb.account_id)
        self.account_combo.setCurrentIndex(aidx if aidx >= 0 else 0)
        self.outstanding_spin.setValue(lb.outstanding or 0)
        self.rate_spin.setValue(lb.interest_rate or 0)
        self.active_check.setChecked(bool(lb.is_active))
        self.principal_spin.setValue(lb.principal or 0)
        self.emi_spin.setValue(lb.emi_amount or 0)
        self.tenure_spin.setValue(lb.tenure_months or 1)
        self.remaining_spin.setValue(lb.remaining_months or 0)
        if lb.start_date:
            self.start_date.setDate(QDate.fromString(lb.start_date, "yyyy-MM-dd"))
        if lb.next_due_date:
            self.due_date.setDate(QDate.fromString(lb.next_due_date, "yyyy-MM-dd"))
        if lb.notes:
            self.notes_edit.setPlainText(lb.notes)
        self._on_type_changed()
        self._update_emi_preview()

    def get_liability(self) -> Liability:
        t = self.type_combo.currentData()
        is_loan = t in _EMI_TYPES

        def _opt(spin: QDoubleSpinBox) -> Optional[float]:
            v = spin.value()
            return v if v > 0 else None

        def _opt_i(spin: QSpinBox) -> Optional[int]:
            v = spin.value()
            return v if v > 0 else None

        return Liability(
            id=self._liability.id if self._editing else None,
            name=self.name_edit.text().strip(),
            liability_type=t,
            lender=self.lender_edit.text().strip() or None,
            outstanding=self.outstanding_spin.value(),
            interest_rate=self.rate_spin.value() or None,
            principal=self.principal_spin.value() if is_loan else 0.0,
            emi_amount=_opt(self.emi_spin)        if is_loan else None,
            tenure_months=_opt_i(self.tenure_spin)   if is_loan else None,
            remaining_months=_opt_i(self.remaining_spin) if is_loan else None,
            start_date=(self.start_date.date().toString("yyyy-MM-dd")
                        if is_loan else None),
            next_due_date=self.due_date.date().toString("yyyy-MM-dd"),
            account_id=self.account_combo.currentData(),
            notes=self.notes_edit.toPlainText().strip() or None,
            is_active=int(self.active_check.isChecked()),
        )
