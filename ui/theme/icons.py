"""A small, consistent line-icon set, drawn as inline SVG and tinted per theme.

24x24 grid, round caps/joins, one stroke weight - so every icon reads as part
of one family at 16-20px. No image files to ship or lose: the shapes are here.
"""
from __future__ import annotations

from functools import lru_cache

from PyQt6.QtCore import QByteArray, QRectF, Qt
from PyQt6.QtGui import QColor, QIcon, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer

_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
    'stroke="{color}" stroke-width="{weight}" stroke-linecap="round" '
    'stroke-linejoin="round">{body}</svg>'
)

ICONS: dict[str, str] = {
    "dashboard": '<rect x="3.5" y="3.5" width="7" height="8" rx="1.6"/><rect x="13.5" y="3.5" width="7" height="5" rx="1.6"/>'
                 '<rect x="13.5" y="11.5" width="7" height="9" rx="1.6"/><rect x="3.5" y="14.5" width="7" height="6" rx="1.6"/>',
    "accounts": '<path d="M3.5 9.5h17"/><path d="M12 3.5l8.5 4.5h-17z"/><path d="M6 9.5v8M10 9.5v8M14 9.5v8M18 9.5v8"/><path d="M3.5 20.5h17"/>',
    "transactions": '<path d="M5 8h14M16 5l3 3-3 3"/><path d="M19 16H5M8 13l-3 3 3 3"/>',
    "income": '<path d="M3.5 16.5l5.5-5.5 4 4 7.5-7.5"/><path d="M14.5 7.5h6v6"/>',
    "investments": '<circle cx="12" cy="12" r="8.5"/><path d="M12 3.5V12l6 6"/>',
    "liabilities": '<rect x="2.5" y="5.5" width="19" height="13" rx="2.2"/><path d="M2.5 10h19"/><path d="M6.5 14.5h4"/>',
    "goals": '<circle cx="12" cy="12" r="8.5"/><circle cx="12" cy="12" r="4.8"/><circle cx="12" cy="12" r="1.2"/>',
    "budget": '<path d="M3.5 17a8.5 8.5 0 0 1 17 0"/><path d="M12 17l4.2-4.6"/><circle cx="12" cy="17" r="1.4"/>'
              '<path d="M6.3 11.3l1.1 1.1M12 8.5v1.5M17.7 11.3l-1.1 1.1"/>',
    "projections": '<path d="M3.5 3.5v17h17"/><path d="M7.5 15l3.5-4 3 2.5 5-6.5"/>',
    "settings": '<path d="M4 7h9M17 7h3M4 12h3M11 12h9M4 17h11M19 17h1"/>'
                '<circle cx="15" cy="7" r="2"/><circle cx="9" cy="12" r="2"/><circle cx="17" cy="17" r="2"/>',
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "sun": '<circle cx="12" cy="12" r="3.8"/><path d="M12 2.5v2M12 19.5v2M4.6 4.6L6 6M18 18l1.4 1.4M2.5 12h2M19.5 12h2'
           'M4.6 19.4L6 18M18 6l1.4-1.4"/>',
    "moon": '<path d="M19.5 14.2A8 8 0 1 1 9.8 4.5a6.4 6.4 0 0 0 9.7 9.7z"/>',
    "monitor": '<rect x="3" y="4.5" width="18" height="12" rx="2"/><path d="M8.5 20h7M12 16.5V20"/>',
    "check": '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
    "check_circle": '<circle cx="12" cy="12" r="8.5"/><path d="M8.3 12.3l2.6 2.6 4.9-5.4"/>',
    "alert": '<path d="M12 4l9 15.5H3z"/><path d="M12 10v4M12 16.8v.2"/>',
    "info": '<circle cx="12" cy="12" r="8.5"/><path d="M12 11v5M12 7.8v.2"/>',
    "clock": '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/>',
    "edit": '<path d="M4 20h4L19 9l-4-4L4 16z"/><path d="M13.5 6.5l4 4"/>',
    "trash": '<path d="M4.5 7h15M9.5 7V4.5h5V7M6.5 7l1 13h9l1-13"/>',
    "archive": '<rect x="3" y="4" width="18" height="5" rx="1.2"/><path d="M5 9v10.5h14V9M10 13h4"/>',
    "restore": '<path d="M4 12a8 8 0 1 0 2.4-5.7"/><path d="M4 4.5v4h4"/>',
    "search": '<circle cx="11" cy="11" r="6.5"/><path d="M20 20l-4.2-4.2"/>',
    "chevron_down": '<path d="M6 9l6 6 6-6"/>',
    "chevron_up": '<path d="M6 15l6-6 6 6"/>',
    "chevron_right": '<path d="M9 6l6 6-6 6"/>',
    "arrow_up_right": '<path d="M7 17L17 7M9 7h8v8"/>',
    "arrow_down_left": '<path d="M17 7L7 17M15 17H7V9"/>',
    "wallet": '<path d="M4 7.5a2 2 0 0 1 2-2h11.5v3"/><rect x="4" y="8.5" width="16" height="11" rx="2"/><path d="M15.5 14h1.5"/>',
    "folder": '<path d="M3.5 7a2 2 0 0 1 2-2h4l2 2h7a2 2 0 0 1 2 2v8.5a2 2 0 0 1-2 2h-13a2 2 0 0 1-2-2z"/>',
    "shield": '<path d="M12 3.5l7.5 3V12c0 4.5-3.2 7.4-7.5 8.5-4.3-1.1-7.5-4-7.5-8.5V6.5z"/>',
    "calendar": '<rect x="3.5" y="5" width="17" height="15.5" rx="2"/><path d="M3.5 10h17M8 3v4M16 3v4"/>',
    "save": '<path d="M12 4v10.5M7.5 10l4.5 4.5 4.5-4.5M5 20h14"/>',
    "x": '<path d="M6.5 6.5l11 11M17.5 6.5l-11 11"/>',
    "bell": '<path d="M6 16.5V11a6 6 0 0 1 12 0v5.5l1.5 1.5h-15z"/><path d="M10 20.5a2 2 0 0 0 4 0"/>',
    "repeat": '<path d="M4.5 12A7.5 7.5 0 0 1 17.8 7.3M19.5 4v4h-4"/><path d="M19.5 12A7.5 7.5 0 0 1 6.2 16.7M4.5 20v-4h4"/>',
    "scale": '<path d="M12 4v16M7 20h10M5 8h14"/><path d="M5 8l-2.5 6a3 3 0 0 0 5 0z"/><path d="M19 8l-2.5 6a3 3 0 0 0 5 0z"/>',
    "coins": '<ellipse cx="9" cy="7" rx="5.5" ry="2.5"/><path d="M3.5 7v4c0 1.4 2.5 2.5 5.5 2.5s5.5-1.1 5.5-2.5V7"/>'
             '<path d="M9.5 16.3c.9.1 1.8.2 2.8.2 3 0 5.5-1.1 5.5-2.5v-4"/><path d="M14.5 10.6c2.2.3 3.8 1.2 3.8 2.4"/>',
    "logo": '<path d="M4 18.5V9.5M9.3 18.5v-6M14.7 18.5v-9M20 18.5V5.5"/>',
}


