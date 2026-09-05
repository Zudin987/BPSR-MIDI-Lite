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
        self.stage, self.details, self.retryable = stage, details, retryable


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
                progress_path: Path | None = None) -> str:
    check_cancel(cancel)
    lines: deque[str] = deque(maxlen=120)
    try:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   stdin=subprocess.DEVNULL, text=True, encoding="utf-8", errors="replace",
                                   env=env, cwd=cwd, start_new_session=os.name != "nt",
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except OSError as exc:
        raise StageError(stage, "The worker could not start. Check or repair its runtime in Advanced.", str(exc)) from exc
    with _children_lock:
        _children.add(process)

    def drain() -> None:
        assert process.stdout is not None
        for line in process.stdout:
            lines.append(line[-4000:])

    reader = threading.Thread(target=drain, daemon=True)
    reader.start()
    deadline, last_progress = time.monotonic() + timeout, ""
    try:
        while process.poll() is None:
            check_cancel(cancel)
            if time.monotonic() > deadline:
                raise StageError(stage, "This stage exceeded its time limit. Retry on a shorter song or a faster device.")
            if progress_path is not None and progress is not None:
                try:
                    value = read_json(progress_path)
                    message = str(value.get("message", ""))
                    if message and message != last_progress:
                        progress(message)
                        last_progress = message
                except (OSError, ValueError):
                    pass
            if cancel is None:
                time.sleep(0.1)
            else:
                cancel.wait(0.1)
        reader.join(timeout=2)
        check_cancel(cancel)
        output = "".join(lines)
        if process.returncode:
            raise StageError(stage, "The component failed. Retry or repair its runtime in Advanced.", output)
        return output
    finally:
        if process.poll() is None:
            stop_process(process)
        with _children_lock:
            _children.discard(process)
        reader.join(timeout=2)
        if process.stdout:
            process.stdout.close()


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
            raise StageError(operation, error.get("message", "The model could not complete this stage."),
                             error.get("details", ""), error.get("retryable", True))
        if failure:
            raise failure
        if not isinstance(result.get("result"), dict):
            raise StageError(operation, "The worker result is malformed.")
        return result["result"]
