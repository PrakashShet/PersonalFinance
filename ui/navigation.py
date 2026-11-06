"""Cross-page navigation without views importing each other or MainWindow.

MainWindow registers a handler; a view calls ``go("transactions",
account_id=3)`` and the target page's ``show_with(**kwargs)`` receives it.
"""
from __future__ import annotations

from typing import Callable, Optional

_handler: Optional[Callable[..., None]] = None


def register(handler: Callable[..., None]) -> None:
    global _handler
    _handler = handler


def go(page: str, **kwargs) -> None:
    if _handler is not None:
        _handler(page, **kwargs)
