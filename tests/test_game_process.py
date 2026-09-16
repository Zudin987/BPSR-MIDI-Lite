from __future__ import annotations

import pytest

import game_process
import player as player_module
from player import MidiPlayer


@pytest.mark.parametrize("name", [
    r"C:\Games\bpsr\BPSR_STEAM.exe",
    r"D:\StarSEA_STEAM.exe",
    "BPSR.exe",
    "starsea.exe",
])
def test_known_game_names(name: str) -> None:
    assert game_process.is_game_executable_name(name)


@pytest.mark.parametrize("name", [
    "discord.exe", "firefox.exe", "BPSR_STEAM.exe.backup", "notbpsr.exe", "",
])
def test_other_windows_are_never_game_targets(name: str) -> None:
    assert not game_process.is_game_executable_name(name)


def test_custom_regional_executable_requires_explicit_setting(monkeypatch) -> None:
    assert not game_process.is_game_executable_name("NewRegion.exe")
    monkeypatch.setenv("BPSR_GAME_EXECUTABLES", "NewRegion.exe, invalid/value.exe")
    assert game_process.is_game_executable_name("newregion.exe")
    assert not game_process.is_game_executable_name("invalid/value.exe")


def test_capture_rejects_wrong_foreground_process(monkeypatch) -> None:
    instance = MidiPlayer()
    instance._focus_guard_enabled = True
    monkeypatch.setattr(player_module, "foreground_process_id", lambda: 12345)
    monkeypatch.setattr(player_module, "is_bpsr_process", lambda _pid: False)
    with pytest.raises(RuntimeError, match="BPSR game window"):
        instance._capture_target_process()
    assert instance._target_process_id is None
    monkeypatch.setattr(player_module, "is_bpsr_process", lambda _pid: True)
    instance._capture_target_process()
    assert instance._target_process_id == 12345
