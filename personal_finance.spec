# PyInstaller spec — Personal Finance Manager
# Run via: pyinstaller --noconfirm --clean personal_finance.spec

from pathlib import Path

block_cipher = None
root = Path(SPECPATH)

datas = [
    (str(root / "data" / "seed"), "data/seed"),
    (str(root / "data" / "reference"), "data/reference"),
    (str(root / "db" / "schema.sql"), "db"),
    (str(root / "ui" / "resources" / "styles"), "ui/resources/styles"),
]

a = Analysis(
    ["main.py"],
    pathex=[str(root)],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "pyqtgraph",
        "PyQt6.QtCore",
        "PyQt6.QtGui",
        "PyQt6.QtWidgets",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="PersonalFinanceManager",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="PersonalFinanceManager",
)
