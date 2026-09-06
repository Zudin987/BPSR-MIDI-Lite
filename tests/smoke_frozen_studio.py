"""Run both frozen Studio worker boundaries against real Python runtimes."""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

# This script is executed as `python tests/smoke_frozen_studio.py`, so Python
# otherwise puts only the tests directory at sys.path[0]. Add the repository
# root explicitly before importing Studio modules used to provision Python 3.11.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from studio_band.protocol import run_process
from studio_band.runtime import RuntimeManager
from studio_synthetic_audio import make_song


def main():
    executable = Path(sys.argv[1]).resolve()
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        audio = root / "synthetic.wav"
        make_song(audio)
        request, response, progress = (root / n for n in ("request.json", "response.json", "progress.json"))
        request.write_text(json.dumps({"protocol": 1, "id": "frozen-smoke", "provider": "basic_pitch", "operation": "infer",
                                       "payload": {"audio": str(audio), "source": "piano", "output": str(root), "device": "cpu"}}))
        # A windowed PyInstaller process can have no stdout; the protocol must
        # still return errors/progress/results through files with matching IDs.
        process = subprocess.run([str(executable), "--studio-worker", str(request), str(response), str(progress)], timeout=300)
        assert response.exists(), "Frozen worker did not write a response (or opened the GUI)"
        result = json.loads(response.read_text(encoding="utf-8"))
        assert process.returncode == 0 and result["status"] == "ok", result
        assert result["id"] == "frozen-smoke"
        assert result["result"]["events"], "Bundled Basic Pitch returned no synthetic notes"

        # Reproduce the boundary that failed on beta.5: a Python 3.10 one-file
        # Studio starts an external managed Python 3.11 model worker. The frozen
        # EXE must stage source outside _MEI so 3.11 can never import PyInstaller's
        # Python 3.10 extension modules such as _socket.pyd.
        manager = RuntimeManager(root / "runtime-smoke")
        uv = manager._uv()
        runtime = manager.runtime_root / "python311-smoke"
        run_process(
            [str(uv), "venv", "--python", "3.11", "--managed-python", str(runtime)],
            stage="Python 3.11 smoke setup",
            env=manager.environment(),
            timeout=900,
        )
        python311 = manager.python("python311-smoke")
        external_report = root / "external-worker-smoke.json"
        external = subprocess.run(
            [str(executable), "--studio-external-worker-smoke", str(python311), str(external_report)],
            timeout=300,
        )
        assert external_report.exists(), "Frozen external worker smoke did not write its report"
        external_result = json.loads(external_report.read_text(encoding="utf-8"))
        assert external.returncode == 0 and external_result.get("ok") is True, external_result
        assert external_result.get("worker_outside_mei") is True, external_result
        assert "(3, 11)" in external_result.get("external_python", ""), external_result
        print("Frozen Basic Pitch worker and isolated external Python 3.11 model worker verified.")


if __name__ == "__main__":
    main()
