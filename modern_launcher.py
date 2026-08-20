from __future__ import annotations

import app
from gaming_ui_2026 import install_gaming_ui_2026
from local_search_integration import install_local_search_integration
from modern_ui import install_modern_ui
from online_integration import install_online_integration
from online_search_bridge import install_online_search_bridge
from online_search_ui_2026 import install_online_search_ui_2026


# v3.1 keeps the proven BPSR MIDI planner/input engine and replaces only the
# presentation/search layers with the 2026 single-window experience.
app.APP_VERSION = "3.1.0"

install_online_search_bridge()
install_modern_ui(app)
install_gaming_ui_2026(app)
install_online_integration(app)
install_online_search_ui_2026()
install_local_search_integration(app)


if __name__ == "__main__":
    raise SystemExit(app.main())
