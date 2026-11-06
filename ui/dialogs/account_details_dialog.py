"""Full account view with section-wise editing.

Shows every detail section read-only. Each section has its own Edit button
that opens the generic SectionEditDialog for just that section. Archiving /
restoring the account lives at the bottom. All persistence goes through the
AccountService passed in by the caller.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from config.account_fields import SECTIONS, Field, label_for_value
from models.account import Account
from services.account_service import AccountService
from ui.dialogs.section_edit_dialog import SectionEditDialog
from utils.formatters import fmt_inr


class AccountDetailsDialog(QDialog):
    """Read-only details with per-section editing and archive/restore."""

    def __init__(self, account: Account, service: AccountService, parent=None) -> None:
        super().__init__(parent)
        self.service = service
        self.account = account
        self.changed = False  # caller refreshes its list when True

        self.setWindowTitle(f"Account - {account.name}")
        self.setModal(True)
        self.setMinimumSize(520, 640)
        self._build()

    # ------------------------------------------------------------------ UI
    def _build(self) -> None:
        root = QVBoxLayout(self)

        self.title = QLabel(self.account.name or "Unnamed")
        self.title.setObjectName("pageTitle")
        root.addWidget(self.title)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        root.addWidget(self.scroll, 1)

        # Bottom action bar: archive/restore + close
        bar = QHBoxLayout()
        self.archive_btn = QPushButton()
        self.archive_btn.clicked.connect(self._on_archive_toggle)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        bar.addWidget(self.archive_btn)
        bar.addStretch(1)
        bar.addWidget(close_btn)
        root.addLayout(bar)

        self._render()

    def _render(self) -> None:
        """(Re)build the scrollable section list from the current account."""
        self.title.setText(self.account.name or "Unnamed")
        self.archive_btn.setText(
            "Restore account" if self.account.is_active != 1 else "Archive account"
        )

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 8, 0)
        layout.setSpacing(6)

        for section in SECTIONS:
            layout.addWidget(self._section_widget(section))

        layout.addStretch(1)
        self.scroll.setWidget(container)

    def _section_widget(self, section) -> QFrame:
        frame = QFrame()
        frame.setObjectName("detailSection")
        box = QVBoxLayout(frame)
        box.setContentsMargins(14, 12, 14, 12)
        box.setSpacing(6)

        # Header: title + Edit button
        header = QHBoxLayout()
        heading = QLabel(section.title)
        heading.setObjectName("sectionLabel")
        edit_btn = QPushButton("Edit")
        edit_btn.setObjectName("tileBtn")
        edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        edit_btn.clicked.connect(lambda _=False, s=section: self._edit_section(s))
        header.addWidget(heading, 1)
        header.addWidget(edit_btn, 0)
        box.addLayout(header)

        # Read-only field rows
        form = QFormLayout()
        form.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow
        )
        for f in section.fields:
            form.addRow(f.label, self._value_label(f))
        box.addLayout(form)
        return frame

    def _value_label(self, f: Field) -> QLabel:
        value = getattr(self.account, f.attr, None)
        text = self._format_value(f, value)
        lbl = QLabel(text)
        lbl.setObjectName("detailValue")
        lbl.setWordWrap(True)
        lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        return lbl

    @staticmethod
    def _format_value(f: Field, value) -> str:
        if f.kind == "checkbox":
            return "Yes" if value else "No"
        if f.kind == "money":
            return fmt_inr(value or 0.0)
        if f.kind == "percent":
            return f"{value:.2f} %" if value else "-"
        if f.kind in ("int", "day"):
            return str(value) if value else "-"
        if f.kind == "combo":
            return label_for_value(f, value) or "-"
        return str(value) if value not in (None, "") else "-"

    # --------------------------------------------------------------- actions
    def _edit_section(self, section) -> None:
        dialog = SectionEditDialog(self.account, section, parent=self)
        if dialog.exec():
            updated = dialog.get_account()
            self.service.update_account(updated)
            refreshed = self.service.get_account(self.account.id)
            self.account = refreshed or updated
            self.changed = True
            self._render()

    def _on_archive_toggle(self) -> None:
        if self.account.id is None:
            return
        if self.account.is_active == 1:
            confirm = QMessageBox.question(
                self,
                "Archive account",
                f'Archive "{self.account.name}"?\n\n'
                "It will be hidden from active lists but its history is kept.",
            )
            if confirm != QMessageBox.StandardButton.Yes:
                return
            self.service.archive_account(self.account.id)
        else:
            self.service.restore_account(self.account.id)

        self.account = self.service.get_account(self.account.id) or self.account
        self.changed = True
        self._render()
