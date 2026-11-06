"""Accounts tab - master/detail.

Left:  scrollable list of account tiles (single-click to select, double-click
       opens the section edit dialog for the Account Details section).
Right: read-only section list for the selected account with a per-section
       Edit button and archive/restore. Mirrors the layout used by the
       Goals, Liabilities and Income tabs.
"""
from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QFormLayout,
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

from config.account_fields import ACCOUNT_SECTION, SECTIONS, Field, label_for_value
from models.account import Account
from services.app_context import AppContext
from ui.dialogs.section_edit_dialog import SectionEditDialog
from ui.widgets.account_tile import AccountTile
from ui.widgets.kpi_card import KpiCard
from utils.formatters import fmt_inr


class AccountsView(QWidget):
    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self.ctx = ctx
        self.service = ctx.account_service
        self._topics = {"accounts", "transactions"}
        self._dirty = True
        self._accounts: list[Account] = []
        self._tiles: list[AccountTile] = []
        self._selected_id: Optional[int] = None

        self.ctx.events.changed.connect(self._on_data_changed)
        self._build()
        self.refresh()

    # ------------------------------------------------------------------ UI
    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(14)

        # Header: title + Add
        hdr = QHBoxLayout()
        title = QLabel("Accounts")
        title.setObjectName("pageTitle")
        hdr.addWidget(title)
        hdr.addStretch()
        self.add_btn = QPushButton("Add Account")
        self.add_btn.setObjectName("primaryBtn")
        self.add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.add_btn.clicked.connect(self._on_add)
        hdr.addWidget(self.add_btn)
        root.addLayout(hdr)

        # KPI row
        kpi_row = QGridLayout()
        kpi_row.setSpacing(12)
        self.kpi_count = KpiCard("Active Accounts", "-")
        self.kpi_liquid = KpiCard("Cash & Bank", "-")
        self.kpi_cc = KpiCard("Credit Card Outstanding", "-")
        for i, w in enumerate([self.kpi_count, self.kpi_liquid, self.kpi_cc]):
            kpi_row.addWidget(w, 0, i)
        root.addLayout(kpi_row)

        # Toolbar: archived toggle
        bar = QHBoxLayout()
        self.show_archived = QCheckBox("Show archived")
        self.show_archived.stateChanged.connect(self.refresh)
        bar.addStretch(1)
        bar.addWidget(self.show_archived)
        root.addLayout(bar)

        # Splitter: tile list | details panel
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

        # Scrollable list of account tiles
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
        self.scroll.setMinimumHeight(220)
        layout.addWidget(self.scroll, 1)

        self.empty_label = QLabel(
            'No accounts yet. Click "Add Account" to create one.'
        )
        self.empty_label.setObjectName("tileFlags")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setWordWrap(True)
        self.empty_label.hide()
        layout.addWidget(self.empty_label)

        # Action bar (operates on the selected account)
        action_bar = QHBoxLayout()
        self.edit_btn = QPushButton("Edit")
        self.edit_btn.setEnabled(False)
        self.edit_btn.clicked.connect(self._on_edit_first)
        self.archive_btn = QPushButton("Archive")
        self.archive_btn.setEnabled(False)
        self.archive_btn.clicked.connect(self._on_archive_toggle)
        action_bar.addWidget(self.edit_btn)
        action_bar.addWidget(self.archive_btn)
        action_bar.addStretch()
        layout.addLayout(action_bar)
        return container

    def _build_detail(self) -> QWidget:
        self.detail_stack = QStackedWidget()

        placeholder = QLabel("Select an account to see its details.")
        placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        placeholder.setObjectName("tileFlags")
        placeholder.setWordWrap(True)
        self.detail_stack.addWidget(placeholder)

        self.detail = _AccountDetailPanel(on_edit_section=self._edit_section)
        self.detail_stack.addWidget(self.detail)
        return self.detail_stack

    # --------------------------------------------------------------- actions
    def _on_add(self) -> None:
        dialog = SectionEditDialog(
            Account(), ACCOUNT_SECTION, parent=self, title="Add Account"
        )
        if dialog.exec():
            account = dialog.get_account()
            new_id = self.service.create_account(account)
            if new_id is not None:
                self._selected_id = new_id
            self._maybe_warn_loan_tracking(account)
            self.refresh()

    def _on_tile_clicked(self, acct: Account) -> None:
        self._selected_id = acct.id
        for t in self._tiles:
            t.set_selected(t.account.id == acct.id)
        self._update_buttons()
        self.detail.load(acct)
        self.detail_stack.setCurrentIndex(1)

    def _on_tile_activated(self, acct: Account) -> None:
        """Double-click: select, then open the Account Details edit dialog."""
        self._on_tile_clicked(acct)
        self._edit_section(ACCOUNT_SECTION)

    def _on_edit_first(self) -> None:
        """Edit button: open the primary Account Details section editor."""
        self._edit_section(ACCOUNT_SECTION)

    def _edit_section(self, section) -> None:
        acct = self._selected_account()
        if acct is None:
            return
        dialog = SectionEditDialog(acct, section, parent=self)
        if dialog.exec():
            updated = dialog.get_account()
            self.service.update_account(updated)
            self._maybe_warn_loan_tracking(updated)
            self.refresh()

    def _on_archive_toggle(self) -> None:
        acct = self._selected_account()
        if acct is None or acct.id is None:
            return
        if acct.is_active == 1:
            confirm = QMessageBox.question(
                self,
                "Archive account",
                f'Archive "{acct.name}"?\n\n'
                "It will be hidden from active lists but its history is kept.",
            )
            if confirm != QMessageBox.StandardButton.Yes:
                return
            self.service.archive_account(acct.id)
        else:
            self.service.restore_account(acct.id)
        self.refresh()

    def _maybe_warn_loan_tracking(self, account: Account) -> None:
        if not AppContext.account_has_loan_fields(account):
            return
        QMessageBox.information(
            self,
            "Debt tracking",
            "This account has loan fields filled in.\n\n"
            "For accurate net worth, also record the loan under the "
            "Liabilities tab — account loan fields are descriptive; "
            "the Liabilities table is the source of truth for debt totals.",
        )

    def _on_data_changed(self, topic: str) -> None:
        if topic in self._topics:
            self._dirty = True

    def ensure_fresh(self) -> None:
        if self._dirty:
            self.refresh()

    # ---------------------------------------------------------------- render
    def refresh(self) -> None:
        include_archived = self.show_archived.isChecked()
        self._accounts = self.service.get_all(include_archived=include_archived)
        self._refresh_tiles()
        self._update_kpis()
        self._refresh_detail()
        self._dirty = False

    def _refresh_tiles(self) -> None:
        for tile in self._tiles:
            self.tile_layout.removeWidget(tile)
            tile.deleteLater()
        self._tiles = []
        while self.tile_layout.count():
            self.tile_layout.takeAt(0)

        for a in self._accounts:
            tile = AccountTile(
                a,
                selected=(a.id == self._selected_id),
                on_click=self._on_tile_clicked,
                on_activate=self._on_tile_activated,
                parent=self.tile_container,
            )
            self._tiles.append(tile)
            self.tile_layout.addWidget(tile)
        self.tile_layout.addStretch(1)

        has_accounts = bool(self._accounts)
        self.empty_label.setVisible(not has_accounts)
        self.scroll.setVisible(has_accounts)
        self._update_buttons()

    def _refresh_detail(self) -> None:
        acct = self._selected_account()
        if acct is None:
            self.detail_stack.setCurrentIndex(0)
            return
        self.detail.load(acct)
        self.detail_stack.setCurrentIndex(1)

    def _selected_account(self) -> Optional[Account]:
        if self._selected_id is None:
            return None
        return next((a for a in self._accounts if a.id == self._selected_id), None)

    def _update_buttons(self) -> None:
        acct = self._selected_account()
        has_sel = acct is not None
        self.edit_btn.setEnabled(has_sel)
        self.archive_btn.setEnabled(has_sel)
        if acct is not None:
            self.archive_btn.setText(
                "Restore" if acct.is_active != 1 else "Archive"
            )
        else:
            self.archive_btn.setText("Archive")

    def _update_kpis(self) -> None:
        summary = self.service.account_summary()
        self.kpi_count.set_value(str(summary["count"]))
        self.kpi_liquid.set_value(fmt_inr(summary["liquid_balance"], compact=True))
        self.kpi_cc.set_value(
            fmt_inr(summary["credit_card_outstanding"], compact=True)
        )


