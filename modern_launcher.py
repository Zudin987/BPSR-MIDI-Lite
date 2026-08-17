from __future__ import annotations

import app
from modern_ui import install_modern_ui


# Keep the established MIDI engine while installing the simplified UI.
app.APP_VERSION = "2.4.0"

install_modern_ui(app)


if __name__ == "__main__":
    raise SystemExit(app.main())
