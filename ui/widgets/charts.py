"""Theme-aware charts.

* :class:`TrendChart` - one series over time (net worth): 2px line, a ~10%
  area wash, solid hairline grid, value at the end, hover crosshair + tooltip.
  A single series needs no legend; the card title names it.
* :class:`SegmentedBar` - one whole split into parts (allocation): a thin
  8px bar, 2px surface gaps between parts, fully rounded ends, plus a legend
  *table* (name, amount, share) so identity and value never depend on colour.

Series colours come from the validated categorical slots in ``tokens.py`` and
are assigned in a fixed order by entity, never by rank.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Callable, Optional, Sequence

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QPainter, QPainterPath
from PyQt6.QtWidgets import (
    QGridLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ui.theme import theme
from ui.widgets.common import clear_layout, label

try:
    import pyqtgraph as pg

    pg.setConfigOptions(antialias=True)
    _HAS_PG = True
except ImportError:  # pragma: no cover
    _HAS_PG = False


def _ts(d: str) -> float:
    return datetime.combine(date.fromisoformat(d[:10]), datetime.min.time()).timestamp()


class TrendChart(QWidget):
    """Line + area chart of (iso_date, value) points."""

    def __init__(self, value_fmt: Callable[[float], str], height: int = 220, parent=None) -> None:
        super().__init__(parent)
        self._fmt = value_fmt
        self._points: list[tuple[str, float]] = []
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        self._empty = label("", "muted", wrap=True)
        self._empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty.setMinimumHeight(height)
        root.addWidget(self._empty)
        self.plot = None
        if _HAS_PG:
            axis = pg.DateAxisItem(orientation="bottom")
            self.plot = pg.PlotWidget(axisItems={"bottom": axis})
            self.plot.setMinimumHeight(height)
            self.plot.setBackground(None)
            self.plot.setMenuEnabled(False)
            self.plot.hideButtons()
            self.plot.setMouseEnabled(x=False, y=False)
            pi = self.plot.getPlotItem()
            pi.showGrid(x=False, y=True, alpha=1.0)
            self._curve = pi.plot([], [])
            self._fill_base = pi.plot([], [])
            self._fill = pg.FillBetweenItem(self._curve, self._fill_base)
            pi.addItem(self._fill)
            self._end_dot = pg.ScatterPlotItem(size=9)
            pi.addItem(self._end_dot)
            self._end_label = pg.TextItem(anchor=(1, 1.2))
            pi.addItem(self._end_label)
            self._vline = pg.InfiniteLine(angle=90, movable=False)
            self._vline.setVisible(False)
            pi.addItem(self._vline, ignoreBounds=True)
            self._hover = pg.TextItem(anchor=(0, 1))
            self._hover.setVisible(False)
            pi.addItem(self._hover, ignoreBounds=True)
            self.plot.scene().sigMouseMoved.connect(self._on_mouse)
            root.addWidget(self.plot)
        theme.changed.connect(self._restyle)
        self._restyle()

    def set_points(self, points: Sequence[tuple[str, float]], empty_text: str = "") -> None:
        self._points = [(d, float(v)) for d, v in points]
        has = len(self._points) >= 2 and self.plot is not None
        self._empty.setText(empty_text or "Not enough history yet.")
        self._empty.setVisible(not has)
        if self.plot is None:
            return
        self.plot.setVisible(has)
        if not has:
            return
        xs = [_ts(d) for d, _ in self._points]
        ys = [v for _, v in self._points]
        lo = min(min(ys), 0.0) if min(ys) < 0 else min(ys)
        self._curve.setData(xs, ys)
        self._fill_base.setData(xs, [lo] * len(xs))
        self._end_dot.setData([xs[-1]], [ys[-1]])
        self._end_label.setText(self._fmt(ys[-1]))
        self._end_label.setPos(xs[-1], ys[-1])
        pad = (max(ys) - lo) * 0.12 or abs(ys[-1]) * 0.1 or 1.0
        self.plot.setYRange(lo - pad * 0.2, max(ys) + pad, padding=0)
        self.plot.setXRange(xs[0], xs[-1], padding=0.02)
        left = self.plot.getPlotItem().getAxis("left")
        left.tickStrings = lambda values, scale, spacing: [self._fmt(v) for v in values]

    def _restyle(self) -> None:
        if self.plot is None:
            return
        line = theme.qcolor("series_1")
        wash = theme.qcolor("series_1", 0.10)
        surface = theme.qcolor("surface")
        self.plot.setBackground(surface)
        self._curve.setPen(pg.mkPen(line, width=2))
        self._fill_base.setPen(pg.mkPen(None))
        self._fill.setBrush(pg.mkBrush(wash))
        self._end_dot.setPen(pg.mkPen(surface, width=2))
        self._end_dot.setBrush(pg.mkBrush(line))
        self._end_label.setColor(theme.qcolor("text"))
        self._vline.setPen(pg.mkPen(theme.qcolor("chart_axis"), width=1))
        self._hover.setColor(theme.qcolor("text"))
        self._hover.fill = pg.mkBrush(surface)
        pi = self.plot.getPlotItem()
        # pyqtgraph draws gridlines in the axis pen's colour: give the left
        # axis the hairline grid colour, the bottom axis the baseline colour.
        left, bottom = pi.getAxis("left"), pi.getAxis("bottom")
        left.setPen(pg.mkPen(theme.qcolor("chart_grid"), width=1))
        bottom.setPen(pg.mkPen(theme.qcolor("chart_axis"), width=1))
        for ax in (left, bottom):
            ax.setTextPen(pg.mkPen(theme.qcolor("chart_text")))
            ax.setStyle(tickLength=0, tickTextOffset=8)
        left.setGrid(255)
        if self._points:
            self.set_points(self._points)

    def _on_mouse(self, pos) -> None:
        if not self._points or self.plot is None:
            return
        vb = self.plot.getPlotItem().vb
        if not self.plot.sceneBoundingRect().contains(pos):
            self._vline.setVisible(False)
            self._hover.setVisible(False)
            return
        x = vb.mapSceneToView(pos).x()
        xs = [_ts(d) for d, _ in self._points]
        i = min(range(len(xs)), key=lambda k: abs(xs[k] - x))
        d, v = self._points[i]
        self._vline.setPos(xs[i])
        self._vline.setVisible(True)
        self._hover.setHtml(
            f'<div style="padding:2px 4px;">{date.fromisoformat(d[:10]).strftime("%d %b %Y")}'
            f"<br><b>{self._fmt(v)}</b></div>"
        )
        self._hover.setPos(xs[i], v)
        self._hover.setAnchor((1, 1) if i > len(xs) / 2 else (0, 1))
        self._hover.setVisible(True)

    def leaveEvent(self, event) -> None:
        if self.plot is not None:
            self._vline.setVisible(False)
            self._hover.setVisible(False)
        super().leaveEvent(event)


class _Bar(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.parts: list[tuple[float, str]] = []      # (fraction, colour token)
        self.setFixedHeight(10)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), 8.0
        y = (self.height() - h) / 2
        if not self.parts:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(theme.qcolor("track"))
            p.drawRoundedRect(QRectF(0, y, w, h), h / 2, h / 2)
            return
        clip = QPainterPath()
        clip.addRoundedRect(QRectF(0, y, w, h), h / 2, h / 2)
        p.setClipPath(clip)
        gap = 2.0
        usable = w - gap * (len(self.parts) - 1)
        x = 0.0
        for frac, token in self.parts:
            seg = max(1.0, usable * frac)
            p.fillRect(QRectF(x, y, seg, h), theme.qcolor(token))
            x += seg + gap
        p.end()


class SegmentedBar(QWidget):
    """Part-to-whole bar + legend table. Parts: (key, label, value)."""

    SLOTS = ("series_1", "series_2", "series_3", "series_4", "series_5")

    def __init__(self, value_fmt: Callable[[float], str], compact: bool = False, parent=None) -> None:
        super().__init__(parent)
        self._fmt = value_fmt
        self._compact = compact
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10 if compact else 14)
        self._bar = _Bar()
        root.addWidget(self._bar)
        self._legend = QGridLayout()
        self._legend.setHorizontalSpacing(8 if compact else 12)
        self._legend.setVerticalSpacing(9)
        root.addLayout(self._legend)
        self._parts: list[tuple[str, str, float]] = []
        self._colors: dict[str, str] = {}
        theme.changed.connect(self._render)

    def set_parts(self, parts: Sequence[tuple[str, str, float]],
                  order: Optional[Sequence[str]] = None, empty_text: str = "No data yet") -> None:
        """``order`` fixes which colour slot each key gets (identity, not rank)."""
        keys = list(order) if order else [k for k, _, _ in parts]
        self._colors = {k: (self.SLOTS[i] if i < len(self.SLOTS) else "series_other")
                        for i, k in enumerate(keys)}
        self._colors.setdefault("other", "series_other")
        self._parts = [(k, lbl, v) for k, lbl, v in parts if v > 0]
        self._empty_text = empty_text
        self._render()

    def _render(self) -> None:
        clear_layout(self._legend)
        total = sum(v for _, _, v in self._parts)
        if total <= 0:
            self._bar.parts = []
            self._legend.addWidget(label(getattr(self, "_empty_text", "No data yet"), "muted"), 0, 0)
            self._bar.update()
            return
        self._bar.parts = [(v / total, self._colors.get(k, "series_other")) for k, _, v in self._parts]
        self._bar.update()
        if self._compact:
            # One row: swatch, name, share - every part labelled, no colour-only identity.
            col = 0
            for k, lbl, v in self._parts:
                swatch = QLabel()
                swatch.setFixedSize(10, 10)
                swatch.setStyleSheet(
                    f"background-color: {theme.color(self._colors.get(k, 'series_other'))};"
                    "border-radius: 3px;")
                self._legend.addWidget(swatch, 0, col, Qt.AlignmentFlag.AlignVCenter)
                self._legend.addWidget(label(lbl, "rowTitle"), 0, col + 1)
                self._legend.addWidget(label(f"{v / total * 100:.0f}%  ·  {self._fmt(v)}", "rowMeta"),
                                       0, col + 2)
                spacer = QLabel("")
                spacer.setFixedWidth(14)
                self._legend.addWidget(spacer, 0, col + 3)
                col += 4
            self._legend.setColumnStretch(col, 1)
            return
        for row, (k, lbl, v) in enumerate(self._parts):
            swatch = QLabel()
            swatch.setFixedSize(10, 10)
            swatch.setStyleSheet(
                f"background-color: {theme.color(self._colors.get(k, 'series_other'))};"
                "border-radius: 3px;"
            )
            self._legend.addWidget(swatch, row, 0, Qt.AlignmentFlag.AlignVCenter)
            self._legend.addWidget(label(lbl, "rowTitle"), row, 1)
            value = label(self._fmt(v), "rowValue")
            value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._legend.addWidget(value, row, 2)
            share = label(f"{v / total * 100:.0f}%", "rowMeta")
            share.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            share.setMinimumWidth(38)
            self._legend.addWidget(share, row, 3)
        self._legend.setColumnStretch(1, 1)