# ── inline detail panel ─────────────────────────────────────────────────────

class _AccountDetailPanel(QFrame):
    """Read-only section list with a per-section Edit button.

    Mirrors what AccountDetailsDialog renders, but embedded inside the tab.
    """

    def __init__(self, on_edit_section) -> None:
        super().__init__()
        self._on_edit_section = on_edit_section
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setObjectName("breakdownPanel")

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(10)

        self._header = QLabel("")
        self._header.setObjectName("sectionLabel")
        f = self._header.font()
        f.setBold(True)
        f.setPointSize(f.pointSize() + 2)
        self._header.setFont(f)
        root.addWidget(self._header)

        self._subtitle = QLabel("")
        self._subtitle.setObjectName("tileFlags")
        root.addWidget(self._subtitle)

        # Scroll area for the section cards
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._sections_holder = QWidget()
        self._sections_layout = QVBoxLayout(self._sections_holder)
        self._sections_layout.setContentsMargins(0, 4, 6, 4)
        self._sections_layout.setSpacing(8)
        self._sections_layout.addStretch(1)
        self._scroll.setWidget(self._sections_holder)
        root.addWidget(self._scroll, 1)

        self.account: Optional[Account] = None

    def load(self, account: Account) -> None:
        self.account = account
        self._header.setText(account.name or "Unnamed")

        status = "Active" if account.is_active == 1 else "Archived"
        bits = [status]
        if account.account_type:
            bits.append(account.account_type.title().replace("_", " "))
        if account.institution:
            bits.append(account.institution)
        self._subtitle.setText("   ·   ".join(bits))

        # Clear existing section cards
        while self._sections_layout.count():
            item = self._sections_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

        for section in SECTIONS:
            self._sections_layout.addWidget(self._section_widget(section))
        self._sections_layout.addStretch(1)

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
        edit_btn.clicked.connect(lambda _=False, s=section: self._on_edit_section(s))
        header.addWidget(heading, 1)
        header.addWidget(edit_btn, 0)
        box.addLayout(header)

        form = QFormLayout()
        form.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow
        )
        for f in section.fields:
            form.addRow(f.label, self._value_label(f))
        box.addLayout(form)
        return frame

    def _value_label(self, f: Field) -> QLabel:
        value = getattr(self.account, f.attr, None) if self.account else None
        lbl = QLabel(self._format_value(f, value))
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
