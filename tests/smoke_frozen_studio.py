"""Run the windowed PyInstaller child protocol with real bundled Basic Pitch."""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

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
        print("Frozen worker, Basic Pitch model, JSON protocol and note events verified.")


if __name__ == "__main__":
    main()
