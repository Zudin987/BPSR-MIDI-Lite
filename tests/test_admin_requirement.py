from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_windows_build_requires_administrator():
    spec = (ROOT / "BPSR-MIDI-Lite.spec").read_text(encoding="utf-8")
    assert "uac_admin=True" in spec
    assert "uac_admin=False" not in spec


def test_restart_as_administrator_button_was_removed():
    app = (ROOT / "app.py").read_text(encoding="utf-8")
    assert "Restart as Administrator" not in app
    assert "_restart_as_admin" not in app
    assert "restart_as_administrator" not in app


def test_optional_elevation_helper_was_removed():
    win_input = (ROOT / "win_input.py").read_text(encoding="utf-8")
    assert "def restart_as_administrator" not in win_input
    assert "def elevation_target" not in win_input
