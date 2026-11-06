"""CSV read/write helpers."""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Any


def read_csv(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        return [
            {k: _coerce(v) for k, v in row.items()}
            for row in reader
        ]


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str] | None = None) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = fieldnames or list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _coerce(v: Any) -> Any:
    """Best-effort string -> number coercion for CSV cells."""
    if v is None or v == "":
        return None
    try:
        if "." in v:
            return float(v)
        return int(v)
    except (ValueError, TypeError):
        return v
