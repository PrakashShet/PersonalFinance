"""Shared helpers for account QComboBox widgets."""
from __future__ import annotations

from PyQt6.QtWidgets import QComboBox


def reload_account_combo(
    combo: QComboBox,
    accounts: list[tuple[int, str]],
    *,
    all_label: str | None = "All accounts",
    all_value=None,
) -> None:
    """Rebuild combo items from ``(id, name)`` pairs, preserving selection."""
    selected = combo.currentData()
    combo.blockSignals(True)
    combo.clear()
    if all_label is not None:
        combo.addItem(all_label, all_value)
    for aid, name in accounts:
        combo.addItem(name, aid)
    idx = combo.findData(selected)
    combo.setCurrentIndex(idx if idx >= 0 else 0)
    combo.blockSignals(False)
