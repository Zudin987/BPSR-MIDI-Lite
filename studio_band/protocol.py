"""File-based JSON protocol works with windowed EXEs and isolated Python workers."""
from __future__ import annotations

import atexit
import os
import signal
import subprocess
import threading
import time
import uuid
from collections import deque
from pathlib import Path
from typing import Callable

from .progress import ProgressEvent, as_progress_event, emit_progress, format_elapsed
from .storage import atomic_json, read_json

PROTOCOL_VERSION = 1
_children: set[subprocess.Popen] = set()
_children_lock = threading.Lock()


def stop_workers() -> None:
    with _children_lock:
        children = list(_children)
    for process in children:
        try:
            stop_process(process)
        except (OSError, subprocess.SubprocessError):
            pass


atexit.register(stop_workers)


class Cancelled(RuntimeError):
    pass


class StageError(RuntimeError):
    def __init__(self, stage: str, message: str, details: str = "", retryable: bool = True):
        super().__init__(f"{stage}: {message}")
        self.stage, self.message, self.details, self.retryable = stage, message, details, retryable


class RuntimeSetupError(StageError):
    """A dependency/runtime preparation failure that must not become fallback."""

    def __init__(self, runtime: str, message: str, details: str = "", retryable: bool = True):
        super().__init__("Runtime setup", message, details, retryable)
        self.runtime = runtime


def check_cancel(cancel: threading.Event | None) -> None:
    if cancel is not None and cancel.is_set():
        raise Cancelled("Conversion cancelled. Completed analysis remains cached.")


def stop_process(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), timeout=10)
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    process.wait(timeout=10)


def run_process(command: list[str], *, stage: str, cancel=None, progress=None,
                timeout: float = 7200, env: dict | None = None, cwd: Path | None = None,
                progress_path: Path | None = None, stall_warning_after: float = 120) -> str:
    check_cancel(cancel)
    stdout_lines: deque[str] = deque(maxlen=400)
    stderr_lines: deque[str] = deque(maxlen=400)
    activity_lock = threading.Lock()
    last_activity = [time.monotonic()]

    def note_activity() -> None:
        with activity_lock:
            last_activity[0] = time.monotonic()

    def technical_output() -> str:
        with activity_lock:
            stdout = list(stdout_lines)
            stderr = list(stderr_lines)
        sections = []
        if stdout:
            sections.append("[stdout]\n" + "".join(stdout).rstrip())
        if stderr:
            sections.append("[stderr]\n" + "".join(stderr).rstrip())
        return "\n\n".join(sections)

    def standard_output() -> str:
        # Successful callers historically consume stdout (JSON lines from
        # yt-dlp and package rows from ``uv pip freeze``). Keep the labelled,
        # split stdout/stderr rendering exclusively for failure details so
        # diagnostics cannot contaminate machine-readable successful output.
        with activity_lock:
            return "".join(stdout_lines)

    try:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   stdin=subprocess.DEVNULL, text=True, encoding="utf-8", errors="replace",
                                   env=env, cwd=cwd, start_new_session=os.name != "nt",
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except OSError as exc:
        raise StageError(stage, "The worker could not start. Check or repair its runtime in Advanced.", str(exc)) from exc
    with _children_lock:
        _children.add(process)

    def drain(stream, lines: deque[str]) -> None:
        assert stream is not None
        for line in stream:
            with activity_lock:
                lines.append(line[-4000:])
                last_activity[0] = time.monotonic()

    stdout_reader = threading.Thread(target=drain, args=(process.stdout, stdout_lines), daemon=True)
    stderr_reader = threading.Thread(target=drain, args=(process.stderr, stderr_lines), daemon=True)
    stdout_reader.start()
    stderr_reader.start()
    deadline, last_progress, last_progress_event = time.monotonic() + timeout, None, None
    stall_reported_at = None
    try:
        while process.poll() is None:
            check_cancel(cancel)
            if time.monotonic() > deadline:
                raise StageError(stage, "This stage exceeded its time limit. Retry on a shorter song or a faster device.",
                                 technical_output())
            if progress_path is not None and progress is not None:
                try:
                    value = read_json(progress_path)
                    event = as_progress_event(value)
                    signature = tuple(sorted(event.to_dict().items()))
                    if event.message and signature != last_progress:
                        progress(event)
                        last_progress = signature
                        last_progress_event = event
                        note_activity()
                except (OSError, ValueError):
                    pass
            with activity_lock:
                activity_at = last_activity[0]
            if stall_reported_at is not None and activity_at > stall_reported_at:
                stall_reported_at = None
            idle = time.monotonic() - activity_at
            repeat_stall_warning = (
                stall_reported_at is None
                or time.monotonic() - stall_reported_at >= stall_warning_after
            )
            if progress is not None and stall_warning_after > 0 and idle >= stall_warning_after and repeat_stall_warning:
                setup = "setup" in stage.casefold() or "install" in stage.casefold()
                previous = last_progress_event
                operation = (
                    previous.message.rstrip(".\u2026 ") if previous is not None and previous.message
                    else ("Preparing runtime" if setup else "Running component")
                )
                emit_progress(
                    progress,
                    f"{operation} — no new progress report for {format_elapsed(idle)}; "
                    f"the {'setup ' if setup else ''}worker process is still running…",
                    activity="waiting",
                    stage_fraction=previous.stage_fraction if previous is not None else None,
                    indeterminate=True,
                    bytes_done=previous.bytes_done if previous is not None else None,
                    bytes_total=previous.bytes_total if previous is not None else None,
                    last_reported_activity=previous.activity if previous is not None else "",
                )
                stall_reported_at = time.monotonic()
            if cancel is None:
                time.sleep(0.1)
            else:
                cancel.wait(0.1)
        stdout_reader.join(timeout=2)
        stderr_reader.join(timeout=2)
        check_cancel(cancel)
        output = technical_output()
        if process.returncode:
            raise StageError(stage, "The component failed. Retry or repair its runtime in Advanced.", output)
        return standard_output()
    finally:
        if process.poll() is None:
            stop_process(process)
        with _children_lock:
            _children.discard(process)
        stdout_reader.join(timeout=2)
        stderr_reader.join(timeout=2)
        if process.stdout:
            process.stdout.close()
        if process.stderr:
            process.stderr.close()


