"""DataPersister: atomic, change-only saves; backups and tiered retention."""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from models.account import Account
from repositories.account_repo import AccountRepository
from services.data_persister import (
    STORE_DUMP_ORDER,
    WIPE_GUARD_MIN_ROWS,
    DataPersister,
    SaveRefused,
    backup_store,
    backups_to_keep,
    list_backups,
)


def test_dump_store_data_writes_all_files(temp_db, tmp_path: Path):
    AccountRepository(temp_db).insert(
        Account(name="Savings", account_type="savings", current_balance=1_000.0)
    )
    store_dir = tmp_path / "store"
    DataPersister(temp_db).dump_store_data(store_dir)

    for _, filename in STORE_DUMP_ORDER:
        data = json.loads((store_dir / filename).read_text(encoding="utf-8"))
        assert isinstance(data, list)
    accounts = json.loads((store_dir / "accounts.json").read_text(encoding="utf-8"))
    assert [a["name"] for a in accounts] == ["Savings"]
    # No temp files left behind by the atomic writer.
    assert not list(store_dir.glob(".*.tmp"))


def test_second_save_writes_nothing_when_unchanged(temp_db, tmp_path: Path):
    store_dir = tmp_path / "store"
    persister = DataPersister(temp_db)
    first = persister.dump_store_data(store_dir)
    assert len(first.written) == len(STORE_DUMP_ORDER)

    second = persister.dump_store_data(store_dir)
    assert second.written == []
    assert second.unchanged == len(STORE_DUMP_ORDER)

    AccountRepository(temp_db).insert(Account(name="New", account_type="cash"))
    third = persister.dump_store_data(store_dir)
    assert third.written == ["accounts.json"]


def test_wipe_guard_refuses_to_empty_a_large_file(temp_db, tmp_path: Path):
    store_dir = tmp_path / "store"
    store_dir.mkdir()
    rows = [{"id": i, "name": f"A{i}"} for i in range(WIPE_GUARD_MIN_ROWS)]
    (store_dir / "accounts.json").write_text(json.dumps(rows), encoding="utf-8")

    with pytest.raises(SaveRefused):
        DataPersister(temp_db).dump_store_data(store_dir)
    # The file on disk is untouched.
    assert len(json.loads((store_dir / "accounts.json").read_text(encoding="utf-8"))) == WIPE_GUARD_MIN_ROWS


def test_backup_skips_identical_store(tmp_path: Path):
    store = tmp_path / "store"
    store.mkdir()
    (store / "accounts.json").write_text("[]", encoding="utf-8")
    root = tmp_path / "backups"

    t0 = datetime(2026, 11, 1, 9, 0, 0)
    first = backup_store(store, root, label="startup", now=t0)
    again = backup_store(store, root, label="startup", now=t0 + timedelta(minutes=5))
    assert again == first
    assert len(list_backups(root)) == 1

    (store / "accounts.json").write_text('[{"id": 1}]', encoding="utf-8")
    changed = backup_store(store, root, label="startup", now=t0 + timedelta(minutes=10))
    assert changed != first
    assert len(list_backups(root)) == 2


def test_backup_mirror_copy(tmp_path: Path):
    store = tmp_path / "store"
    store.mkdir()
    (store / "accounts.json").write_text("[]", encoding="utf-8")
    mirror = tmp_path / "onedrive" / "pfm"
    dest = backup_store(store, tmp_path / "backups", label="manual", mirror_root=mirror)
    assert (mirror / dest.name / "accounts.json").exists()


def test_retention_keeps_recent_daily_monthly_yearly_and_forever_labels():
    now = datetime(2026, 11, 6, 12, 0, 0)
    names = []
    # Three backups a day for the last 60 days.
    for d in range(60):
        for h in (9, 13, 20):
            ts = now - timedelta(days=d, hours=12 - h)
            names.append(ts.strftime("%Y%m%d_%H%M%S") + "_startup")
    names.append("20200315_100000_shutdown")          # old: newest of 2020
    names.append("20200101_100000_shutdown")          # older in the same year
    names.append("20210601_100000_pre-migration-v2")   # labelled: forever

    keep = backups_to_keep(names, now)

    assert "20210601_100000_pre-migration-v2" in keep
    assert "20200315_100000_shutdown" in keep          # yearly
    assert "20200101_100000_shutdown" not in keep
    # The newest 30 are kept outright - never fewer than the pre-1.0 policy kept.
    newest = sorted(names, reverse=True)[:30]
    assert set(newest) <= keep
    # One per day survives for 30 days; older days only monthly.
    days_kept = {n[:8] for n in keep if n.startswith("2026")}
    cutoff = (now - timedelta(days=30)).strftime("%Y%m%d")
    assert all(day in days_kept for day in {n[:8] for n in names if n[:8] >= cutoff})
    assert len(keep) < len(names) / 2


def test_retention_ignores_foreign_folders(tmp_path: Path):
    from services.data_persister import prune_backups

    root = tmp_path / "backups"
    (root / "my notes").mkdir(parents=True)
    for i in range(15):
        (root / f"2020{i + 1:02d}01_000000" if i < 12 else root / f"2021010{i - 11}_000000").mkdir()
    prune_backups(root, datetime(2026, 1, 1))
    assert (root / "my notes").exists()
