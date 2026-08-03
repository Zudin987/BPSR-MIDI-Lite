import ctypes

import pytest

import win_input


def test_input_structure_matches_win32_abi():
    expected = 40 if ctypes.sizeof(ctypes.c_void_p) == 8 else 28
    assert ctypes.sizeof(win_input.INPUT) == expected
    assert win_input.EXPECTED_INPUT_SIZE == expected


def test_union_is_large_enough_for_mouseinput():
    assert ctypes.sizeof(win_input.INPUT_UNION) >= ctypes.sizeof(win_input.MOUSEINPUT)
    assert ctypes.sizeof(win_input.INPUT_UNION) >= ctypes.sizeof(win_input.KEYBDINPUT)


def test_supported_backends_are_stable():
    assert set(win_input.SUPPORTED_BACKENDS) == {"scan", "pynput", "virtual", "legacy"}


def test_sender_rejects_unknown_backend_before_use(monkeypatch):
    if win_input.os.name != "nt":
        with pytest.raises(RuntimeError):
            win_input.WindowsKeySender("unknown")
