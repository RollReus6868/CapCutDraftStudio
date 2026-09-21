# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — chạy được trên cả Windows và macOS.

* Windows : một file .exe duy nhất, không hiện cửa sổ console.
* macOS   : thư mục .app (onedir + BUNDLE) để khởi động nhanh và ký được.

Thư mục `bin/` (nếu có) được gói kèm — workflow CI tải ffmpeg vào đó để
người dùng Windows không phải tự cài gì thêm.
"""
import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

APP_NAME = "CapCut Draft Studio"
BUNDLE_ID = "com.leo.capcutdraftstudio"
VERSION = "0.4.1"

ROOT = Path(SPECPATH)
IS_MAC = sys.platform == "darwin"
IS_WIN = os.name == "nt"

# ---------------------------------------------------------------- dữ liệu --
datas = []
assets = ROOT / "assets"
if assets.is_dir():
    datas.append((str(assets), "assets"))

# ffmpeg/ffprobe đi kèm (nếu có) -> nằm cạnh app khi chạy
bin_dir = ROOT / "bin"
if bin_dir.is_dir():
    for f in sorted(bin_dir.iterdir()):
        if f.is_file():
            datas.append((str(f), "bin"))

# pycapcut đi kèm vài file JSON mẫu (draft_meta_info.json,
# draft_content_template.json) nằm ngay trong package — đây là DATA FILE,
# PyInstaller không tự phát hiện qua import nên phải gom thủ công, nếu không
# lúc chạy bản đóng gói sẽ báo FileNotFoundError khi tạo draft.
datas += collect_data_files("pycapcut")

# pymediainfo đi kèm thư viện MediaInfo (MediaInfo.dll / libmediainfo.dylib)
# nằm trong package — không gom thì bản đóng gói đọc không ra thời lượng file.
datas += collect_data_files("pymediainfo")
binaries_extra = collect_dynamic_libs("pymediainfo")

hiddenimports = [
    "tkinter", "tkinter.ttk", "tkinter.filedialog", "tkinter.messagebox",
    "tkinter.simpledialog", "tkinter.scrolledtext", "tkinter.font",
    "openpyxl", "pymediainfo", "pycapcut",
    "capcut_draft_studio.render", "capcut_draft_studio.updater",
    "capcut_draft_studio.capcut_export",
    "capcut_draft_studio.ui.app", "capcut_draft_studio.ui.pages",
    "capcut_draft_studio.ui.theme", "capcut_draft_studio.ui.widgets",
]
if IS_WIN:
    # chỉ dùng cho tính năng "nhờ CapCut tự export"
    hiddenimports += ["uiautomation", "pycapcut.jianying_controller", "comtypes"]

excludes = [
    "matplotlib", "numpy", "scipy", "pandas", "pytest", "IPython",
    "PyQt5", "PySide2", "PySide6", "notebook", "sphinx",
]

a = Analysis(
    ["launcher.py"],
    pathex=[str(ROOT)],
    binaries=binaries_extra,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
)

pyz = PYZ(a.pure)

ico = assets / "icon.ico"
icns = assets / "icon.icns"
png = assets / "icon.png"
if IS_MAC:
    icon = icns if icns.is_file() else (png if png.is_file() else None)
else:
    icon = ico if ico.is_file() else None
version_file = ROOT / "version_info.txt"

common = dict(
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,                  # UPX hay bị diệt virus báo nhầm
    upx_exclude=[],
    console=False,              # không hiện cửa sổ đen
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(icon) if icon else None,
)

if IS_MAC:
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, runtime_tmpdir=None, **common)
    coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name=APP_NAME)
    app = BUNDLE(
        coll,
        name=f"{APP_NAME}.app",
        icon=str(icon) if icon else None,
        bundle_identifier=BUNDLE_ID,
        version=VERSION,
        info_plist={
            "CFBundleName": APP_NAME,
            "CFBundleDisplayName": APP_NAME,
            "CFBundleShortVersionString": VERSION,
            "CFBundleVersion": VERSION,
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "11.0",
        },
    )
else:
    exe = EXE(
        pyz, a.scripts, a.binaries, a.datas, [],
        runtime_tmpdir=None,
        version=str(version_file) if version_file.is_file() else None,
        **common,
    )