@lru_cache(maxsize=512)
def pixmap(name: str, color: str, size: int = 18, weight: float = 1.8, dpr: float = 2.0) -> QPixmap:
    """Render icon ``name`` in ``color`` at ``size`` logical pixels."""
    body = ICONS.get(name, ICONS["info"])
    svg = _SVG.format(color=_svg_color(color), weight=weight, body=body)
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    px = QPixmap(int(size * dpr), int(size * dpr))
    px.fill(Qt.GlobalColor.transparent)
    painter = QPainter(px)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter, QRectF(0, 0, size * dpr, size * dpr))
    painter.end()
    px.setDevicePixelRatio(dpr)
    return px


def icon(name: str, color: str, selected_color: str | None = None, size: int = 18) -> QIcon:
    """A QIcon; ``selected_color`` tints the Selected/Active state (nav items)."""
    ic = QIcon()
    ic.addPixmap(pixmap(name, color, size), QIcon.Mode.Normal)
    if selected_color:
        ic.addPixmap(pixmap(name, selected_color, size), QIcon.Mode.Selected)
        ic.addPixmap(pixmap(name, selected_color, size), QIcon.Mode.Active)
    return ic


def _svg_color(color: str) -> str:
    """SVG renderers want #rrggbb; tokens may be rgba(...)."""
    if color.startswith("#"):
        return color
    c = QColor(color)
    return c.name() if c.isValid() else "#888888"
