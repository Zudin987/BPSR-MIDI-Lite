from __future__ import annotations

import ctypes
import os
import subprocess
import sys
import threading
import time
from pathlib import Path


# Fixed-width Win32 types. Using ctypes.wintypes.LONG outside Windows can have
# the host platform's size, so define the ABI types explicitly.
WORD = ctypes.c_uint16
DWORD = ctypes.c_uint32
LONG = ctypes.c_int32
UINT = ctypes.c_uint32
INT = ctypes.c_int32
ULONG_PTR = ctypes.c_uint64 if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_uint32


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

INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
INPUT_HARDWARE = 2
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008
MAPVK_VK_TO_VSC = 0
VK_F10 = 0x79

SUPPORTED_BACKENDS = ("scan", "pynput", "virtual", "legacy")
BACKEND_NAMES = {
    "scan": "Win32 scan code",
    "pynput": "Pynput compatibility",
    "virtual": "Win32 virtual key",
    "legacy": "Legacy keybd_event",
}


def is_running_as_admin() -> bool:
    """Return True when this process has an elevated Windows token."""
    if os.name != "nt" or shell32 is None:
        return False
    try:
        return bool(shell32.IsUserAnAdmin())
    except OSError:
        return False


def elevation_target() -> tuple[str, str]:
    """Return the executable and Windows command line used for an elevated restart."""
    if getattr(sys, "frozen", False):
        executable = str(Path(sys.executable).resolve())
        arguments = list(sys.argv[1:])
    else:
        executable = str(Path(sys.executable).resolve())
        arguments = [str(Path(sys.argv[0]).resolve()), *sys.argv[1:]]
    return executable, subprocess.list2cmdline(arguments)


