# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec для YTrayPlayer.
Собирает один exe. mpv и yt-dlp кладутся РЯДОМ в bin/ (см. make_dist.bat).
"""
import sys
from pathlib import Path

block_cipher = None

project_dir = Path(SPECPATH).resolve()
assets_dir = project_dir / "assets"
locales_dir = project_dir / "locales"

# Что пакуем внутрь exe как data-файлы
datas = []
if assets_dir.exists():
    for f in assets_dir.iterdir():
        if f.is_file():
            datas.append((str(f), "assets"))
if locales_dir.exists():
    for f in locales_dir.iterdir():
        if f.is_file():
            datas.append((str(f), "locales"))

# Скрытые импорты — то, что PyInstaller иногда не находит сам
hiddenimports = [
    "pystray._win32",
    "win11toast",
    "PIL._tkinter_finder",  # на всякий случай
    "PySide6.QtCore",
    "PySide6.QtGui",
    "PySide6.QtWidgets",
]

# Исключаем лишнее, чтобы уменьшить размер exe
excludes = [
    "tkinter",
    "matplotlib",
    "numpy",
    "pandas",
    "scipy",
    "PyQt5",
    "PyQt6",
    "IPython",
    "jupyter",
    "notebook",
    "pytest",
    "setuptools",
    "pip",
    "wheel",
]

a = Analysis(
    ["main.py"],
    pathex=[str(project_dir)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="YTrayPlayer",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,             # UPX выключен — антивирусы на него ругаются
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,         # без чёрного окна консоли
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(assets_dir / "icon.ico") if (assets_dir / "icon.ico").exists() else None,
)