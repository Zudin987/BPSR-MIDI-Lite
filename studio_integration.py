from __future__ import annotations

from typing import Any

import studio_ui


def _build_ui(self: Any) -> None:
    # Build the unchanged Lite + Online Sequencer interface first, then add the
    # Studio-only YouTube tab. Lite's launcher never installs this integration.
    self._studio_original_build_ui()
    studio_ui.attach(self)


def _analyze(self: Any) -> None:
    self._studio_original_analyze()
    if not hasattr(self, "song_source_var") or self.song_source_var.get() != "youtube":
        return

    if self.current_plan is None and not self.file_var.get():
        title, message = studio_ui.empty_selection_message()
        self.suitability_var.set(title)
        self.analysis_var.set(message)
        return

    if self.current_plan is not None:
        suffix = studio_ui.analysis_suffix()
        current = self.analysis_var.get()
        if suffix.strip() not in current:
            self.analysis_var.set(current + suffix)


def install_studio_integration(app_module: Any) -> None:
    """Add Studio-only YouTube/audio transcription without changing Lite."""
    app_class = app_module.App

    app_class._studio_original_build_ui = app_class._build_ui
    app_class._studio_original_analyze = app_class._analyze

    app_class._build_ui = _build_ui
    app_class._analyze = _analyze
