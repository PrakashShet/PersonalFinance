"""Storage.open / save: validate before touching anything, migrate with a
backup, fail closed on damaged files."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from config.settings import settings
from db.connection import Database
from services.data_loader import StoreLoadError
from services.data_persister import list_backups
from services.storage import Storage
from services.store_migrations import META_FILE, STORE_VERSION, StoreVersionError
from tests.conftest import SCHEMA_PATH


def _storage(tmp_path: Path) -> tuple[Storage, Database]:
    db = Database()
    db.connect(":memory:")
    s = Storage(db, tmp_path / "store", tmp_path / "backups", settings.SEED_DIR,
                settings.REFERENCE_DIR, SCHEMA_PATH, app_version="test")
    return s, db


def _write(store: Path, name: str, data) -> None:
    store.mkdir(parents=True, exist_ok=True)
    (store / name).write_text(json.dumps(data), encoding="utf-8")


def test_open_fresh_store_creates_files_and_meta(tmp_path: Path):
    s, db = _storage(tmp_path)
    report = s.open()
    assert report.migrated_from is None
    assert (tmp_path / "store" / META_FILE).exists()
    assert (tmp_path / "store" / "accounts.json").read_text(encoding="utf-8").strip() == "[]"
    # Seed categories survive a first run.
    assert db.fetch_one("SELECT COUNT(*) AS c FROM categories")["c"] > 0
    db.close()


def test_corrupted_file_raises_and_nothing_is_written(tmp_path: Path):
    store = tmp_path / "store"
    store.mkdir()
    (store / "transactions.json").write_text('[{"id": 1, "txn_date": "2026-', encoding="utf-8")
    _write(store, "accounts.json", [{"id": 1, "name": "A", "account_type": "cash"}])
    before = {p.name: p.read_bytes() for p in store.iterdir()}

    s, db = _storage(tmp_path)
    with pytest.raises(StoreLoadError) as exc:
        s.open()
    assert exc.value.path.name == "transactions.json"
    assert {p.name: p.read_bytes() for p in store.iterdir()} == before
    assert not s.is_open
    db.close()


@pytest.mark.parametrize("content", ["", "{}", '["x"]'])
def test_truncated_or_wrong_shape_files_are_rejected(tmp_path: Path, content: str):
    store = tmp_path / "store"
    store.mkdir()
    (store / "goals.json").write_text(content, encoding="utf-8")
    s, db = _storage(tmp_path)
    with pytest.raises(StoreLoadError):
        s.open()
    db.close()


def test_unknown_field_is_refused_not_dropped(tmp_path: Path):
    store = tmp_path / "store"
    _write(store, "goals.json", [{"id": 1, "name": "G", "target_amount": 1.0, "colour": "red"}])
    s, db = _storage(tmp_path)
    with pytest.raises(StoreLoadError, match="colour"):
        s.open()
    db.close()


def test_v1_store_is_backed_up_then_migrated(tmp_path: Path):
    store = tmp_path / "store"
    _write(store, "accounts.json", [{"id": 1, "name": "Bank", "account_type": "savings",
                                     "opening_balance": 100.0, "current_balance": 150.0,
                                     "is_active": 1}])
    _write(store, "transactions.json", [])
    s, db = _storage(tmp_path)
    report = s.open()

    assert report.migrated_from == 1
    meta = json.loads((store / META_FILE).read_text(encoding="utf-8"))
    assert meta["store_version"] == STORE_VERSION
    names = [p.name for p in list_backups(tmp_path / "backups")]
    assert any("pre-migration" in n for n in names)
    pre = next(p for p in list_backups(tmp_path / "backups") if "pre-migration" in p.name)
    assert json.loads((pre / "transactions.json").read_text(encoding="utf-8")) == []
    rows = db.fetch_all("SELECT txn_type, amount FROM transactions ORDER BY id")
    assert [(r["txn_type"], r["amount"]) for r in rows] == [("adjustment", 100.0), ("adjustment", 50.0)]
    db.close()


def test_newer_store_version_is_refused(tmp_path: Path):
    store = tmp_path / "store"
    _write(store, META_FILE, {"store_version": STORE_VERSION + 1})
    s, db = _storage(tmp_path)
    with pytest.raises(StoreVersionError):
        s.open()
    db.close()


def test_save_round_trip_and_reload(tmp_path: Path):
    s, db = _storage(tmp_path)
    s.open()
    db.execute("INSERT INTO accounts (name, account_type, current_balance) VALUES ('X', 'cash', 5)")
    db.commit()
    result = s.save()
    # First save also persists the seed categories created on first run.
    assert "accounts.json" in result.written
    assert s.save().written == []
    s.close()
    db.close()

    s2, db2 = _storage(tmp_path)
    s2.open()
    assert db2.fetch_one("SELECT name FROM accounts")["name"] == "X"
    db2.close()


def test_nulls_from_old_databases_take_column_defaults(tmp_path: Path):
    """Old app.db files added cc_* columns without NOT NULL, so real stores hold
    explicit nulls there. They must load (as the default), not crash."""
    store = tmp_path / "store"
    _write(store, "accounts.json", [{"id": 1, "name": "Bank", "account_type": "savings",
                                     "current_balance": 10.0, "opening_balance": 10.0,
                                     "is_active": 1, "cc_credit_limit": None,
                                     "loan_principal": None, "bond_units": None}])
    _write(store, "transactions.json", [])
    s, db = _storage(tmp_path)
    s.open()
    row = db.fetch_one("SELECT cc_credit_limit, loan_principal, bond_units FROM accounts")
    assert (row["cc_credit_limit"], row["loan_principal"], row["bond_units"]) == (0, 0, 0)
    db.close()


def test_failed_load_after_migration_leaves_files_untouched(tmp_path: Path):
    store = tmp_path / "store"
    # A liability with no principal violates NOT NULL (no default): genuine bad data.
    _write(store, "liabilities.json", [{"id": 1, "name": "X", "liability_type": "bnpl",
                                        "principal": None, "outstanding": 5.0}])
    _write(store, "accounts.json", [{"id": 1, "name": "Bank", "account_type": "savings",
                                     "opening_balance": 1.0, "current_balance": 2.0}])
    before = {p.name: p.read_bytes() for p in store.iterdir()}
    s, db = _storage(tmp_path)
    with pytest.raises(StoreLoadError):
        s.open()
    assert {p.name: p.read_bytes() for p in store.iterdir() if p.name in before} == before
    assert not (store / META_FILE).exists()
    db.close()


def test_budgets_survive_save_and_reload(tmp_path: Path):
    from services.app_context import AppContext

    s, db = _storage(tmp_path)
    s.open()
    ctx = AppContext.create(db)
    food = next(cid for cid, name in ctx.expense_categories() if name == "Groceries")
    ctx.budget_service.set_limit(food, "monthly", 8_000, notes="DMart + vegetables")
    ctx.budget_service.set_limit(food, "yearly", 90_000)
    assert "budgets.json" in s.save().written
    s.close()
    db.close()

    rows = json.loads((tmp_path / "store" / "budgets.json").read_text(encoding="utf-8"))
    assert sorted((r["period"], r["amount"]) for r in rows) == [("monthly", 8000.0), ("yearly", 90000.0)]

    s2, db2 = _storage(tmp_path)
    s2.open()
    ctx2 = AppContext.create(db2)
    budgets = {b.period: b for b in ctx2.budget_service.list_all()}
    assert budgets["monthly"].amount == 8000.0
    assert budgets["monthly"].notes == "DMart + vegetables"
    assert budgets["yearly"].category_id == food
    db2.close()


def test_store_without_budgets_file_gets_an_empty_one(tmp_path: Path):
    """An existing (pre-budgets) store opens unchanged and gains budgets.json."""
    store = tmp_path / "store"
    _write(store, "accounts.json", [{"id": 1, "name": "Bank", "account_type": "savings",
                                     "opening_balance": 0.0, "current_balance": 0.0}])
    s, db = _storage(tmp_path)
    s.open()
    assert (store / "budgets.json").read_text(encoding="utf-8").strip() == "[]"
    db.close()


def test_budget_for_a_missing_category_stops_the_load(tmp_path: Path):
    store = tmp_path / "store"
    _write(store, "categories.json", [{"id": 1, "name": "Food", "kind": "expense"}])
    _write(store, "budgets.json", [{"id": 1, "category_id": 99, "period": "monthly",
                                    "amount": 5000.0}])
    s, db = _storage(tmp_path)
    with pytest.raises(StoreLoadError, match="budgets.json"):
        s.open()
    db.close()


def test_a_new_store_is_written_complete_before_the_startup_backup(tmp_path: Path):
    s, db = _storage(tmp_path)
    s.open()
    on_disk = json.loads((tmp_path / "store" / "categories.json").read_text(encoding="utf-8"))
    assert len(on_disk) > 0                      # the seed categories, not "[]"
    [backup] = list_backups(tmp_path / "backups")
    assert json.loads((backup / "categories.json").read_text(encoding="utf-8")) == on_disk
    db.close()


def test_an_empty_categories_file_does_not_wipe_the_categories(tmp_path: Path):
    """The first save never happened (the app was closed a second after its first
    start): categories.json is still "[]". That used to wipe the seed categories
    on every later start - leaving no categories at all, with no way to add any."""
    store = tmp_path / "store"
    _write(store, "categories.json", [])
    _write(store, "accounts.json", [{"id": 1, "name": "Bank", "account_type": "savings",
                                     "opening_balance": 0.0, "current_balance": 0.0}])
    s, db = _storage(tmp_path)
    s.open()
    assert db.fetch_one("SELECT COUNT(*) AS c FROM categories")["c"] > 0
    healed = json.loads((store / "categories.json").read_text(encoding="utf-8"))
    assert len(healed) > 0                       # and written back straight away
    db.close()
