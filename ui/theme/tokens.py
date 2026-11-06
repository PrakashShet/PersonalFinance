"""Colour tokens for the light and dark themes.

Every colour in the UI comes from here - views and widgets refer to a token by
name (``theme.color("text_muted")``) or style themselves through the QSS
template (``ui/resources/styles/theme.qss``, ``$token`` placeholders). Never
hardcode a hex value in a view.

Text tokens meet WCAG AA (>= 4.5:1) on their surface in both modes. The chart
series are the validated categorical palette from the dataviz method (adjacent
CVD separation and normal-vision floors pass in both modes against these exact
surfaces; light-mode aqua/yellow sit below 3:1, so charts always ship a legend
table with names and values).
"""
from __future__ import annotations

LIGHT: dict[str, str] = {
    # surfaces
    "bg": "#F4F5F7",
    "surface": "#FFFFFF",
    "surface_alt": "#F8F9FB",
    "surface_hover": "#F1F3F6",
    "sidebar": "#FFFFFF",
    "border": "#E4E7EC",
    "border_strong": "#D0D5DD",
    # text
    "text": "#101828",
    "text_secondary": "#344054",
    "text_muted": "#667085",
    "text_faint": "#98A2B3",
    # accent (indigo - deliberately not green/red, which mean gain/loss)
    "accent": "#4F46E5",
    "accent_hover": "#4338CA",
    "accent_pressed": "#3730A3",
    "accent_soft": "#EEF2FF",
    "accent_soft_border": "#C7D2FE",
    "accent_text": "#4338CA",
    "on_accent": "#FFFFFF",
    "focus": "#6366F1",
    "selection": "#E0E7FF",
    # status (text colour, soft fill, border)
    "positive": "#067647", "positive_soft": "#ECFDF3", "positive_border": "#ABEFC6",
    "negative": "#D92D20", "negative_soft": "#FEF3F2", "negative_border": "#FECDCA",
    "warning": "#B54708", "warning_soft": "#FFFAEB", "warning_border": "#FEDF89",
    "info": "#175CD3", "info_soft": "#EFF8FF", "info_border": "#B2DDFF",
    "neutral": "#475467", "neutral_soft": "#F2F4F7", "neutral_border": "#E4E7EC",
    # charts
    "chart_grid": "#EAECF0",
    "chart_axis": "#D0D5DD",
    "chart_text": "#667085",
    "series_1": "#2a78d6",
    "series_2": "#eb6834",
    "series_3": "#1baf7a",
    "series_4": "#eda100",
    "series_5": "#e87ba4",
    "series_other": "#98A2B3",
    # misc
    "scroll_handle": "#D0D5DD",
    "scroll_handle_hover": "#98A2B3",
    "tooltip_bg": "#101828",
    "tooltip_text": "#FFFFFF",
    "track": "#EAECF0",
}

DARK: dict[str, str] = {
    "bg": "#0E0F12",
    "surface": "#17181B",
    "surface_alt": "#1C1D21",
    "surface_hover": "#232429",
    "sidebar": "#121316",
    "border": "#2A2C31",
    "border_strong": "#3A3D44",
    "text": "#ECEDEF",
    "text_secondary": "#C5C8CE",
    "text_muted": "#8B909A",
    "text_faint": "#5F646E",
    "accent": "#5558E3",
    "accent_hover": "#6366F1",
    "accent_pressed": "#4F46E5",
    "accent_soft": "rgba(129, 140, 248, 0.14)",
    "accent_soft_border": "rgba(129, 140, 248, 0.38)",
    "accent_text": "#A5B4FC",
    "on_accent": "#FFFFFF",
    "focus": "#818CF8",
    "selection": "rgba(129, 140, 248, 0.24)",
    "positive": "#47CD89", "positive_soft": "rgba(71, 205, 137, 0.12)", "positive_border": "rgba(71, 205, 137, 0.32)",
    "negative": "#F97066", "negative_soft": "rgba(249, 112, 102, 0.12)", "negative_border": "rgba(249, 112, 102, 0.32)",
    "warning": "#FDB022", "warning_soft": "rgba(253, 176, 34, 0.12)", "warning_border": "rgba(253, 176, 34, 0.32)",
    "info": "#53B1FD", "info_soft": "rgba(83, 177, 253, 0.12)", "info_border": "rgba(83, 177, 253, 0.32)",
    "neutral": "#B4B8C0", "neutral_soft": "rgba(255, 255, 255, 0.06)", "neutral_border": "rgba(255, 255, 255, 0.12)",
    "chart_grid": "#25272C",
    "chart_axis": "#3A3D44",
    "chart_text": "#8B909A",
    "series_1": "#3987e5",
    "series_2": "#d95926",
    "series_3": "#199e70",
    "series_4": "#c98500",
    "series_5": "#d55181",
    "series_other": "#5F646E",
    "scroll_handle": "#3A3D44",
    "scroll_handle_hover": "#5F646E",
    "tooltip_bg": "#ECEDEF",
    "tooltip_text": "#0E0F12",
    "track": "#2A2C31",
}

TONES = ("neutral", "accent", "positive", "negative", "warning", "info")
