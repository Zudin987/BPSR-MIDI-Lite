"""Studio-only audio analysis. No AI framework is imported by this package."""
from __future__ import annotations

import os

VERSION = "0.5.0-beta.9-hotfix7"
PIPELINE_VERSION = "band-accurate-9"

# beta.9 is an additive quality layer over the proven beta.8 implementation.
# External model workers need only provider/runtime registration. Keeping the
# desktop pipeline/fusion layer out of those clean Python 3.11 bundles prevents
# imports of root-level Studio modules that are intentionally not staged there.
if os.environ.get("BPSR_STUDIO_WORKER") == "1":
    from . import providers, runtime
    from .beta9 import _patch_providers, _patch_runtimes
    from .precision_judges import (
        _patch_providers as _patch_precision_providers,
        _patch_runtimes as _patch_precision_runtimes,
    )
    from .fast_precision import _patch_providers as _patch_fast_precision_providers

    _patch_runtimes(runtime)
    _patch_providers(providers)
    _patch_precision_runtimes(runtime)
    _patch_precision_providers(providers)
    _patch_fast_precision_providers(providers)
else:
    from .beta9 import apply_beta9
    from .pitch_guard import apply_pitch_guard
    from .final_audio_note_guard import apply_final_audio_note_guard
    from .precision_judges import apply_precision_judges
    from .fast_precision import apply_fast_precision

    apply_beta9()
    apply_pitch_guard()
    apply_final_audio_note_guard()
    apply_precision_judges()
    apply_fast_precision()