"""Base dataclass utilities used by all domain models."""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from typing import Any


@dataclass
class BaseModel:
    """Shared serialization helpers."""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_row(cls, row: Any) -> "BaseModel":
        """Build a model from a sqlite3.Row (or any mapping)."""
        if row is None:
            return None  # type: ignore
        cls_fields = {f.name for f in fields(cls)}
        data = {k: row[k] for k in row.keys() if k in cls_fields}
        return cls(**data)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BaseModel":
        cls_fields = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in cls_fields})
