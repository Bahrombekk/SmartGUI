# -*- mode: python ; coding: utf-8 -*-
# SafeZone (SmartGUI) — PyInstaller build.
# Yig'ish: build.bat  (yoki: venv\Scripts\python.exe -m PyInstaller SmartGUI.spec --noconfirm)
#
# Natija: dist\SafeZone\SafeZone.exe (onedir). settings.json, smartgui.db, logs\,
# violations\ exe yonida yaratiladi. settings.json ATAYLAB bundle'ga qo'shilmaydi
# (ichida token/parollar bor) — faqat settings.example.json qo'shiladi.

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

datas = [
    ("images", "images"),
    ("app/ui/styles/qss", "app/ui/styles/qss"),
    ("app/models", "app/models"),
    ("settings.example.json", "."),
]
datas += collect_data_files("ultralytics")   # cfg/*.yaml, trackers
datas += collect_data_files("cv2")           # haarcascades

hiddenimports = collect_submodules("ultralytics") + collect_submodules("app")

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "pytest", "IPython", "notebook", "jupyter"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="SafeZone",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon="images/app.ico",
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="SafeZone",
)
