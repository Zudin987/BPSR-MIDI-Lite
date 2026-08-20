from __future__ import annotations

import app
from local_search_integration import install_local_search_integration
from modern_ui import install_modern_ui
from online_integration import install_online_integration
from studio_integration import install_studio_integration
from studio_polish import install_studio_polish


# Studio remains a separate build target; Lite keeps its own launcher/spec.
app.APP_VERSION = "Studio 0.1.1-beta"

install_modern_ui(app)
install_online_integration(app)
install_local_search_integration(app)
install_studio_integration(app)
install_studio_polish(app)


if __name__ == "__main__":
    raise SystemExit(app.main())
