"""Tests for DataPersister: dumping tables to JSON, backups, and pruning."""
from __future__ import annotations

import json
from pathlib import Path

from models.account import Account
from repositories.account_repo import AccountRepository
from services.data_persister import STORE_DUMP_ORDER, DataPersister


def test_dump_store_data_writes_all_files(temp_db, tmp_path: Path):
    AccountRepository(temp_db).insert(
        Account(name="Savings", account_type="savings", current_balance=1_000.0)
    )

    store_dir = tmp_path / "store"
    persister = DataPersister(temp_db)
    persister.dump_store_data(store_dir, make_backup=False)

    for _, filename in STORE_DUMP_ORDER:
        out_path = store_dir / filename
        assert out_path.exists()
        data = json.loads(out_path.read_text(encoding="utf-8"))
        assert isinstance(data, list)

    accounts = json.loads((store_dir / "accounts.json").read_text(encoding="utf-8"))
    assert len(accounts) == 1
    assert accounts[0]["name"] == "Savings"


def test_dump_store_data_creates_backup_when_store_nonempty(temp_db, tmp_path: Path):
    store_dir = tmp_path / "store"
    persister = DataPersister(temp_db)

    # First dump: store dir doesn't exist yet, so no backup is made.
    persister.dump_store_data(store_dir, make_backup=True)
    backups_root = store_dir.parent / "user" / "backups"
    assert not backups_root.exists() or not list(backups_root.iterdir())

    # Second dump: store dir is now non-empty, so a backup snapshot is taken.
    persister.dump_store_data(store_dir, make_backup=True)
    assert backups_root.exists()
    snapshots = [p for p in backups_root.iterdir() if p.is_dir()]
    assert len(snapshots) == 1


def test_prune_backups_retains_only_keep_count(tmp_path: Path):
    backups_root = tmp_path / "backups"
    backups_root.mkdir()
    for ts in ["20260101_000000", "20260102_000000", "20260103_000000"]:
        (backups_root / ts).mkdir()

    DataPersister._prune_backups(backups_root, keep=2)

    remaining = sorted(p.name for p in backups_root.iterdir())
    assert remaining == ["20260102_000000", "20260103_000000"]
