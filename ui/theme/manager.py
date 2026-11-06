"""ThemeManager - light / dark / follow-system theming for the whole app.

``theme`` (module singleton) is safe to use before ``install()``: it answers
token lookups with the light palette, which is what headless tests see.

Switching theme re-renders the stylesheet from ``theme.qss`` with the other
token set, applies a matching QPalette (dialogs, calendars, menus), tells
Windows to draw a matching title bar, and emits ``changed`` so custom-painted
widgets and charts can repaint.
"""
from __future__ import annotations

import re
from pathlib import Path
from string import Template
from typing import Optional

from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QFontDatabase, QGuiApplication, QPalette

from config.settings import settings
from ui.theme import icons
from ui.theme.tokens import DARK, LIGHT

MODES = ("system", "light", "dark")
_RGBA = re.compile(r"rgba?\(\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)\s*(?:,\s*([\d.]+)\s*)?\)")


def to_qcolor(value: str) -> QColor:
    m = _RGBA.match(value.strip())
    if m:
        r, g, b = (int(float(x)) for x in m.group(1, 2, 3))
        a = float(m.group(4)) if m.group(4) is not None else 1.0
        return QColor(r, g, b, int(round(a * 255)))
    return QColor(value)


class ThemeManager(QObject):
    changed = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self.mode = "system"
        self.is_dark = False
        self.tokens: dict[str, str] = dict(LIGHT)
        self._app = None

    # ------------------------------------------------------------ public
    def color(self, token: str) -> str:
        return self.tokens.get(token, "#ff00ff")

    def qcolor(self, token: str, alpha: Optional[float] = None) -> QColor:
        c = to_qcolor(self.color(token))
        if alpha is not None:
            c.setAlphaF(alpha)
        return c

    def install(self, app, mode: str = "system") -> None:
        """Attach to the QApplication and apply ``mode``."""
        self._app = app
        app.setStyle("Fusion")
        app.setFont(_ui_font())
        hints = app.styleHints()
        try:
            hints.colorSchemeChanged.connect(self._on_system_scheme_changed)
        except (AttributeError, TypeError):
            pass
        self.set_mode(mode)

    def set_mode(self, mode: str) -> None:
        self.mode = mode if mode in MODES else "system"
        self._apply()

    # ------------------------------------------------------------ internals
    def _system_is_dark(self) -> bool:
        try:
            return QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark
        except AttributeError:
            return False

    def _on_system_scheme_changed(self, *_args) -> None:
        if self.mode == "system":
            self._apply()

    def _apply(self) -> None:
        app = self._app
        hints = app.styleHints() if app is not None else None
        if hints is not None and hasattr(hints, "unsetColorScheme"):
            # Let the real system setting through before deciding.
            if self.mode == "system":
                hints.unsetColorScheme()
        dark = (self.mode == "dark") or (self.mode == "system" and self._system_is_dark())
        self.is_dark = dark
        self.tokens = dict(DARK if dark else LIGHT)
        if app is None:
            self.changed.emit()
            return
        if hints is not None and hasattr(hints, "setColorScheme") and self.mode != "system":
            # Native title bar follows the app's choice (Windows 11).
            hints.setColorScheme(Qt.ColorScheme.Dark if dark else Qt.ColorScheme.Light)
        app.setPalette(self._palette())
        app.setStyleSheet(self.stylesheet())
        self.changed.emit()

    def stylesheet(self) -> str:
        template = settings.load_stylesheet()
        values = dict(self.tokens)
        values.update(self._indicator_images())
        return Template(template).safe_substitute(values)

    def _indicator_images(self) -> dict[str, str]:
        """Small PNGs the stylesheet needs (combo arrows, check marks)."""
        out_dir = settings.CACHE_DIR / "theme" / ("dark" if self.is_dark else "light")
        specs = {
            "img_chevron_down": ("chevron_down", self.color("text_muted"), 14),
            "img_chevron_up": ("chevron_up", self.color("text_muted"), 14),
            "img_check": ("check", self.color("on_accent"), 14),
        }
        paths: dict[str, str] = {}
        try:
            out_dir.mkdir(parents=True, exist_ok=True)
            for key, (name, color, size) in specs.items():
                path = out_dir / f"{name}.png"
                if not path.exists():
                    icons.pixmap(name, color, size, 2.2, 1.0).save(str(path), "PNG")
                hi = out_dir / f"{name}@2x.png"
                if not hi.exists():
                    icons.pixmap(name, color, size * 2, 2.2, 1.0).save(str(hi), "PNG")
                paths[key] = _qss_path(path)
        except OSError:
            for key in specs:
                paths[key] = ""
        return paths

    def _palette(self) -> QPalette:
        t = self.qcolor
        p = QPalette()
        roles = {
            QPalette.ColorRole.Window: t("bg"),
            QPalette.ColorRole.WindowText: t("text"),
            QPalette.ColorRole.Base: t("surface"),
            QPalette.ColorRole.AlternateBase: t("surface_alt"),
            QPalette.ColorRole.Text: t("text"),
            QPalette.ColorRole.Button: t("surface"),
            QPalette.ColorRole.ButtonText: t("text"),
            QPalette.ColorRole.Highlight: t("accent"),
            QPalette.ColorRole.HighlightedText: t("on_accent"),
            QPalette.ColorRole.ToolTipBase: t("tooltip_bg"),
            QPalette.ColorRole.ToolTipText: t("tooltip_text"),
            QPalette.ColorRole.PlaceholderText: t("text_faint"),
            QPalette.ColorRole.Link: t("accent_text"),
            QPalette.ColorRole.Mid: t("border"),
            QPalette.ColorRole.Midlight: t("surface_hover"),
            QPalette.ColorRole.Dark: t("border_strong"),
            QPalette.ColorRole.Light: t("surface"),
            QPalette.ColorRole.Shadow: QColor(0, 0, 0, 60),
            QPalette.ColorRole.BrightText: t("negative"),
        }
        for role, color in roles.items():
            p.setColor(role, color)
        for role in (QPalette.ColorRole.Text, QPalette.ColorRole.WindowText,
                     QPalette.ColorRole.ButtonText):
            p.setColor(QPalette.ColorGroup.Disabled, role, t("text_faint"))
        return p


def _qss_path(path: Path) -> str:
    return str(path).replace("\\", "/")


def _ui_font() -> QFont:
    families = set(QFontDatabase.families())
    for name in ("Segoe UI Variable Text", "Segoe UI", "Inter", "Helvetica Neue", "Arial"):
        if name in families:
            f = QFont(name)
            break
    else:
        f = QFont()
    f.setPointSizeF(10.0)
    f.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    return f


theme = ThemeManager()
