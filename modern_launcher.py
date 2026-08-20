from __future__ import annotations

import app
from local_search_integration import install_local_search_integration
from modern_ui import install_modern_ui
from online_integration import install_online_integration


# Keep the established MIDI engine/UI, then layer the optional online library.
app.APP_VERSION = "3.0.7"

install_modern_ui(app)
install_online_integration(app)
install_local_search_integration(app)


if __name__ == "__main__":
    raise SystemExit(app.main())
