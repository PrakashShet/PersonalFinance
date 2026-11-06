"""Tile widget representing a single account in the Accounts view.

Single click selects the tile (shows the detail panel on the right);
double click opens the section-editor dialog directly. Selection highlight
is toggled via ``set_selected``.
"""
from __future__ import annotations

from typing import Callable

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout

from config.constants import AccountType
from models.account import Account
from utils.formatters import fmt_money

_TYPE_LABELS = {
    AccountType.SAVINGS.value: "Savings",
    AccountType.CURRENT.value: "Current",
    AccountType.SALARY.value: "Salary",
    AccountType.CASH.value: "Cash",
    AccountType.WALLET.value: "Wallet",
    AccountType.CREDIT_CARD.value: "Credit Card",
}

_STYLE = """
QFrame#accountTile {
    background-color: rgba(201, 170, 122, 0.10);
    border: 1px solid rgba(201, 170, 122, 0.30);
    border-radius: 14px;
}
QFrame#accountTile:hover {
    background-color: rgba(201, 170, 122, 0.17);
    border-color: rgba(201, 170, 122, 0.55);
}
QFrame#accountTile[selected="true"] {
    background-color: rgba(201, 170, 122, 0.22);
    border: 2px solid rgba(201, 170, 122, 0.78);
}
QFrame#accountTile[archived="true"] {
    background-color: rgba(201, 170, 122, 0.05);
    border-color: rgba(201, 170, 122, 0.18);
}
"""

_ACTIVE_BADGE   = ("rgba(16, 185, 129, 0.16)", "#6ee7b7")
_INACTIVE_BADGE = ("rgba(201, 170, 122, 0.10)", "#9c8869")


def _badge(text: str, bg: str, fg: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(
        f"background-color:{bg}; color:{fg}; border-radius:6px; "
        f"padding:2px 8px; font-size:11px; font-weight:600;"
    )
    return lbl


class AccountTile(QFrame):
    """Clickable tile in the accounts master list."""

    def __init__(
        self,
        account: Account,
        *,
        selected: bool = False,
        on_click: Callable[[Account], None],
        on_activate: Callable[[Account], None] | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.account = account
        self._on_click = on_click
        self._on_activate = on_activate

        self.setObjectName("accountTile")
        self.setProperty("selected", selected)
        self.setProperty("archived", account.is_active != 1)
        self.setStyleSheet(_STYLE)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(120)
        self._build()

    def _build(self) -> None:
        a = self.account
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(6)

        # Header: name + status badge
        header = QHBoxLayout()
        name = QLabel(a.name or "Unnamed")
        name.setWordWrap(True)
        name.setStyleSheet(
            "color:#f4eee2; font-size:16px; font-weight:700; background:transparent;"
        )
        header.addWidget(name, 1)
        ab_bg, ab_fg = _ACTIVE_BADGE if a.is_active == 1 else _INACTIVE_BADGE
        header.addWidget(
            _badge("Active" if a.is_active == 1 else "Archived", ab_bg, ab_fg), 0
        )
        root.addLayout(header)

        # Meta: type + institution
        meta_bits = [_TYPE_LABELS.get(a.account_type, a.account_type)]
        if a.institution:
            meta_bits.append(a.institution)
        meta = QLabel("   ·   ".join(meta_bits))
        meta.setStyleSheet("color:#c4a878; font-size:12px; background:transparent;")
        root.addWidget(meta)

        # Flags
        flags = []
        if a.demat_enabled:
            flags.append("Demat")
        if a.investment_enabled:
            flags.append("Investment")
        if flags:
            flag_lbl = QLabel("   +   ".join(flags) + " enabled")
            flag_lbl.setStyleSheet(
                "color:#9c8869; font-size:11px; background:transparent;"
            )
            root.addWidget(flag_lbl)

        root.addStretch(1)

        # Balance (in the account's own currency)
        bal = QLabel(fmt_money(a.current_balance, a.currency))
        bal.setStyleSheet(
            "color:#f4eee2; font-size:15px; font-weight:700; background:transparent;"
        )
        root.addWidget(bal)

    def set_selected(self, selected: bool) -> None:
        self.setProperty("selected", selected)
        self.style().unpolish(self)
        self.style().polish(self)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._on_click(self.account)
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._on_activate:
            self._on_activate(self.account)
        super().mouseDoubleClickEvent(event)
