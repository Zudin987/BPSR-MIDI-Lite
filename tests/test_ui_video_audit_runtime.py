from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest


_RUNTIME_AVAILABLE = (
    importlib.util.find_spec("numpy") is not None
    and importlib.util.find_spec("basic_pitch") is not None
)
pytestmark = pytest.mark.skipif(
    os.name != "nt" or not _RUNTIME_AVAILABLE,
    reason="Windows Studio/Tk recording-driven UI contract",
)


def test_recording_driven_ui_smoke() -> None:
    result = subprocess.run(
        [sys.executable, "tests/smoke_studio_video_audit.py"],
        cwd=Path(__file__).resolve().parents[1],
        text=True,
        capture_output=True,
        timeout=90,
        check=False,
    )
    assert result.returncode == 0, (
        f"recording-driven Studio UI smoke failed\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
