"""beta.8 runtime compatibility layer for the stronger separation ensemble.

The established runtime implementation is kept in ``runtime_legacy`` so this
follow-up can stay small and low-risk while upgrading only the HQ separator.
"""
from __future__ import annotations

from . import runtime_legacy as _legacy

AUDIO_SEPARATOR_VERSION = "0.47.0"
HQ_SIX_STEM_MODEL = "BS-Roformer-SW.ckpt"

# audio-separator 0.47 adds maintained multi-stem RoFormer output support,
# including BS-Roformer-SW. Keep the existing isolated HQ environment and its
# tested Torch family; changing the requirement forces RuntimeManager to repair
# an older 0.30.2 HQ environment on first HQ use.
_legacy.RUNTIMES["hq"] = [
    requirement.replace("audio-separator[cpu]==0.30.2", f"audio-separator[cpu]=={AUDIO_SEPARATOR_VERSION}")
    for requirement in _legacy.RUNTIMES["hq"]
]
_legacy.RUNTIME_VALIDATION["hq"] = _legacy.RUNTIME_VALIDATION["hq"].replace(
    "'audio-separator': '0.30.2'", f"'audio-separator': '{AUDIO_SEPARATOR_VERSION}'"
)

# Fingerprints describe the maximum provider capability. The provider records
# the exact models that actually ran, so CPU/fallback jobs remain truthful.
_legacy.PROVIDER_MODEL["roformer"] = f"{_legacy.HQ_MODEL}+optional-{HQ_SIX_STEM_MODEL}"
_legacy.PROVIDER_MODEL["demucs"] = "htdemucs_6s+htdemucs_ft+optional-BS-Roformer-SW"

# Re-export the established API after mutating the backing module globals.
from .runtime_legacy import *  # noqa: F401,F403,E402

# Keep the public compatibility module monkeypatchable. A few focused tests and
# downstream integrations replace runtime.run_process; the legacy class resolves
# globals in runtime_legacy, so synchronize that hook immediately before the
# inherited installer runs.
run_process = _legacy.run_process
emit_progress = _legacy.emit_progress


class RuntimeManager(_legacy.RuntimeManager):
    def install(self, name: str, *, device: str = "cpu", cancel=None, progress=None,
                repair: bool = False) -> None:
        _legacy.run_process = run_process
        _legacy.emit_progress = emit_progress
        return super().install(
            name, device=device, cancel=cancel, progress=progress, repair=repair
        )


# New constants are intentionally exported by this compatibility module.
AUDIO_SEPARATOR_VERSION = "0.47.0"
HQ_SIX_STEM_MODEL = "BS-Roformer-SW.ckpt"
