# Run with: pyinstaller BPSR-MIDI-Studio.spec
#
# Studio intentionally uses an onedir portable build. Basic Pitch + ONNX +
# scientific Python are much more reliable and launch faster this way than
# unpacking a very large one-file executable every run.

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

project = Path(SPECPATH)

basic_pitch_datas = collect_data_files("basic_pitch")
imageio_datas = collect_data_files("imageio_ffmpeg")
imageio_binaries = collect_dynamic_libs("imageio_ffmpeg")

a = Analysis(
    [str(project / "studio_launcher.py")],
    pathex=[str(project)],
    binaries=imageio_binaries,
    datas=basic_pitch_datas + imageio_datas,
    hiddenimports=[
        "pynput.keyboard._win32",
        "pynput._util.win32",
        "basic_pitch.inference",
        "basic_pitch.note_creation",
        "basic_pitch.constants",
        "basic_pitch.commandline_printing",
        "imageio_ffmpeg",
        "onnxruntime",
        "onnxruntime.capi._pybind_state",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tensorflow", "torch"],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="BPSR-MIDI-Studio",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    uac_admin=True,
    icon=str(project / "assets" / "app.ico"),
    version=str(project / "studio_version_info.txt"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="BPSR-MIDI-Studio",
)
