from __future__ import annotations

import app
from modern_ui import install_modern_ui
from online_integration import install_online_integration
from studio_integration import install_studio_integration


# Studio is a separate build target. The existing Lite launcher/spec stay unchanged.
app.APP_VERSION = "Studio 0.1.0-beta"

install_modern_ui(app)
install_online_integration(app)
install_studio_integration(app)


if __name__ == "__main__":
    raise SystemExit(app.main())
