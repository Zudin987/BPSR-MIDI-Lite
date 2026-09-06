"""Studio-only audio analysis. No AI framework is imported by this package."""

VERSION = "0.5.0-beta.9"
PIPELINE_VERSION = "band-accurate-3"

# beta.9 is an additive quality layer over the proven beta.8 implementation.
# Importing it patches only lightweight orchestration; heavy AI frameworks stay
# inside isolated worker runtimes and are still imported lazily.
from .beta9 import apply_beta9

apply_beta9()
