from __future__ import annotations

import app
from modern_ui import install_modern_ui


# v2 keeps the established MIDI engine while simplifying how users reach it.
app.APP_VERSION = "2.2.0"

install_modern_ui(app)


if __name__ == "__main__":
    raise SystemExit(app.main())
