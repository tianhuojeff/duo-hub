from pathlib import Path

from PyInstaller.utils.hooks import collect_all


project_root = Path.cwd()
webview_datas, webview_binaries, webview_hiddenimports = collect_all("webview")

a = Analysis(
    [str(project_root / "duo_hub_desktop.py")],
    pathex=[str(project_root)],
    binaries=webview_binaries,
    datas=[
        (str(project_root / "web"), "web"),
        (str(project_root / "config.json"), "."),
        (str(project_root / "VERSION"), "."),
    ] + webview_datas,
    hiddenimports=webview_hiddenimports + ["webview.platforms.edgechromium"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="DuoHub",
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
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="DuoHub",
)

