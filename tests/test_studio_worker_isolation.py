from __future__ import annotations

import sys
from pathlib import Path

from studio_band.runtime import RuntimeManager
from studio_band_worker_isolation import install_external_worker_isolation, stage_external_worker


def test_external_worker_bundle_is_source_only_and_content_addressed(tmp_path: Path) -> None:
    manager = RuntimeManager(tmp_path)
    first = stage_external_worker(manager)
    second = stage_external_worker(manager)

    assert first == second
    assert first.is_file()
    assert first.parent.is_relative_to(manager.runtime_root / "worker-source")
    assert (first.parent / "studio_band" / "providers.py").is_file()
    assert (first.parent / "studio_band" / "protocol.py").is_file()
    assert (first.parent / "studio-worker-bundle.json").is_file()
    assert not list(first.parent.rglob("*.pyd"))
    assert not list(first.parent.rglob("*.dll"))


def test_frozen_external_provider_uses_clean_worker_bundle(tmp_path: Path, monkeypatch) -> None:
    install_external_worker_isolation()
    manager = RuntimeManager(tmp_path)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(manager, "available", lambda name: True)

    command = manager.command_for("demucs")

    assert command[0] == str(manager.python("separator"))
    worker = Path(command[1])
    assert worker.is_file()
    assert worker.parent.is_relative_to(manager.runtime_root / "worker-source")
    assert worker.name == "studio_band_worker.py"
