"""Roundtrip test: load JSON -> SQLite -> dump JSON -> compare."""
from __future__ import annotations

import json
from pathlib import Path

from db.connection import Database
from services.data_loader import DataLoader
from services.data_persister import DataPersister


def test_roundtrip_accounts(temp_db: Database, tmp_path: Path):
    store = tmp_path / "store"
    store.mkdir()
    accounts = [
        {"id": 1, "name": "HDFC", "account_type": "savings", "current_balance": 50000},
        {"id": 2, "name": "ICICI", "account_type": "salary",  "current_balance": 75000},
    ]
    (store / "accounts.json").write_text(json.dumps(accounts), encoding="utf-8")
    # Other store files needed by loader
    for fn in ["categories.json", "income_sources.json", "holdings.json",
               "liabilities.json", "goals.json", "goal_holdings.json",
               "transactions.json", "holding_valuations.json",
               "net_worth_snapshots.json", "reminders.json"]:
        (store / fn).write_text("[]", encoding="utf-8")

    DataLoader(temp_db).load_store_data(store)
    rows = temp_db.fetch_all("SELECT * FROM accounts ORDER BY id")
    assert len(rows) == 2
    assert rows[0]["name"] == "HDFC"
    assert rows[1]["current_balance"] == 75000

    out = tmp_path / "out"
    out.mkdir()
    DataPersister(temp_db).dump_store_data(out, make_backup=False)
    dumped = json.loads((out / "accounts.json").read_text(encoding="utf-8"))
    assert len(dumped) == 2
    assert dumped[0]["name"] == "HDFC"
