"""Studio-only audio analysis. No AI framework is imported by this package."""
from __future__ import annotations

import os

VERSION = "0.5.0-beta.9-hotfix2"
PIPELINE_VERSION = "band-accurate-4"

# beta.9 is an additive quality layer over the proven beta.8 implementation.
# External model workers need only provider/runtime registration. Keeping the
# desktop pipeline/fusion layer out of those clean Python 3.11 bundles prevents
# imports of root-level Studio modules that are intentionally not staged there.
if os.environ.get("BPSR_STUDIO_WORKER") == "1":
    from . import providers, runtime
    from .beta9 import _patch_providers, _patch_runtimes

    _patch_runtimes(runtime)
    _patch_providers(providers)
else:
    from .beta9 import apply_beta9
    from .pitch_guard import apply_pitch_guard

    apply_beta9()
    apply_pitch_guard()
