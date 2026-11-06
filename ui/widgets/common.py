"""Shared building blocks for every page.

Everything here is styled by the theme stylesheet through object names and
dynamic properties (``tone``, ``kind``, ``selected``) - no colours in code -
so a theme switch restyles it all without rebuilding a widget.
"""
from __future__ import annotations

from typing import Callable, Iterable, Optional, Sequence

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtGui import QFont, QFontMetrics
from PyQt6.QtWidgets import (
    QButtonGroup,
    QDialogButtonBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLayout,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ui.theme import icons, theme


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def repolish(widget: QWidget) -> None:
    """Re-apply the stylesheet after a dynamic property changed."""
    style = widget.style()
    style.unpolish(widget)
    style.polish(widget)
    widget.update()


def set_tone(widget: QWidget, tone: Optional[str]) -> None:
    widget.setProperty("tone", tone or "")
    repolish(widget)


def clear_layout(layout: QLayout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        w = item.widget()
        if w is not None:
            w.setParent(None)
            w.deleteLater()
        elif item.layout() is not None:
            clear_layout(item.layout())


def label(text: str = "", role: Optional[str] = None, tone: Optional[str] = None,
          wrap: bool = False, selectable: bool = False) -> QLabel:
    lbl = QLabel(text)
    if role:
        lbl.setObjectName(role)
    if tone:
        lbl.setProperty("tone", tone)
    if wrap:
        lbl.setWordWrap(True)
    if selectable:
        lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return lbl


def button(text: str, kind: str = "secondary", icon_name: Optional[str] = None,
           on_click: Optional[Callable] = None, tooltip: str = "",
           size: str = "") -> QPushButton:
    btn = QPushButton(text)
    btn.setProperty("kind", kind)
    if size:
        btn.setProperty("size", size)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    if icon_name:
        color = theme.color("on_accent") if kind == "primary" else (
            theme.color("negative") if kind == "danger" else theme.color("text_secondary"))
        btn.setIcon(icons.icon(icon_name, color, size=16))
        btn.setIconSize(QSize(16, 16))
        btn.setProperty("iconName", icon_name)
    if on_click is not None:
        btn.clicked.connect(lambda _checked=False: on_click())
    if tooltip:
        btn.setToolTip(tooltip)
    return btn


def refresh_button_icon(btn: QPushButton) -> None:
    """Re-tint a button's icon after a theme change."""
    name = btn.property("iconName")
    if not name:
        return
    kind = btn.property("kind")
    color = theme.color("on_accent") if kind == "primary" else (
        theme.color("negative") if kind == "danger" else theme.color("text_secondary"))
    btn.setIcon(icons.icon(name, color, size=16))


def style_button_box(box: QDialogButtonBox) -> None:
    """Mark the accepting button (Save / OK) as the primary action."""
    for b in box.buttons():
        role = box.buttonRole(b)
        if role in (QDialogButtonBox.ButtonRole.AcceptRole, QDialogButtonBox.ButtonRole.YesRole):
            b.setProperty("kind", "primary")
            repolish(b)
        b.setCursor(Qt.CursorShape.PointingHandCursor)


class ElidedLabel(QLabel):
    """Single-line label that shortens itself with "…" instead of forcing its
    container wider (long names and notes used to push pages off-screen).
    The full text is kept in the tooltip."""

    def __init__(self, text: str = "", role: Optional[str] = None,
                 tone: Optional[str] = None, parent=None) -> None:
        super().__init__(parent)
        if role:
            self.setObjectName(role)
        if tone:
            self.setProperty("tone", tone)
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._full = ""
        self.setText(text)

    def setText(self, text: str) -> None:  # noqa: N802 (Qt naming)
        self._full = text or ""
        self._apply()

    def full_text(self) -> str:
        return self._full

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return QSize(24, super().minimumSizeHint().height())

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(self.fontMetrics().horizontalAdvance(self._full) + 4,
                     super().sizeHint().height())

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._apply()

    def _apply(self) -> None:
        elided = self.fontMetrics().elidedText(self._full, Qt.TextElideMode.ElideRight,
                                               max(10, self.width()))
        super().setText(elided)
        self.setToolTip(self._full if elided != self._full else "")


def escape_mnemonic(text: str) -> str:
    """Button/menu text treats & as a shortcut marker - show it literally."""
    return text.replace("&", "&&")


def hline() -> QFrame:
    line = QFrame()
    line.setObjectName("divider")
    line.setFrameShape(QFrame.Shape.NoFrame)
    return line


def icon_label(name: str, token: str = "text_muted", size: int = 18) -> QLabel:
    lbl = QLabel()
    lbl.setPixmap(icons.pixmap(name, theme.color(token), size))
    lbl.setFixedSize(size, size)
    return lbl


# --------------------------------------------------------------------------
# containers
# --------------------------------------------------------------------------

class Card(QFrame):
    """A white (or dark-surface) rounded panel with an optional header row."""

    def __init__(self, title: str = "", subtitle: str = "", action: Optional[QWidget] = None,
                 padding: int = 18, spacing: int = 12, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("card")
        root = QVBoxLayout(self)
        root.setContentsMargins(padding, padding - 2, padding, padding)
        root.setSpacing(spacing)
        self.title_label: Optional[QLabel] = None
        self.subtitle_label: Optional[QLabel] = None
        if title or action is not None:
            head = QHBoxLayout()
            head.setSpacing(8)
            text_col = QVBoxLayout()
            text_col.setSpacing(2)
            self.title_label = label(title, "cardTitle")
            text_col.addWidget(self.title_label)
            if subtitle:
                self.subtitle_label = label(subtitle, "cardSubtitle", wrap=True)
                text_col.addWidget(self.subtitle_label)
            head.addLayout(text_col, 1)
            if action is not None:
                head.addWidget(action, 0, Qt.AlignmentFlag.AlignTop)
            root.addLayout(head)
        self.body = QVBoxLayout()
        self.body.setSpacing(spacing)
        root.addLayout(self.body, 1)


class PageHeader(QWidget):
    """Page title + one-line description + actions on the right."""

    def __init__(self, title: str, subtitle: str = "",
                 actions: Sequence[QWidget] = (), parent=None) -> None:
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)
        col = QVBoxLayout()
        col.setSpacing(3)
        self.title = label(title, "pageTitle")
        col.addWidget(self.title)
        self.subtitle = label(subtitle, "pageSubtitle", wrap=True)
        self.subtitle.setVisible(bool(subtitle))
        col.addWidget(self.subtitle)
        row.addLayout(col, 1)
        self.actions = QHBoxLayout()
        self.actions.setSpacing(8)
        for a in actions:
            self.actions.addWidget(a)
        row.addLayout(self.actions)

    def set_subtitle(self, text: str) -> None:
        self.subtitle.setText(text)
        self.subtitle.setVisible(bool(text))


class Badge(QLabel):
    def __init__(self, text: str, tone: str = "neutral", parent=None) -> None:
        super().__init__(text, parent)
        self.setObjectName("badge")
        self.setProperty("tone", tone)
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)

    def set(self, text: str, tone: str) -> None:
        self.setText(text)
        set_tone(self, tone)


class Banner(QFrame):
    """Inline message with an icon and an optional action button."""

    _ICONS = {"info": "info", "warning": "alert", "negative": "alert", "positive": "check_circle",
              "neutral": "info"}

    def __init__(self, text: str, tone: str = "info", action_text: str = "",
                 on_action: Optional[Callable] = None, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("banner")
        self.setProperty("tone", tone)
        row = QHBoxLayout(self)
        row.setContentsMargins(12, 10, 12, 10)
        row.setSpacing(10)
        token = {"info": "info", "warning": "warning", "negative": "negative",
                 "positive": "positive"}.get(tone, "text_muted")
        row.addWidget(icon_label(self._ICONS.get(tone, "info"), token, 18), 0, Qt.AlignmentFlag.AlignTop)
        self.text = label(text, "bannerText", wrap=True)
        row.addWidget(self.text, 1)
        if action_text and on_action is not None:
            row.addWidget(button(action_text, "secondary", on_click=on_action, size="small"),
                          0, Qt.AlignmentFlag.AlignVCenter)


class EmptyState(QWidget):
    """Friendly 'nothing here yet' with a next step."""

    def __init__(self, icon_name: str, title: str, text: str = "",
                 action_text: str = "", on_action: Optional[Callable] = None,
                 parent=None) -> None:
        super().__init__(parent)
        col = QVBoxLayout(self)
        col.setContentsMargins(24, 32, 24, 32)
        col.setSpacing(8)
        col.addStretch(1)
        self._icon = QLabel()
        self._icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._icon_name = icon_name
        self._paint_icon()
        col.addWidget(self._icon)
        self.title = label(title, "emptyTitle")
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        col.addWidget(self.title)
        self.text = label(text, "emptyText", wrap=True)
        self.text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.text.setVisible(bool(text))
        col.addWidget(self.text)
        if action_text and on_action is not None:
            row = QHBoxLayout()
            row.addStretch(1)
            row.addWidget(button(action_text, "primary", "plus", on_click=on_action))
            row.addStretch(1)
            col.addSpacing(6)
            col.addLayout(row)
        col.addStretch(1)
        theme.changed.connect(self._paint_icon)

    def _paint_icon(self) -> None:
        self._icon.setPixmap(icons.pixmap(self._icon_name, theme.color("text_faint"), 36))

    def set_text(self, title: str, text: str = "") -> None:
        self.title.setText(title)
        self.text.setText(text)
        self.text.setVisible(bool(text))


class SegmentedControl(QFrame):
    """A row of mutually exclusive options (filters, type pickers)."""

    changed = pyqtSignal(str)

    def __init__(self, options: Iterable[tuple[str, str]], current: Optional[str] = None,
                 parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("segmented")
        row = QHBoxLayout(self)
        row.setContentsMargins(3, 3, 3, 3)
        row.setSpacing(2)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._buttons: dict[str, QPushButton] = {}
        for key, text in options:
            b = QPushButton(text)
            b.setObjectName("segment")
            b.setCheckable(True)
            # The checked segment is drawn semi-bold; size every segment for
            # that, or a long selected label loses its last letters.
            bold = QFont(b.font())
            bold.setWeight(QFont.Weight.DemiBold)
            b.setMinimumWidth(QFontMetrics(bold).horizontalAdvance(text) + 32)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _c=False, k=key: self._emit(k))
            self._group.addButton(b)
            self._buttons[key] = b
            row.addWidget(b)
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        first = current or next(iter(self._buttons), None)
        if first:
            self._buttons[first].setChecked(True)
        self._current = first

    def _emit(self, key: str) -> None:
        if key != self._current:
            self._current = key
            self.changed.emit(key)

    def current(self) -> Optional[str]:
        return self._current

    def set_current(self, key: str, emit: bool = False) -> None:
        if key in self._buttons:
            self._buttons[key].setChecked(True)
            changed = key != self._current
            self._current = key
            if emit and changed:
                self.changed.emit(key)

    def set_visible_option(self, key: str, visible: bool) -> None:
        if key in self._buttons:
            self._buttons[key].setVisible(visible)


class StatGrid(QWidget):
    """Label-over-value cells in a grid. Items: (label, value, tone)."""

    def __init__(self, columns: int = 3, parent=None) -> None:
        super().__init__(parent)
        self._columns = columns
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setHorizontalSpacing(24)
        self._grid.setVerticalSpacing(14)

    def set_items(self, items: Sequence[tuple]) -> None:
        clear_layout(self._grid)
        for i, item in enumerate(items):
            text, value = item[0], item[1]
            tone = item[2] if len(item) > 2 else None
            cell = QWidget()
            col = QVBoxLayout(cell)
            col.setContentsMargins(0, 0, 0, 0)
            col.setSpacing(3)
            col.addWidget(label(text, "statLabel"))
            col.addWidget(label(value, "statValue", tone=tone, wrap=True, selectable=True))
            r, c = divmod(i, self._columns)
            self._grid.addWidget(cell, r, c, Qt.AlignmentFlag.AlignTop)
        for c in range(self._columns):
            self._grid.setColumnStretch(c, 1)


def progress(pct: float, tone: str = "", large: bool = False) -> QProgressBar:
    bar = QProgressBar()
    bar.setRange(0, 1000)
    bar.setValue(int(max(0.0, min(100.0, pct)) * 10))
    bar.setTextVisible(False)
    if tone:
        bar.setProperty("tone", tone)
    if large:
        bar.setProperty("size", "large")
    return bar


class ActivityRow(QFrame):
    """A compact list row: date | title + meta | amount (+ optional action)."""

    def __init__(self, date_text: str, title: str, meta: str = "", amount: str = "",
                 tone: Optional[str] = None, action: Optional[QWidget] = None,
                 icon_name: Optional[str] = None, icon_token: str = "text_muted",
                 parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("row")
        row = QHBoxLayout(self)
        row.setContentsMargins(8, 7, 8, 7)
        row.setSpacing(12)
        if icon_name:
            row.addWidget(icon_label(icon_name, icon_token, 18), 0, Qt.AlignmentFlag.AlignVCenter)
        if date_text:
            d = label(date_text, "rowMeta")
            d.setMinimumWidth(78)
            row.addWidget(d, 0)
        col = QVBoxLayout()
        col.setSpacing(1)
        col.addWidget(ElidedLabel(title, "rowTitle"))
        if meta:
            col.addWidget(ElidedLabel(meta, "rowMeta"))
        row.addLayout(col, 1)
        if amount:
            a = label(amount, "rowValue", tone=tone)
            a.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            row.addWidget(a, 0)
        if action is not None:
            row.addWidget(action, 0)
