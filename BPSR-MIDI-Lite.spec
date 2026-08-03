# Run with: pyinstaller BPSR-MIDI-Lite.spec
from pathlib import Path

project = Path(SPECPATH)

a = Analysis(
    [str(project / "app.py")],
    pathex=[str(project)],
    binaries=[],
    datas=[],
    hiddenimports=[],
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
    a.binaries,
    a.datas,
    [],
    name="BPSR-MIDI-Lite",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon=str(project / "assets" / "app.ico"),
    version=str(project / "version_info.txt"),
)
