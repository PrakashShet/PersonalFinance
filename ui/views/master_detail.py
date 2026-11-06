"""MasterDetailView - the shared shape of Accounts, Investments, Liabilities,
Goals and Income: header -> KPI row -> filters -> [tile list | detail pane].

Subclasses provide data and rendering through a handful of hooks; selection,
empty states, the "show inactive" toggle, lazy refresh and re-theming are
handled here once instead of five times.

Hooks
    fetch(include_inactive) -> list        items to show
    filter_items(items) -> list            apply the page's own filter (optional)
    make_tile(item, selected) -> ListTile
    render_detail(item, panel)             fill the DetailPanel
    refresh_kpis(items)                    update KPI cards (optional)
    on_add()                               the header's primary action
    on_activate(item)                      double-click (default: nothing)
"""
from __future__ import annotations

from typing import Any, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QScrollArea,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from services.app_context import AppContext
from ui.widgets.common import EmptyState, PageHeader, button
from ui.widgets.detail_panel import DetailPanel
from ui.widgets.kpi_card import KpiCard
from ui.widgets.list_tile import ListTile
from utils.logger import get_logger

log = get_logger(__name__)


class MasterDetailView(QWidget):
    title = ""
    subtitle = ""
    add_label = "Add"
    topics: frozenset[str] = frozenset()
    inactive_label: Optional[str] = "Show inactive"
    empty_icon = "plus"
    empty_title = "Nothing here yet"
    empty_text = ""
    select_hint = "Select an item on the left to see its details."

    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self.ctx = ctx
        self._topics = set(self.topics)
        self._dirty = True
        self._items: list = []
        self._tiles: list[ListTile] = []
        self._selected_id: Any = None

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(18)

        self.add_btn = button(self.add_label, "primary", "plus", on_click=self.on_add)
        self.header = PageHeader(self.title, self.subtitle,
                                 [*self.header_actions(), self.add_btn])
        root.addWidget(self.header)

        self.kpis: list[KpiCard] = self.build_kpis()
        if self.kpis:
            kpi_row = QHBoxLayout()
            kpi_row.setSpacing(14)
            for card in self.kpis:
                kpi_row.addWidget(card)
            root.addLayout(kpi_row)

        extra = self.build_extra()
        if extra is not None:
            root.addWidget(extra)

        bar = QHBoxLayout()
        bar.setSpacing(10)
        filters = self.build_filters()
        if filters is not None:
            bar.addWidget(filters)
        bar.addStretch(1)
        self.inactive_check: Optional[QCheckBox] = None
        if self.inactive_label:
            self.inactive_check = QCheckBox(self.inactive_label)
            self.inactive_check.toggled.connect(lambda _c: self.refresh())
            bar.addWidget(self.inactive_check)
        root.addLayout(bar)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self._build_list())
        splitter.addWidget(self._build_detail())
        splitter.setStretchFactor(0, 5)
        splitter.setStretchFactor(1, 6)
        splitter.setSizes([460, 560])
        root.addWidget(splitter, 1)

        self.ctx.events.changed.connect(self._on_data_changed)
        self.refresh()

    # ------------------------------------------------------------ hooks
    def header_actions(self) -> list[QWidget]:
        return []

    def build_kpis(self) -> list[KpiCard]:
        return []

    def build_extra(self) -> Optional[QWidget]:
        return None

    def build_filters(self) -> Optional[QWidget]:
        return None

    def fetch(self, include_inactive: bool) -> list:
        raise NotImplementedError

    def filter_items(self, items: list) -> list:
        return items

    def item_id(self, item) -> Any:
        return item.id

    def make_tile(self, item, selected: bool) -> ListTile:
        raise NotImplementedError

    def render_detail(self, item, panel: DetailPanel) -> None:
        raise NotImplementedError

    def refresh_kpis(self, items: list) -> None:
        pass

    def on_add(self) -> None:
        pass

    def on_activate(self, item) -> None:
        pass

    # ------------------------------------------------------------- layout
    def _build_list(self) -> QWidget:
        self.list_stack = QStackedWidget()
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.tile_container = QWidget()
        self.tile_layout = QVBoxLayout(self.tile_container)
        self.tile_layout.setContentsMargins(0, 0, 8, 0)
        self.tile_layout.setSpacing(8)
        self.tile_layout.addStretch(1)
        self.scroll.setWidget(self.tile_container)
        self.list_stack.addWidget(self.scroll)

        self.empty = EmptyState(self.empty_icon, self.empty_title, self.empty_text,
                                self.add_label, self.on_add)
        self.list_stack.addWidget(self.empty)
        self.list_stack.setMinimumWidth(320)
        return self.list_stack

    def _build_detail(self) -> QWidget:
        card = QFrame()
        card.setObjectName("detailCard")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(0, 0, 0, 0)
        self.detail_stack = QStackedWidget()
        self.placeholder = EmptyState("chevron_right", "Nothing selected", self.select_hint)
        self.detail_stack.addWidget(self.placeholder)
        self.detail = DetailPanel()
        self.detail_stack.addWidget(self.detail)
        lay.addWidget(self.detail_stack)
        card.setMinimumWidth(380)
        return card

    # ------------------------------------------------------------ refresh
    def _on_data_changed(self, topic: str) -> None:
        if topic in self._topics:
            self._dirty = True

    def mark_dirty(self) -> None:
        self._dirty = True

    def ensure_fresh(self) -> None:
        if self._dirty:
            self.refresh()

    def include_inactive(self) -> bool:
        return bool(self.inactive_check and self.inactive_check.isChecked())

    def refresh(self) -> None:
        try:
            all_items = self.fetch(self.include_inactive())
        except Exception:
            log.exception(f"{type(self).__name__}: loading items failed")
            all_items = []
        self._items = all_items
        visible = self.filter_items(all_items)
        ids = [self.item_id(i) for i in visible]
        if self._selected_id not in ids:
            self._selected_id = ids[0] if ids else None
        self._rebuild_tiles(visible)
        try:
            self.refresh_kpis(all_items)
        except Exception:
            log.exception(f"{type(self).__name__}: KPI refresh failed")
        self._show_selected()
        self._dirty = False

    def _rebuild_tiles(self, visible: list) -> None:
        for t in self._tiles:
            t.setParent(None)
            t.deleteLater()
        self._tiles = []
        while self.tile_layout.count():
            self.tile_layout.takeAt(0)
        for item in visible:
            tile = self.make_tile(item, self.item_id(item) == self._selected_id)
            tile.clicked.connect(self.select)
            tile.activated.connect(self._activate)
            self._tiles.append(tile)
            self.tile_layout.addWidget(tile)
        self.tile_layout.addStretch(1)
        self.list_stack.setCurrentIndex(0 if visible else 1)

    def select(self, item_id: Any) -> None:
        self._selected_id = item_id
        for t in self._tiles:
            t.set_selected(t.key == item_id)
        self._show_selected()

    def _activate(self, item_id: Any) -> None:
        self.select(item_id)
        item = self.selected()
        if item is not None:
            self.on_activate(item)

    def selected(self):
        if self._selected_id is None:
            return None
        return next((i for i in self._items if self.item_id(i) == self._selected_id), None)

    def _show_selected(self) -> None:
        item = self.selected()
        if item is None:
            self.detail_stack.setCurrentIndex(0)
            return
        self.detail.clear()
        try:
            self.render_detail(item, self.detail)
        except Exception:
            log.exception(f"{type(self).__name__}: rendering detail failed")
        self.detail.finish()
        self.detail_stack.setCurrentIndex(1)
        for t in self._tiles:
            if t.key == self._selected_id:
                self.scroll.ensureWidgetVisible(t, 0, 40)
