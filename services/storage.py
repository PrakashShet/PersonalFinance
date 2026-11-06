"""Storage - the one place that opens, saves and backs up the user's data.

Lifecycle::

    storage = Storage(db, store_dir, backup_dir, seed_dir, reference_dir, schema_path)
    report  = storage.open()     # validate -> (backup + migrate) -> load -> backup
    storage.save()               # after edits; writes only changed files, atomically
    storage.close()              # final save + shutdown backup

``open`` reads and validates *every* store file before touching anything. If a
file is damaged it raises :class:`StoreLoadError` and nothing is written - the
app shows the user which file and where the newest backup is, and quits.

No Qt here: timers and dialogs live in the UI layer (``ui/autosave.py``,
``main.py``).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Callable, Optional

from db.connection import Database
from db.migrate import run_migrations
from services.data_loader import DataLoader, StoreLoadError, read_store
from services.data_persister import (
    DataPersister,
    SaveResult,
    backup_store,
    latest_backup,
    list_backups,
)
from services.store_migrations import (
    META_FILE,
    STORE_VERSION,
    StoreVersionError,
    migrate,
    read_meta,
    write_meta,
)
from utils.json_handler import dumps_records, write_text_atomic
from utils.logger import get_logger

log = get_logger(__name__)

__all__ = ["Storage", "OpenReport", "StoreLoadError", "StoreVersionError"]


@dataclass
class OpenReport:
    store_version: int
    migrated_from: Optional[int] = None
    migration_notes: list[str] = field(default_factory=list)
    startup_backup: Optional[Path] = None


class Storage:
    def __init__(
        self,
        db: Database,
        store_dir: Path,
        backup_dir: Path,
        seed_dir: Path,
        reference_dir: Path,
        schema_path: Path,
        app_version: str = "",
        mirror_dir: Callable[[], Optional[str]] | None = None,
    ) -> None:
        self.db = db
        self.store_dir = Path(store_dir)
        self.backup_dir = Path(backup_dir)
        self.seed_dir = Path(seed_dir)
        self.reference_dir = Path(reference_dir)
        self.schema_path = Path(schema_path)
        self.app_version = app_version
        self._mirror_dir = mirror_dir or (lambda: None)
        self.last_saved_at: Optional[datetime] = None
        self.last_error: Optional[str] = None
        self.is_open = False

    # ------------------------------------------------------------------ open
    def open(self) -> OpenReport:
        self.store_dir.mkdir(parents=True, exist_ok=True)
        tables = read_store(self.store_dir)            # raises StoreLoadError
        meta = read_meta(self.store_dir)               # raises StoreLoadError
        version = int(meta["store_version"])
        if version > STORE_VERSION:
            raise StoreVersionError(version, STORE_VERSION)

        report = OpenReport(store_version=STORE_VERSION)
        if version < STORE_VERSION:
            backup_store(self.store_dir, self.backup_dir,
                         label=f"pre-migration-v{STORE_VERSION}", mirror_root=self._mirror())
            report.migrated_from = version
            report.migration_notes = migrate(tables, version, date.today())

        # Load first: migrated data is written back only once it has proven
        # it loads, so a failed upgrade leaves the files exactly as they were.
        self.db.apply_schema(self.schema_path)
        run_migrations(self.db)
        loader = DataLoader(self.db)
        loader.load_seed_data(self.seed_dir)
        loader.load_store_data(self.store_dir, data=tables)
        loader.load_reference_data(self.reference_dir)

        if report.migrated_from is not None:
            for filename, rows in tables.items():
                if rows is not None:
                    write_text_atomic(self.store_dir / filename, dumps_records(rows))
            write_meta(self.store_dir, STORE_VERSION, self.app_version)
            log.info(f"Store migrated v{version} -> v{STORE_VERSION}")
            for note in report.migration_notes:
                log.info(f"  migration: {note}")
        elif meta.get("_missing"):
            write_meta(self.store_dir, STORE_VERSION, self.app_version)
        self.is_open = True

        # A new store (or one whose first save never happened) has rows only in
        # memory, e.g. the seed categories. Write them now, so the files and the
        # startup backup are complete even if the app is closed a second later.
        if any(rows is None for rows in tables.values()) or not tables.get("categories.json"):
            self.save()

        # The store just validated and loaded: that's a known-good backup.
        report.startup_backup = self.backup("startup")
        return report

    # ------------------------------------------------------------------ save
    def save(self, before: Callable[[], None] | None = None) -> SaveResult:
        """Persist SQLite to the store. ``before`` runs first (e.g. the daily
        net-worth snapshot). Raises on failure; records the error for the UI."""
        if not self.is_open:
            raise RuntimeError("Storage is not open")
        try:
            if before is not None:
                before()
            result = DataPersister(self.db).dump_store_data(self.store_dir)
        except Exception as e:
            self.last_error = str(e)
            log.exception("Save failed")
            raise
        self.last_error = None
        self.last_saved_at = datetime.now()
        return result

    def close(self, before: Callable[[], None] | None = None) -> None:
        if not self.is_open:
            return
        try:
            self.save(before)
        finally:
            self.backup("shutdown")
            self.is_open = False

    # --------------------------------------------------------------- backups
    def backup(self, label: str = "manual") -> Optional[Path]:
        try:
            return backup_store(self.store_dir, self.backup_dir, label=label,
                                mirror_root=self._mirror())
        except OSError as e:
            log.error(f"Backup ({label}) failed: {e}")
            return None

    def latest_backup(self) -> Optional[Path]:
        return latest_backup(self.backup_dir)

    def backup_count(self) -> int:
        return len(list_backups(self.backup_dir))

    def _mirror(self) -> Optional[Path]:
        value = self._mirror_dir()
        return Path(value) if value else None

    @property
    def meta_path(self) -> Path:
        return self.store_dir / META_FILE
