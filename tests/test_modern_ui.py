from __future__ import annotations

from modern_ui import _preserve_song_speed


class FakeVar:
    def __init__(self, value: int) -> None:
        self.value = value

    def get(self) -> int:
        return self.value

    def set(self, value: int) -> None:
        self.value = value


class FakeApp:
    def __init__(self, speed: int) -> None:
        self.speed_var = FakeVar(speed)
        self._suspend_auto_analysis = False
        self.analysis_scheduled = 0
        self.config_saved = 0

    def _schedule_analysis(self) -> None:
        self.analysis_scheduled += 1

    def _save_config(self) -> None:
        self.config_saved += 1


def test_unlock_profile_change_does_not_reset_song_speed() -> None:
    app = FakeApp(75)

    def profile_change_that_applies_profile_defaults() -> None:
        app.speed_var.set(100)

    _preserve_song_speed(app, profile_change_that_applies_profile_defaults)

    assert app.speed_var.get() == 75
    assert app.analysis_scheduled == 1
    assert app.config_saved == 1


def test_song_speed_is_clamped_to_supported_range() -> None:
    app = FakeApp(999)

    def profile_change() -> None:
        app.speed_var.set(100)

    _preserve_song_speed(app, profile_change)

    assert app.speed_var.get() == 200
