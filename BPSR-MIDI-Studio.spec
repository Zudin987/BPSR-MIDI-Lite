# Run with: pyinstaller BPSR-MIDI-Studio.spec
#
# Studio is intentionally a one-file build for end users: download the EXE and
# run it directly, like Lite. PyInstaller extracts the bundled AI/audio runtime
# to a temporary folder automatically while the app is running.

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

project = Path(SPECPATH)

basic_pitch_datas = collect_data_files("basic_pitch")
imageio_datas = collect_data_files("imageio_ffmpeg")
soundcard_datas = collect_data_files("soundcard")
drop_datas = collect_data_files("tkinterdnd2")
worker_sources = [(str(p), "studio_band") for p in (project / "studio_band").glob("*.py")]
worker_sources += [(str(project / "studio_band_worker.py"), "."),
                   (str(project / "profiles" / "bpsr_drums.json"), "profiles")]
imageio_binaries = collect_dynamic_libs("imageio_ffmpeg")

a = Analysis(
    [str(project / "studio_launcher.py")],
    pathex=[str(project)],
    binaries=imageio_binaries,
    datas=basic_pitch_datas + imageio_datas + soundcard_datas + drop_datas + worker_sources,
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
        "soundcard",
        "soundcard.mediafoundation",
        "cffi",
        "_cffi_backend",
        "tkinterdnd2",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tensorflow", "torch", "torchaudio", "torchvision", "demucs",
              "transkun", "beat_this", "mt3_infer", "audio_separator", "adtof_pytorch"],
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
