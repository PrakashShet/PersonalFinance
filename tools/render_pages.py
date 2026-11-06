"""Render every page of the real app to PNG files - for reviewing UI changes.

Safe by construction: the store is COPIED into a fresh temporary folder first
(PFM_HOME points there), so the real data is never opened for writing. The
copy goes through the real startup path, including any pending format upgrade.

    python tools/render_pages.py                       # data/store, both themes
    python tools/render_pages.py --store <dir> --out shots --theme dark

Runs headless (Qt offscreen platform) using the Windows font folder.
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--store", default=str(ROOT / "data" / "store"))
    ap.add_argument("--out", default=str(ROOT / "shots"))
    ap.add_argument("--theme", choices=("light", "dark", "both"), default="both")
    ap.add_argument("--size", default="1440x900")
    args = ap.parse_args()

    home = Path(tempfile.mkdtemp(prefix="pfm-render-"))
    if Path(args.store).is_dir():
        shutil.copytree(args.store, home / "data" / "store")
    os.environ["PFM_HOME"] = str(home)
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")
    sys.path.insert(0, str(ROOT))
    os.chdir(ROOT)

    from PyQt6.QtWidgets import QApplication

    app = QApplication(sys.argv)

    from config.settings import settings
    from db.connection import db
    from services.app_context import AppContext
    from services.storage import Storage
    from ui.main_window import NAV, MainWindow
    from ui.theme import theme

    assert str(settings.STORE_DIR).startswith(str(home)), "refusing to open real data"
    db.connect(":memory:")
    storage = Storage(db, settings.STORE_DIR, settings.BACKUP_DIR, settings.SEED_DIR,
                      settings.REFERENCE_DIR, settings.SCHEMA_PATH, settings.APP_VERSION)
    storage.open()
    ctx = AppContext.create(db, storage=storage)

    width, height = (int(x) for x in args.size.lower().split("x"))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    modes = ("light", "dark") if args.theme == "both" else (args.theme,)
    theme.install(app, modes[0])
    window = MainWindow(ctx)
    window.resize(width, height)
    window.show()
    for mode in modes:
        theme.set_mode(mode)
        for i, (key, *_rest) in enumerate(NAV):
            window.sidebar.setCurrentRow(i)
            for _ in range(3):
                app.processEvents()
            path = out / f"{mode}_{i}_{key}.png"
            window.grab().save(str(path))
            print(path)
    db.close()
    shutil.rmtree(home, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
