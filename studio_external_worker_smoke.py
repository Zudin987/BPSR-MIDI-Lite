"""Frozen-build diagnostic for the external model-worker Python boundary."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

from studio_band.protocol import PROTOCOL_VERSION, run_process
from studio_band.runtime import RuntimeManager
from studio_band.storage import atomic_json, read_json
from studio_band_worker_isolation import stage_external_worker


def main(argv=None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        return 2
    python311 = Path(args[0]).resolve()
    report_path = Path(args[1]).resolve() if len(args) > 1 else None
    if not python311.is_file():
        return 3

    try:
        version = subprocess.check_output(
            [str(python311), "-c", "import sys; print(sys.version_info[:2])"],
            text=True,
            stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            timeout=30,
        ).strip()
        if "(3, 11)" not in version:
            raise RuntimeError(f"Expected Python 3.11, got {version}")

        with tempfile.TemporaryDirectory(prefix="bpsr-studio-worker-smoke-") as temporary:
            root = Path(temporary)
            manager = RuntimeManager(root)
            worker = stage_external_worker(manager)
            requests = root / "requests"
            requests.mkdir(parents=True, exist_ok=True)
            request_id = uuid.uuid4().hex
            request = requests / "request.json"
            response = requests / "response.json"
            progress = requests / "progress.json"
            atomic_json(
                request,
                {
                    "protocol": PROTOCOL_VERSION,
                    "id": request_id,
                    "provider": "demucs",
                    "operation": "capabilities",
                    "payload": {},
                },
            )
            run_process(
                [str(python311), str(worker), str(request), str(response), str(progress)],
                stage="Frozen external worker smoke",
                env=manager.environment(),
                cwd=requests,
                timeout=120,
            )
            result = read_json(response)
            if result.get("protocol") != PROTOCOL_VERSION or result.get("id") != request_id:
                raise RuntimeError("External worker returned an incompatible response")
            if result.get("status") != "ok":
                raise RuntimeError(json.dumps(result, ensure_ascii=False))
            payload = result.get("result", {})
            if payload.get("provider") != "demucs":
                raise RuntimeError("External worker did not load the expected provider registry")

            frozen_root = Path(getattr(sys, "_MEIPASS", "")).resolve() if getattr(sys, "frozen", False) else None
            if frozen_root and worker.resolve().is_relative_to(frozen_root):
                raise RuntimeError("External worker was not isolated from PyInstaller's extraction directory")

            report = {
                "ok": True,
                "host_frozen": bool(getattr(sys, "frozen", False)),
                "host_python": list(sys.version_info[:3]),
                "external_python": version,
                "worker_outside_mei": True,
                "capabilities": payload,
            }
            if report_path:
                report_path.parent.mkdir(parents=True, exist_ok=True)
                report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        return 0
    except Exception as exc:
        if report_path:
            try:
                report_path.parent.mkdir(parents=True, exist_ok=True)
                report_path.write_text(
                    json.dumps({"ok": False, "error": str(exc)}, indent=2), encoding="utf-8"
                )
            except OSError:
                pass
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
