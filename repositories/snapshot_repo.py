from __future__ import annotations

from typing import Optional

from models.snapshot import NetWorthSnapshot
from repositories.base_repo import BaseRepository


class SnapshotRepository(BaseRepository[NetWorthSnapshot]):
    table_name = "net_worth_snapshots"
    model_class = NetWorthSnapshot

    def list_ordered(self) -> list[NetWorthSnapshot]:
        return self.list_all("1 = 1 ORDER BY snapshot_date")

    def upsert(
        self,
        snapshot_date: str,
        total_assets: float,
        total_liabilities: float,
        net_worth: float,
        breakdown_json: Optional[str],
    ) -> None:
        """One row per day; a later snapshot the same day replaces the earlier."""
        self.db.execute(
            """
            INSERT INTO net_worth_snapshots
              (snapshot_date, total_assets, total_liabilities, net_worth, breakdown_json)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(snapshot_date) DO UPDATE SET
              total_assets = excluded.total_assets,
              total_liabilities = excluded.total_liabilities,
              net_worth = excluded.net_worth,
              breakdown_json = excluded.breakdown_json
            """,
            (snapshot_date, total_assets, total_liabilities, net_worth, breakdown_json),
        )
        self.db.commit()

    def on_or_before(self, snapshot_date: str) -> Optional[NetWorthSnapshot]:
        row = self.db.fetch_one(
            "SELECT * FROM net_worth_snapshots WHERE snapshot_date <= ? "
            "ORDER BY snapshot_date DESC LIMIT 1",
            (snapshot_date,),
        )
        return NetWorthSnapshot.from_row(row) if row else None
