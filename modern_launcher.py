from __future__ import annotations

import app
from modern_ui import install_modern_ui


# v2 is a presentation/flow redesign. MIDI planning, note mapping, page timing
# and Windows input behavior continue to use the established engine modules.
app.APP_VERSION = "2.0.0"

install_modern_ui(app)


if __name__ == "__main__":
    raise SystemExit(app.main())
