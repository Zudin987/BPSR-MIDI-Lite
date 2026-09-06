"""Audition exported musical events with Windows' MIDI synthesizer, never game keys."""
from __future__ import annotations

import ctypes
import os
import threading
import time

from .export import CHANNELS, PROGRAMS


def preview_messages(record: dict, parts: set[str]) -> list[tuple[float, int]]:
    events = []
    for part in sorted(parts):
        channel = CHANNELS[part]
        events.append((0.0, 0xC0 | channel | PROGRAMS[part] << 8))
        for event in record["parts"].get(part, []):
            pitch = (record["drum_profile"]["preview_gm"][event["role"]] if part == "drums" else event["pitch"])
            events.append((event["start"], 0x90 | channel | pitch << 8 | event["velocity"] << 16))
            events.append((event["end"], 0x80 | channel | pitch << 8))
    return sorted(events, key=lambda e: (e[0], 0 if e[1] & 0xF0 == 0xC0 else 1 if e[1] & 0xF0 == 0x80 else 2))


class PreviewPlayer:
    def __init__(self):
        self.cancel = threading.Event()
        self.thread = None

    def stop(self):
        self.cancel.set()
        if self.thread and self.thread is not threading.current_thread():
            self.thread.join(timeout=1)

    def play(self, record: dict, parts: set[str], on_error=lambda _: None):
        self.stop()
        if os.name != "nt":
            raise RuntimeError("MIDI audition uses the Windows MIDI synthesizer. Export the MIDI to listen on this platform.")
        events = preview_messages(record, parts)
        self.cancel = threading.Event()
        cancel = self.cancel

        def work():
            winmm = ctypes.WinDLL("winmm")
            handle = ctypes.c_void_p()
            winmm.midiOutOpen.argtypes = [ctypes.POINTER(ctypes.c_void_p), ctypes.c_uint, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_uint]
            winmm.midiOutShortMsg.argtypes = [ctypes.c_void_p, ctypes.c_uint]
            winmm.midiOutReset.argtypes = [ctypes.c_void_p]
            winmm.midiOutClose.argtypes = [ctypes.c_void_p]
            result = winmm.midiOutOpen(ctypes.byref(handle), 0xFFFFFFFF, 0, 0, 0)
            if result:
                on_error("Windows could not open a MIDI synthesizer. You can still export and play the files.")
                return
            try:
                origin = time.monotonic()
                for when, message in events:
                    if cancel.wait(max(0, origin+when-time.monotonic())):
                        return
                    winmm.midiOutShortMsg(handle, message)
            finally:
                winmm.midiOutReset(handle)
                winmm.midiOutClose(handle)
        self.thread = threading.Thread(target=work, daemon=True, name="studio-midi-audition")
        self.thread.start()