class WorkerClient:
    def __init__(self, requests: Path, command_for: Callable[[str], list[str]], env: dict | None = None):
        self.requests, self.command_for, self.env = requests, command_for, env

    def call(self, provider: str, operation: str, payload: dict, *, cancel=None, progress=None,
             timeout: float = 7200) -> dict:
        self.requests.mkdir(parents=True, exist_ok=True)
        request_id = uuid.uuid4().hex
        request = self.requests / (request_id + ".request.json")
        response = self.requests / (request_id + ".response.json")
        updates = self.requests / (request_id + ".progress.json")
        atomic_json(request, {"protocol": PROTOCOL_VERSION, "id": request_id,
                              "provider": provider, "operation": operation, "payload": payload})
        failure = None
        try:
            run_process(self.command_for(provider) + [str(request), str(response), str(updates)],
                        stage=operation, cancel=cancel, progress=progress, timeout=timeout,
                        env=self.env, cwd=self.requests, progress_path=updates)
        except StageError as exc:
            failure = exc
        try:
            result = read_json(response)
        except (OSError, ValueError) as exc:
            if failure:
                raise failure
            raise StageError(operation, "The worker did not return a valid result.", str(exc)) from exc
        if result.get("protocol") != PROTOCOL_VERSION or result.get("id") != request_id:
            raise StageError(operation, "The worker returned an incompatible response.")
        if result.get("status") != "ok":
            error = result.get("error", {})
            details = str(error.get("details", ""))
            if failure and failure.details:
                details = (details.rstrip() + "\n\nWorker process output\n---------------------\n" +
                           failure.details).strip()
            raise StageError(operation, error.get("message", "The model could not complete this stage."),
                             details, error.get("retryable", True))
        if failure:
            raise failure
        if not isinstance(result.get("result"), dict):
            raise StageError(operation, "The worker result is malformed.")
        return result["result"]
