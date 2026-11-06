"""End to end: the real start-up and shutdown path (``main.py``), in a child
process with its own throwaway data folder for every scenario."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from services.data_loader import STORE_LOAD_ORDER

pytestmark = pytest.mark.smoke

RUNNER = Path(__file__).with_name("main_runner.py")


def _start(home: Path, **env) -> tuple[subprocess.Popen, Path]:
    out = home.parent / f"{home.name}-result.json"
    full = {**os.environ, "PFM_HOME": str(home), "E2E_OUT": str(out),
            "QT_QPA_PLATFORM": "offscreen", "PYTHONIOENCODING": "utf-8", **env}
    proc = subprocess.Popen([sys.executable, str(RUNNER)], env=full,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return proc, out


def _run(home: Path, **env) -> dict:
    proc, out = _start(home, **env)
    log, _ = proc.communicate(timeout=60)
    assert out.exists(), log.decode("utf-8", "replace")[-3000:]
    result = json.loads(out.read_text(encoding="utf-8"))
    result["log"] = log.decode("utf-8", "replace")
    return result


def _store(home: Path) -> Path:
    return home / "data" / "store"


def _backups(home: Path) -> list[str]:
    folder = home / "data" / "user" / "backups"
    return sorted(p.name for p in folder.iterdir()) if folder.is_dir() else []


def test_first_start_creates_every_file_and_a_backup(tmp_path):
    home = tmp_path / "home"
    r = _run(home)
    assert r["exit"] == 0 and r["messages"] == [], r
    files = {p.name for p in _store(home).iterdir()}
    assert {f for f, _t in STORE_LOAD_ORDER} | {"_meta.json"} <= files
    assert json.loads((_store(home) / "_meta.json").read_text(encoding="utf-8"))["store_version"] == 2
    assert any(name.endswith("_startup") for name in _backups(home))
    assert not (home / "data" / "app.lock").exists(), "the lock is released on exit"


def test_a_second_copy_is_refused_and_touches_nothing(tmp_path):
    home = tmp_path / "home"
    r = _run(home, E2E_HOLD_LOCK="1")
    assert r["exit"] == 0
    assert any("already open" in m[2] for m in r["messages"]), r["messages"]
    assert not _store(home).exists()


def test_a_damaged_file_stops_the_app_and_is_left_alone(tmp_path):
    home = tmp_path / "home"
    _store(home).mkdir(parents=True)
    damaged = _store(home) / "accounts.json"
    damaged.write_bytes(b'[{"id": 1, "name": "Bank", ')
    r = _run(home)
    assert r["exit"] == 1
    assert any("accounts.json" in m[1] for m in r["messages"]), r["messages"]
    assert damaged.read_bytes() == b'[{"id": 1, "name": "Bank", '
    assert not (_store(home) / "_meta.json").exists()


def test_data_from_a_newer_version_is_refused(tmp_path):
    home = tmp_path / "home"
    _store(home).mkdir(parents=True)
    (_store(home) / "_meta.json").write_text('{"store_version": 99}', encoding="utf-8")
    r = _run(home)
    assert r["exit"] == 1
    assert any(m[0] == "critical" and "99" in m[2] for m in r["messages"]), r["messages"]


def test_old_format_data_is_backed_up_then_upgraded(tmp_path):
    home = tmp_path / "home"
    _store(home).mkdir(parents=True)
    (_store(home) / "accounts.json").write_text(json.dumps([
        {"id": 1, "name": "Bank", "account_type": "savings", "opening_balance": 1000.0,
         "current_balance": 1500.0, "is_active": 1}]), encoding="utf-8")
    (_store(home) / "transactions.json").write_text("[]", encoding="utf-8")
    r = _run(home)
    assert r["exit"] == 0 and r["messages"] == [], r
    assert any("upgraded" in t for t in r["toasts"]), r["toasts"]
    assert any("pre-migration-v2" in name for name in _backups(home))
    txns = json.loads((_store(home) / "transactions.json").read_text(encoding="utf-8"))
    assert round(sum(t["amount"] for t in txns), 2) == 1500.0     # opening + reconciliation


def test_leftover_sqlite_file_is_removed(tmp_path):
    home = tmp_path / "home"
    (home / "data").mkdir(parents=True)
    (home / "data" / "app.db").write_bytes(b"old")
    r = _run(home)
    assert r["exit"] == 0
    assert not (home / "data" / "app.db").exists()


def test_old_beside_the_exe_data_is_imported_once(tmp_path):
    home, legacy = tmp_path / "home", tmp_path / "old_exe_folder" / "data"
    (legacy / "store").mkdir(parents=True)
    (legacy / "store" / "accounts.json").write_text(json.dumps([
        {"id": 1, "name": "Old bank", "account_type": "savings", "opening_balance": 0.0,
         "current_balance": 0.0, "is_active": 1}]), encoding="utf-8")
    r = _run(home, E2E_LEGACY=str(legacy))
    assert r["exit"] == 0
    assert any("new home" in t for t in r["toasts"]), r["toasts"]
    assert "Old bank" in (_store(home) / "accounts.json").read_text(encoding="utf-8")
    assert (legacy / "store" / "accounts.json").exists(), "the old folder is left untouched"


def test_a_crash_loses_nothing_saved_and_the_app_starts_again(tmp_path):
    home = tmp_path / "home"
    proc, _out = _start(home, E2E_ACTION="add_account", E2E_QUIT_MS="60000")
    accounts = _store(home) / "accounts.json"
    deadline = time.time() + 30
    while time.time() < deadline:
        if accounts.exists() and "Added before the crash" in accounts.read_text(encoding="utf-8"):
            break
        time.sleep(0.2)
    else:
        proc.kill()
        pytest.fail("the account was never saved")
    proc.kill()                                     # no shutdown, no cleanup: a crash
    proc.wait(timeout=30)
    assert (home / "data" / "app.lock").exists(), "the crashed copy left its lock behind"

    r = _run(home)                                  # the stale lock must not block a restart
    assert r["exit"] == 0 and r["messages"] == [], r
    saved = json.loads(accounts.read_text(encoding="utf-8"))
    assert [a["current_balance"] for a in saved if a["name"] == "Added before the crash"] == [1234.0]


def test_an_unexpected_error_is_reported_not_a_crash(tmp_path):
    home = tmp_path / "home"
    r = _run(home, E2E_ACTION="raise")
    assert r["exit"] == 0, r["log"][-2000:]                    # the app kept running
    assert any(m[0] == "critical" and "division by zero" in m[2] for m in r["messages"]), r
    log = (home / "logs" / "app.log")
    assert "ZeroDivisionError" in log.read_text(encoding="utf-8")


def test_start_up_opens_one_window_and_paints_it_before_saving(tmp_path):
    """No flicker: no widget may flash up as a window of its own (start-up used to
    show 51), and the window paints before anything saves (a save straight after
    show() left it blank first)."""
    r = _run(tmp_path / "home", E2E_SPY="1")
    assert r["exit"] == 0, r["log"][-2000:]
    assert r["windows"] == ["MainWindow"], r["windows"]
    assert r["saves_before_paint"] == 0
