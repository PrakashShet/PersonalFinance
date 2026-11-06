"""Generic CRUD repository. All entity repos inherit from this."""
from __future__ import annotations

from typing import Any, Generic, Optional, TypeVar

from db.connection import Database

T = TypeVar("T")


class BaseRepository(Generic[T]):
    """Subclasses set `table_name` and `model_class`."""

    table_name: str = ""
    model_class: type = None  # type: ignore

    def __init__(self, db: Database) -> None:
        self.db = db

    # ---- Read ------------------------------------------------------------
    def get_by_id(self, id_: int) -> Optional[T]:
        row = self.db.fetch_one(f"SELECT * FROM {self.table_name} WHERE id = ?", (id_,))
        return self.model_class.from_row(row) if row else None

    def list_all(self, where: str = "", params: tuple = ()) -> list[T]:
        sql = f"SELECT * FROM {self.table_name}"
        if where:
            sql += f" WHERE {where}"
        rows = self.db.fetch_all(sql, params)
        return [self.model_class.from_row(r) for r in rows]

    def count(self, where: str = "", params: tuple = ()) -> int:
        sql = f"SELECT COUNT(*) AS c FROM {self.table_name}"
        if where:
            sql += f" WHERE {where}"
        row = self.db.fetch_one(sql, params)
        return row["c"] if row else 0

    # ---- Write -----------------------------------------------------------
    def insert(self, entity: Any) -> int:
        data = entity.to_dict()
        data.pop("id", None)
        # Drop None values to let DB defaults take over
        data = {k: v for k, v in data.items() if v is not None}
        cols = ", ".join(data.keys())
        placeholders = ", ".join(["?"] * len(data))
        sql = f"INSERT INTO {self.table_name} ({cols}) VALUES ({placeholders})"
        cur = self.db.execute(sql, tuple(data.values()))
        self.db.commit()
        return cur.lastrowid

    def update(self, entity: Any) -> None:
        data = entity.to_dict()
        id_ = data.pop("id")
        if id_ is None:
            raise ValueError("Cannot update entity without id")
        set_clause = ", ".join([f"{k} = ?" for k in data.keys()])
        sql = f"UPDATE {self.table_name} SET {set_clause} WHERE id = ?"
        self.db.execute(sql, (*data.values(), id_))
        self.db.commit()

    def delete(self, id_: int) -> None:
        self.db.execute(f"DELETE FROM {self.table_name} WHERE id = ?", (id_,))
        self.db.commit()

    def bulk_insert(self, entities: list[Any]) -> None:
        if not entities:
            return
        for e in entities:
            self.insert(e)
