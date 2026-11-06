"""Right-hand detail pane shared by every master/detail page.

Header: title, subtitle, badges and the actions for the selected item (actions
sit next to what they act on). Body: a scrollable column of sections -
stat grids, banners, tables, custom widgets.
"""
from __future__ import annotations

from typing import Callable, Optional, Sequence

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ui.widgets.common import (
    Badge,
    Banner,
    StatGrid,
    button,
    clear_layout,
    hline,
    label,
)

Action = tuple  # (text, callback, kind, icon_name)


class DetailPanel(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(14)

        head = QHBoxLayout()
        head.setSpacing(12)
        titles = QVBoxLayout()
        titles.setSpacing(4)
        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        self.title = label("", "detailTitle", wrap=True)
        title_row.addWidget(self.title, 1)
        self._badges = QHBoxLayout()
        self._badges.setSpacing(6)
        title_row.addLayout(self._badges)
        titles.addLayout(title_row)
        self.subtitle = label("", "pageSubtitle", wrap=True)
        titles.addWidget(self.subtitle)
        head.addLayout(titles, 1)
        root.addLayout(head)

        self._actions = QHBoxLayout()
        self._actions.setSpacing(8)
        root.addLayout(self._actions)
        root.addWidget(hline())

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        holder = QWidget()
        self.body = QVBoxLayout(holder)
        self.body.setContentsMargins(0, 2, 6, 2)
        self.body.setSpacing(18)
        scroll.setWidget(holder)
        root.addWidget(scroll, 1)

    # -------------------------------------------------------------- header
    def set_header(self, title: str, subtitle: str = "",
                   badges: Sequence[tuple[str, str]] = ()) -> None:
        self.title.setText(title)
        self.subtitle.setText(subtitle)
        self.subtitle.setVisible(bool(subtitle))
        clear_layout(self._badges)
        for text, tone in badges:
            self._badges.addWidget(Badge(text, tone))

    def set_actions(self, actions: Sequence[Action]) -> None:
        clear_layout(self._actions)
        for item in actions:
            text, callback = item[0], item[1]
            kind = item[2] if len(item) > 2 else "secondary"
            icon_name = item[3] if len(item) > 3 else None
            self._actions.addWidget(button(text, kind, icon_name, on_click=callback))
        self._actions.addStretch(1)

    # ---------------------------------------------------------------- body
    def clear(self) -> None:
        clear_layout(self.body)

    def add_stats(self, title: str, items: Sequence[tuple], columns: int = 3,
                  action: Optional[tuple[str, Callable]] = None) -> StatGrid:
        section = self._section(title, action)
        grid = StatGrid(columns)
        grid.set_items(items)
        section.addWidget(grid)
        return grid

    def add_banner(self, text: str, tone: str = "info", action_text: str = "",
                   on_action: Optional[Callable] = None) -> Banner:
        b = Banner(text, tone, action_text, on_action)
        self.body.addWidget(b)
        return b

    def add_section(self, title: str, widget: QWidget,
                    action: Optional[tuple[str, Callable]] = None) -> None:
        section = self._section(title, action)
        section.addWidget(widget)

    def add_widget(self, widget: QWidget) -> None:
        self.body.addWidget(widget)

    def add_text(self, text: str, role: str = "muted") -> None:
        self.body.addWidget(label(text, role, wrap=True))

    def finish(self) -> None:
        self.body.addStretch(1)

    def _section(self, title: str, action: Optional[tuple[str, Callable]]) -> QVBoxLayout:
        box = QVBoxLayout()
        box.setContentsMargins(0, 0, 0, 0)     # align with the header and plain text
        box.setSpacing(10)
        if title or action:
            head = QHBoxLayout()
            head.addWidget(label(title, "sectionTitle"), 1)
            if action:
                head.addWidget(button(action[0], "link", on_click=action[1]))
            box.addLayout(head)
        holder = QWidget()
        holder.setLayout(box)
        self.body.addWidget(holder)
        return box
