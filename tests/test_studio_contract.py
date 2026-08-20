from pathlib import Path


def test_lite_build_target_remains_studio_free() -> None:
    launcher = Path("modern_launcher.py").read_text(encoding="utf-8")
    spec = Path("BPSR-MIDI-Lite.spec").read_text(encoding="utf-8")

    assert "studio_" not in launcher
    assert "studio_" not in spec
    assert "studio_launcher.py" not in spec


def test_studio_is_a_separate_launcher_and_build_target() -> None:
    launcher = Path("studio_launcher.py").read_text(encoding="utf-8")
    spec = Path("BPSR-MIDI-Studio.spec").read_text(encoding="utf-8")

    assert "install_modern_ui(app)" in launcher
    assert "install_online_integration(app)" in launcher
    assert "install_studio_integration(app)" in launcher
    assert "studio_launcher.py" in spec
    assert 'name="BPSR-MIDI-Studio"' in spec


def test_studio_youtube_flow_is_search_click_convert_play() -> None:
    ui = Path("studio_ui.py").read_text(encoding="utf-8")
    backend = Path("studio_youtube.py").read_text(encoding="utf-8")

    assert 'text="YouTube"' in ui
    assert 'text="Search"' in ui
    assert 'text="Save MIDI"' in ui
    assert '"<<TreeviewSelect>>"' in ui
    assert "convert_result_to_midi" in ui
    assert "app._schedule_analysis(20)" in ui
    assert "TOP_RESULTS = 3" in backend
    assert "ytsearch{count}" in backend
    assert "--extract-audio" in backend
    assert '"wav"' in backend


def test_studio_provides_current_youtube_js_runtime_without_user_setup() -> None:
    backend = Path("studio_youtube.py").read_text(encoding="utf-8")

    assert "denoland/deno/releases/latest" in backend
    assert "DENO_SUM_URL" in backend
    assert "_expected_deno_sha256" in backend
    assert "--js-runtimes" in backend
    assert 'f"deno:{deno}"' in backend


def test_studio_never_requests_youtube_login_or_browser_cookies() -> None:
    backend = Path("studio_youtube.py").read_text(encoding="utf-8")

    forbidden = (
        "--cookies",
        "--cookies-from-browser",
        "username=",
        "password=",
        "--username",
        "--password",
    )
    assert all(term not in backend for term in forbidden)


def test_studio_audio_is_removed_after_transcription() -> None:
    backend = Path("studio_youtube.py").read_text(encoding="utf-8")
    assert "shutil.rmtree(work_dir, ignore_errors=True)" in backend
    assert "save_midi_to_local" in backend
