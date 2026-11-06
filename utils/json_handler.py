"""JSON read/write helpers.

Every write goes through :func:`write_text_atomic`: the new content is written
to a temporary file in the same folder, flushed to disk, and then swapped in
with ``os.replace`` - an atomic rename on both Windows and POSIX. A crash or
power cut mid-write leaves the previous file intact instead of a truncated one.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any


def read_json(path: Path) -> Any:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig") as f:
        return json.load(f)


def dumps_records(data: Any) -> str:
    """The one serialisation used for store files (stable, human-readable)."""
    return json.dumps(data, indent=2, default=str, ensure_ascii=False) + "\n"


def write_text_atomic(path: Path, text: str, encoding: str = "utf-8") -> None:
    """Replace ``path`` with ``text`` so readers see either old or new, never half."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    with open(tmp, "w", encoding=encoding, newline="\n") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    # On Windows a reader (antivirus, sync client, an open editor) can hold the
    # target briefly; retry before giving up. The old file is untouched until
    # the replace succeeds.
    last_error: OSError | None = None
    for attempt in range(6):
        try:
            os.replace(tmp, path)
            return
        except PermissionError as e:
            last_error = e
            time.sleep(0.05 * (attempt + 1))
    raise last_error  # type: ignore[misc]


def write_json(path: Path, data: Any, indent: int = 2) -> None:
    text = json.dumps(data, indent=indent, default=str, ensure_ascii=False) + "\n"
    write_text_atomic(path, text)
