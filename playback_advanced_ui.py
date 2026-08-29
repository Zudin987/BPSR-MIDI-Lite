from __future__ import annotations

from typing import Any


CUSTOM_PROFILE_LABEL = "Custom — Advanced timing & mapping"


def install_advanced_playback_profile(app_module: Any) -> None:
    """Expose the App's existing custom-profile path for v3.2 timing controls."""
    if getattr(app_module, "_advanced_playback_profile_installed", False):
        return

    original_labels_for = app_module.profile_labels_for
    original_label_for = app_module.profile_label_for

    def profile_labels_for(instrument: Any) -> dict[str, str]:
        labels = dict(original_labels_for(instrument))
        labels[CUSTOM_PROFILE_LABEL] = "custom"
        return labels

    def profile_label_for(instrument: Any, code: str) -> str:
        if code == "custom":
            return CUSTOM_PROFILE_LABEL
        return original_label_for(instrument, code)

    app_module.profile_labels_for = profile_labels_for
    app_module.profile_label_for = profile_label_for
    app_module._advanced_playback_profile_installed = True
