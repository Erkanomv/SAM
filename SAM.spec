# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_all, collect_submodules

webview_datas, webview_binaries, webview_hidden = collect_all("webview")
keyring_datas, keyring_binaries, keyring_hidden = collect_all("keyring")

datas = webview_datas + keyring_datas + [
    ("steam_tracker/web", "steam_tracker/web"),
]
binaries = webview_binaries + keyring_binaries
hiddenimports = (
    webview_hidden
    + keyring_hidden
    + collect_submodules("keyring.backends")
    + collect_submodules("clr_loader")
    + collect_submodules("pythonnet")
    + [
        "webview.platforms.edgechromium",
        "webview.platforms.winforms",
        "win32ctypes",
    ]
)

a = Analysis(
    ["app.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="SAM",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    icon="assets/sam.ico",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="SAM",
)
