from __future__ import annotations

import ctypes
import os
import threading
import time
from ctypes import wintypes


if os.name == "nt":
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    shell32 = ctypes.WinDLL("shell32", use_last_error=True)
else:
    user32 = None
    shell32 = None


# Windows virtual-key constants.
VK_CODES: dict[str, int] = {
    **{chr(code).lower(): code for code in range(ord("A"), ord("Z") + 1)},
    **{str(number): ord(str(number)) for number in range(10)},
    "[": 0xDB,
    "]": 0xDD,
    ",": 0xBC,
    ".": 0xBE,
    "space": 0x20,
    "shift": 0x10,
    "ctrl": 0x11,
}

INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008
MAPVK_VK_TO_VSC = 0
VK_F10 = 0x79


def is_running_as_admin() -> bool:
    """Return True when this process has an elevated Windows token."""
    if os.name != "nt" or shell32 is None:
        return False
    try:
        return bool(shell32.IsUserAnAdmin())
    except OSError:
        return False


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class INPUT_UNION(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("union",)
    _fields_ = [
        ("type", wintypes.DWORD),
        ("union", INPUT_UNION),
    ]


if os.name == "nt" and user32 is not None:
    user32.MapVirtualKeyW.argtypes = (wintypes.UINT, wintypes.UINT)
    user32.MapVirtualKeyW.restype = wintypes.UINT
    user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
    user32.SendInput.restype = wintypes.UINT
    user32.GetAsyncKeyState.argtypes = (ctypes.c_int,)
    user32.GetAsyncKeyState.restype = ctypes.c_short


class WindowsKeySender:
    def __init__(self) -> None:
        if os.name != "nt" or user32 is None:
            raise RuntimeError("Keyboard injection is supported only on Windows.")
        self._held: set[str] = set()
        self._lock = threading.Lock()

    @staticmethod
    def _scan_code(key: str) -> int:
        try:
            virtual_key = VK_CODES[key.lower()]
        except KeyError as exc:
            raise ValueError(f"Unsupported key: {key}") from exc
        scan = user32.MapVirtualKeyW(virtual_key, MAPVK_VK_TO_VSC)
        if not scan:
            raise OSError(f"Could not resolve scan code for key: {key}")
        return int(scan)

    def _send(self, key: str, key_up: bool) -> None:
        scan = self._scan_code(key)
        flags = KEYEVENTF_SCANCODE | (KEYEVENTF_KEYUP if key_up else 0)
        event = INPUT(
            type=INPUT_KEYBOARD,
            ki=KEYBDINPUT(
                wVk=0,
                wScan=scan,
                dwFlags=flags,
                time=0,
                dwExtraInfo=0,
            ),
        )
        sent = user32.SendInput(1, ctypes.byref(event), ctypes.sizeof(INPUT))
        if sent != 1:
            raise ctypes.WinError(ctypes.get_last_error())

    def key_down(self, key: str) -> None:
        key = key.lower()
        with self._lock:
            if key in self._held:
                return
            self._send(key, key_up=False)
            self._held.add(key)

    def key_up(self, key: str) -> None:
        key = key.lower()
        with self._lock:
            if key not in self._held:
                return
            self._send(key, key_up=True)
            self._held.discard(key)

    def tap(self, key: str, hold_seconds: float = 0.012, gap_seconds: float = 0.012) -> None:
        self.key_down(key)
        time.sleep(hold_seconds)
        self.key_up(key)
        if gap_seconds > 0:
            time.sleep(gap_seconds)

    def release_all(self) -> None:
        with self._lock:
            keys = list(self._held)
        for key in keys:
            try:
                self.key_up(key)
            except OSError:
                pass


def f10_is_pressed() -> bool:
    if os.name != "nt" or user32 is None:
        return False
    return bool(user32.GetAsyncKeyState(VK_F10) & 0x8000)
