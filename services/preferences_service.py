"""User preferences (theme, projection assumptions, backup copy folder ...).

Stored as JSON in ``data/user/preferences.json``. Preferences are conveniences,
not records: a damaged file is set aside (``.bad``) and defaults are used,
rather than stopping the app. ``path=None`` keeps them in memory only (tests,
throwaway contexts) so nothing touches the real file.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Optional

from utils.json_handler import write_text_atomic
from utils.logger import get_logger

log = get_logger(__name__)

DEFAULTS: dict[str, Any] = {
    "theme": "system",                 # system | light | dark
    "backup_mirror_dir": "",           # extra folder that receives a copy of each backup
    "last_account_id": None,           # pre-selected in the transaction dialog
    "budget_year_start": 1,            # month a yearly budget starts: 1 = Jan, 4 = Apr (FY)
    "projection": {
        "current_age": 30,
        "retirement_age": 60,
        "life_expectancy": 85,
        "horizon_years": 30,
        "expected_return": 10.0,       # percent
        "post_retire_return": 7.0,
        "inflation": 6.0,
        "salary_growth": 8.0,
        "expense_growth": 6.0,
    },
}


class PreferencesService:
    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = Path(path) if path else None
        self._data: dict[str, Any] = copy.deepcopy(DEFAULTS)
        self._load()

    def _load(self) -> None:
        if self.path is None or not self.path.exists():
            return
        try:
            stored = json.loads(self.path.read_text(encoding="utf-8-sig"))
            if not isinstance(stored, dict):
                raise ValueError("not an object")
        except (OSError, ValueError) as e:
            log.warning(f"Preferences unreadable ({e}); using defaults")
            try:
                self.path.replace(self.path.with_suffix(".json.bad"))
            except OSError:
                pass
            return
        for key, value in stored.items():
            if isinstance(value, dict) and isinstance(self._data.get(key), dict):
                self._data[key].update(value)
            else:
                self._data[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        value = self._data.get(key, default)
        return copy.deepcopy(value)

    def set(self, key: str, value: Any) -> None:
        if self._data.get(key) == value:
            return
        self._data[key] = copy.deepcopy(value)
        self._save()

    def _save(self) -> None:
        if self.path is None:
            return
        try:
            write_text_atomic(
                self.path, json.dumps(self._data, indent=2, ensure_ascii=False) + "\n")
        except OSError as e:
            log.error(f"Could not save preferences: {e}")
