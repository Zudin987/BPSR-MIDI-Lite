from __future__ import annotations

import app
from gaming_runtime_2026 import install_gaming_runtime_2026
from gaming_ui_2026 import install_gaming_ui_2026
from local_search_integration import install_local_search_integration
from modern_ui import install_modern_ui
from online_integration import install_online_integration
from online_search_bridge import install_online_search_bridge
from online_search_ui_2026 import install_online_search_ui_2026
from playback_advanced_ui import install_advanced_playback_profile
from playback_overhaul import install_playback_overhaul


# v3.2 keeps the proven MIDI parser/range model and installs the BPSR-aware
# articulation, state-planning, input batching and timing-telemetry layer.
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


if __name__ == "__main__":
    raise SystemExit(app.main())
