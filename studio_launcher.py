from __future__ import annotations

import app
from gaming_runtime_2026 import install_gaming_runtime_2026
from gaming_ui_2026 import install_gaming_ui_2026
from local_search_integration import install_local_search_integration
from modern_ui import install_modern_ui
from online_integration import install_online_integration
from online_search_bridge import install_online_search_bridge
from online_search_ui_2026 import install_online_search_ui_2026
from playback_adaptive import install_adaptive_arranger
from playback_adaptive_pressure import install_adaptive_pressure_model
from playback_advanced_ui import install_advanced_playback_profile
from playback_calibration_ui import install_calibration_lab
from playback_overhaul import install_playback_overhaul
from studio_audio_latency import install_studio_audio_latency
from studio_core_transcription import install_core_transcription
from studio_integration import install_studio_integration
from studio_polish import install_studio_polish


# Studio remains a separate experimental build target. v3.3 development adds
# the same adaptive arranger/calibration layer while keeping the released Studio
# version string unchanged until the branch is ready to ship.
app.APP_VERSION = "Studio 0.3.0-experimental-beta"

install_core_transcription()
install_online_search_bridge()
install_modern_ui(app)
install_gaming_ui_2026(app)
install_online_integration(app)
install_online_search_ui_2026()
install_local_search_integration(app)
install_studio_integration(app)
install_studio_polish(app)
install_gaming_runtime_2026(app)
install_playback_overhaul(app)
install_advanced_playback_profile(app)
install_adaptive_arranger(app)
install_adaptive_pressure_model(app)
install_calibration_lab(app)
install_studio_audio_latency(app)


if __name__ == "__main__":
    raise SystemExit(app.main())
