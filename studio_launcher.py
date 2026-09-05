from __future__ import annotations

import sys

# Dispatch before importing app/Tk/pynput. A frozen child must never create a
# second GUI, install input hooks, or inherit the parent's worker argv as a song.
if __name__ == "__main__" and len(sys.argv) > 1 and sys.argv[1] == "--studio-worker":
    from studio_band_worker import main as worker_main
    raise SystemExit(worker_main(sys.argv[2:]))

import app
from band_arranger_identity import install_band_arranger_identity
from band_cloudflare import install_cloudflare_band_transport
from band_lineup import install_band_lineup
from band_musical_sharing import install_shared_band_arrangement
from band_network_hardening import install_band_network_hardening
from band_room_registry import install_band_room_registry
from band_runtime_hardening import install_band_runtime_hardening
from band_share import install_band_midi_sharing
from band_ui import install_band_mode
from gaming_runtime_2026 import install_gaming_runtime_2026
from gaming_ui_2026 import install_gaming_ui_2026
from local_search_integration import install_local_search_integration
from modern_ui import install_modern_ui
from online_integration import install_online_integration
from online_search_bridge import install_online_search_bridge
from online_search_ui_2026 import install_online_search_ui_2026
from playback_adaptive import install_adaptive_arranger
from playback_adaptive_pressure import install_adaptive_pressure_model
from playback_adaptive_ui import install_adaptive_arranger_ui
from playback_advanced_ui import install_advanced_playback_profile
from playback_arranger_refinements import install_arranger_refinements
from playback_calibration_guidance import install_guided_calibration
from playback_calibration_provenance import install_calibration_provenance
from playback_calibration_ui import install_calibration_lab
from playback_evidence_refinements import install_evidence_refinements
from playback_overhaul import install_playback_overhaul
from studio_audio_latency import install_studio_audio_latency
from studio_core_transcription import install_core_transcription
from studio_integration import install_studio_integration
from studio_polish import install_studio_polish
from studio_band_responsive import install_responsive_band_audio
from studio_band_ui import install_band_audio
from ui_persistent_library import install_persistent_library
from ui_product_overhaul_v34 import install_product_ui_overhaul


# Studio remains a separate experimental build target and inherits Lite v3.4's
# evidence-driven arranger/UI layer plus optional WASAPI response diagnostics.
app.APP_VERSION = "Studio 0.5.0-band-accurate-beta.3"

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
install_arranger_refinements(app)
install_adaptive_pressure_model(app)
install_adaptive_arranger_ui(app)
install_evidence_refinements(app)
install_calibration_lab(app)
install_guided_calibration(app)
install_calibration_provenance(app)
install_studio_audio_latency(app)
install_product_ui_overhaul(app)
install_persistent_library(app)
install_band_mode(app)
install_band_lineup(app)
install_shared_band_arrangement(app)
install_band_arranger_identity(app)
install_band_runtime_hardening(app)
install_band_midi_sharing(app)
install_band_network_hardening(app)
install_cloudflare_band_transport(app)
install_band_room_registry(app)
install_responsive_band_audio()
install_band_audio(app)


if __name__ == "__main__":
    raise SystemExit(app.main())