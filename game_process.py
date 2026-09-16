"""Conservative Windows process identity checks for MIDI keyboard injection.

The launcher may run under several distribution-specific names. Never infer that
an arbitrary non-launcher foreground window is the game. Process queries are
read-only; failures deliberately prevent input, rather than guessing.
"""
from __future__ import annotations

import ctypes
import ntpath
import os
import re
from ctypes import wintypes

_DEFAULT_NAMES = frozenset({
    "bpsr.exe", "bpsr_steam.exe", "starsea.exe", "starsea_steam.exe",
})
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_NAME_RE = re.compile(r"^[a-zA-Z0-9_.-]+\.exe$", re.ASCII)


def allowed_game_process_names() -> frozenset[str]:
    """Allow documented regional binaries plus explicit, local launcher overrides."""
    custom = os.environ.get("BPSR_GAME_EXECUTABLES", "")
    extra = {
        entry.strip().lower()
        for entry in custom.split(",")
        if _NAME_RE.fullmatch(entry.strip())
    }
    return _DEFAULT_NAMES | extra


def is_game_executable_name(value: str | None) -> bool:
    if not value:
        return False
    return ntpath.basename(value).casefold() in allowed_game_process_names()


def process_executable_name(pid: int | None) -> str | None:
    """Get a process's executable basename using the minimally privileged Win32 API."""
    if os.name != "nt" or pid is None or pid <= 0:
        return None
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.QueryFullProcessImageNameW.argtypes = (
            wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
            ctypes.POINTER(wintypes.DWORD),
        )
        kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
        kernel32.CloseHandle.restype = wintypes.BOOL
        handle = kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return None
        try:
            name = ctypes.create_unicode_buffer(32768)
            capacity = wintypes.DWORD(len(name))
            if not kernel32.QueryFullProcessImageNameW(handle, 0, name, ctypes.byref(capacity)):
                return None
            return ntpath.basename(name.value)
        finally:
            kernel32.CloseHandle(handle)
    except (AttributeError, OSError, ValueError):
        return None


def is_bpsr_process(pid: int | None) -> bool:
    return is_game_executable_name(process_executable_name(pid))
