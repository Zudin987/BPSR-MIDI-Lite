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


# v3.3 development keeps the released v3.2 BPSR timing/safety layer intact and
# adds an adaptive musical arranger plus local in-game calibration on top.
# Public version remains v3.2.0 until the v3.3 candidate is fully validated.
app.APP_VERSION = "3.2.0"

install_online_search_bridge()
install_modern_ui(app)
install_gaming_ui_2026(app)
install_online_integration(app)
install_online_search_ui_2026()
install_local_search_integration(app)
install_gaming_runtime_2026(app)
install_playback_overhaul(app)
install_advanced_playback_profile(app)
install_adaptive_arranger(app)
install_adaptive_pressure_model(app)
install_calibration_lab(app)


if __name__ == "__main__":
    raise SystemExit(app.main())
