"""A date input that can be left unset.

A plain QDateEdit always holds a date, so editing a record that has none (a
holding without a purchase date, a goal without a target date) used to invent
one on Save. ``DateField`` shows "Not set" instead and gives back ``None`` until
a date is picked. Clicking an unset field starts the calendar at today, not 1900.
"""
from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import QDate
from PyQt6.QtWidgets import QDateEdit


class DateField(QDateEdit):
    UNSET = QDate(1900, 1, 1)

    def __init__(self, default: Optional[QDate] = None, parent=None) -> None:
        super().__init__(parent)
        self.setCalendarPopup(True)
        self.setDisplayFormat("dd MMM yyyy")
        self.setMinimumDate(self.UNSET)
        self.setSpecialValueText("Not set")
        self.setDate(default if default is not None else self.UNSET)

    def set_iso(self, iso: Optional[str]) -> None:
        """Show ``iso`` (YYYY-MM-DD), or "Not set" when there is none."""
        d = QDate.fromString((iso or "")[:10], "yyyy-MM-dd")
        self.setDate(d if d.isValid() else self.UNSET)

    def iso(self) -> Optional[str]:
        """The date as YYYY-MM-DD, or None while it is not set."""
        return None if self.date() == self.UNSET else self.date().toString("yyyy-MM-dd")

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        if self.date() == self.UNSET:
            self.setDate(QDate.currentDate())
        super().mousePressEvent(event)
