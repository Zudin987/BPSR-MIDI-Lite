"""Worker entry point shared by isolated Python runtimes and the Studio EXE."""
from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path


def main(argv=None) -> int:
    # PyInstaller's windowed bootloader supplies None for these streams.
    # Model libraries use print/tqdm even though our protocol uses JSON files.
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = sys.stdout
    from studio_band.protocol import PROTOCOL_VERSION
    from studio_band.storage import atomic_json, read_json
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 3:
        return 2
    request_path, response_path, progress_path = map(Path, args)
    request_id = ""
    try:
        request = read_json(request_path)
        request_id = request["id"]
        if request["protocol"] != PROTOCOL_VERSION:
            raise ValueError("Unsupported Studio worker protocol")
        from studio_band.providers import PROVIDERS, run_provider
        provider = request["provider"]
        if provider not in PROVIDERS:
            raise ValueError("Unknown Studio worker provider")
        def report(message):
            atomic_json(progress_path, {"id": request_id, "message": str(message)})
        if request["operation"] == "capabilities":
            result = {"version": 1, "provider": provider, "capabilities": ["infer", "cancel"], "status": "ready"}
        elif request["operation"] == "infer":
            result = run_provider(provider, request["payload"], report)
        else:
            raise ValueError("Unknown Studio worker operation")
        atomic_json(response_path, {"protocol": PROTOCOL_VERSION, "id": request_id, "status": "ok", "result": result})
        return 0
    except Exception as exc:
        atomic_json(response_path, {"protocol": PROTOCOL_VERSION, "id": request_id, "status": "error",
                                   "error": {"message": str(exc) or type(exc).__name__,
                                             "details": traceback.format_exc(), "retryable": True}})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