def restart_as_administrator() -> None:
    """Launch another copy through the Windows UAC prompt."""
    if os.name != "nt" or shell32 is None:
        raise RuntimeError("Administrator restart is supported only on Windows.")
    if is_running_as_admin():
        return

    executable, parameters = elevation_target()
    result = shell32.ShellExecuteW(
        None,
        "runas",
        executable,
        parameters,
        str(Path.cwd()),
        1,
    )
    result_code = int(result or 0)
    if result_code <= 32:
        if result_code == 5:
            raise PermissionError("The Administrator request was cancelled or denied.")
        raise OSError(f"Windows could not restart the app as Administrator (code {result_code}).")


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", LONG),
        ("dy", LONG),
        ("mouseData", DWORD),
        ("dwFlags", DWORD),
        ("time", DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", WORD),
        ("wScan", WORD),
        ("dwFlags", DWORD),
        ("time", DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", DWORD),
        ("wParamL", WORD),
        ("wParamH", WORD),
    ]


class INPUT_UNION(ctypes.Union):
    # The union must include MOUSEINPUT, not only KEYBDINPUT. On 64-bit
    # Windows this makes sizeof(INPUT) 40 bytes, which SendInput requires.
    _fields_ = [
        ("mi", MOUSEINPUT),
        ("ki", KEYBDINPUT),
        ("hi", HARDWAREINPUT),
    ]


class INPUT(ctypes.Structure):
    _anonymous_ = ("union",)
    _fields_ = [
        ("type", DWORD),
        ("union", INPUT_UNION),
    ]


EXPECTED_INPUT_SIZE = 40 if ctypes.sizeof(ctypes.c_void_p) == 8 else 28


if os.name == "nt" and shell32 is not None:
    shell32.ShellExecuteW.argtypes = (
        ctypes.c_void_p,
        ctypes.c_wchar_p,
        ctypes.c_wchar_p,
        ctypes.c_wchar_p,
        ctypes.c_wchar_p,
        ctypes.c_int,
    )
    shell32.ShellExecuteW.restype = ctypes.c_void_p


if os.name == "nt" and user32 is not None:
    user32.MapVirtualKeyW.argtypes = (UINT, UINT)
    user32.MapVirtualKeyW.restype = UINT
    user32.SendInput.argtypes = (UINT, ctypes.POINTER(INPUT), INT)
    user32.SendInput.restype = UINT
    user32.keybd_event.argtypes = (ctypes.c_ubyte, ctypes.c_ubyte, DWORD, ULONG_PTR)
    user32.keybd_event.restype = None
    user32.GetAsyncKeyState.argtypes = (INT,)
    user32.GetAsyncKeyState.restype = ctypes.c_short


def input_abi_diagnostics() -> str:
    return (
        f"INPUT={ctypes.sizeof(INPUT)} bytes "
        f"(expected {EXPECTED_INPUT_SIZE}), pointer={ctypes.sizeof(ctypes.c_void_p) * 8}-bit"
    )


class WindowsKeySender:
    def __init__(self, backend: str = "scan") -> None:
        if os.name != "nt" or user32 is None:
            raise RuntimeError("Keyboard injection is supported only on Windows.")
        if backend not in SUPPORTED_BACKENDS:
            raise ValueError(f"Unknown input backend: {backend}")
        if ctypes.sizeof(INPUT) != EXPECTED_INPUT_SIZE:
            raise RuntimeError(
                "Internal Win32 INPUT layout is invalid: "
                f"{input_abi_diagnostics()}"
            )

        self.backend = backend
        self._held: set[str] = set()
        self._lock = threading.Lock()
        self._pynput_controller = None
        self._pynput_key = None

        if backend == "pynput":
            try:
                from pynput.keyboard import Controller, Key
            except ImportError as exc:
                raise RuntimeError(
                    "Pynput input method is unavailable in this build."
                ) from exc
            self._pynput_controller = Controller()
            self._pynput_key = Key

    @property
    def description(self) -> str:
        return f"{BACKEND_NAMES[self.backend]}; {input_abi_diagnostics()}"

    @staticmethod
    def _virtual_key(key: str) -> int:
        try:
            return VK_CODES[key.lower()]
        except KeyError as exc:
            raise ValueError(f"Unsupported key: {key}") from exc

    @classmethod
    def _scan_code(cls, key: str) -> int:
        virtual_key = cls._virtual_key(key)
        scan = user32.MapVirtualKeyW(virtual_key, MAPVK_VK_TO_VSC)
        if not scan:
            raise OSError(f"Could not resolve scan code for key: {key}")
        return int(scan)

    @staticmethod
    def _raise_sendinput_error() -> None:
        error = ctypes.get_last_error()
        if error:
            raise ctypes.WinError(error)
        raise OSError(
            "SendInput inserted 0 events. Windows may have blocked input because "
            "the target is running at a higher privilege level."
        )

    def _send_win32(self, key: str, key_up: bool, use_scan_code: bool) -> None:
        virtual_key = self._virtual_key(key)
        scan_code = self._scan_code(key)
        flags = KEYEVENTF_KEYUP if key_up else 0

        if use_scan_code:
            flags |= KEYEVENTF_SCANCODE
            w_vk = 0
            w_scan = scan_code
        else:
            w_vk = virtual_key
            w_scan = 0

        event = INPUT(
            type=INPUT_KEYBOARD,
            ki=KEYBDINPUT(
                wVk=w_vk,
                wScan=w_scan,
                dwFlags=flags,
                time=0,
                dwExtraInfo=0,
            ),
        )

        ctypes.set_last_error(0)
        sent = user32.SendInput(1, ctypes.pointer(event), ctypes.sizeof(INPUT))
        if sent != 1:
            self._raise_sendinput_error()

    def _pynput_value(self, key: str):  # type: ignore[no-untyped-def]
        assert self._pynput_key is not None
        if key == "shift":
            return self._pynput_key.shift
        if key == "ctrl":
            return self._pynput_key.ctrl
        if key == "space":
            return self._pynput_key.space
        return key

    def _send(self, key: str, key_up: bool) -> None:
        if self.backend == "scan":
            self._send_win32(key, key_up, use_scan_code=True)
            return
        if self.backend == "virtual":
            self._send_win32(key, key_up, use_scan_code=False)
            return
        if self.backend == "legacy":
            virtual_key = self._virtual_key(key)
            scan_code = self._scan_code(key)
            flags = KEYEVENTF_KEYUP if key_up else 0
            user32.keybd_event(virtual_key, scan_code, flags, 0)
            return
        if self.backend == "pynput":
            assert self._pynput_controller is not None
            value = self._pynput_value(key)
            if key_up:
                self._pynput_controller.release(value)
            else:
                self._pynput_controller.press(value)
            return
        raise RuntimeError(f"Unsupported backend: {self.backend}")

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

    def tap(
        self,
        key: str,
        hold_seconds: float = 0.012,
        gap_seconds: float = 0.012,
    ) -> None:
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
