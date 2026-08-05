from __future__ import annotations

import app
from modern_ui import install_modern_ui


# Public release version. The launcher sets this before App is created, so the
# window title, header badge, and hidden diagnostic metadata all use v1.2.0.
app.APP_VERSION = "1.2.0"

install_modern_ui(app)


if __name__ == "__main__":
    raise SystemExit(app.main())
