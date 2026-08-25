from __future__ import annotations

from types import SimpleNamespace

import pytest

import player as player_module
from midi_engine import PlannedEvent
from player import MidiPlayer


class FakeSender:
    def __init__(self) -> None:
        self.held: set[str] = set()
        self.actions: list[tuple[str, str]] = []
        self.taps: list[str] = []

    def key_down(self, key: str) -> None:
        if key in self.held:
            return
        self.held.add(key)
        self.actions.append(("down", key))

    def key_up(self, key: str) -> None:
        if key not in self.held:
            return
        self.held.remove(key)
        self.actions.append(("up", key))

    def tap(
        self,
        key: str,
        hold_seconds: float = 0.012,
        gap_seconds: float = 0.012,
    ) -> None:
        del hold_seconds, gap_seconds
        self.taps.append(key)
        self.key_down(key)
        self.key_up(key)

    def release_all(self) -> None:
        for key in list(self.held):
            self.key_up(key)


class ImmediatePlayer(MidiPlayer):
    def _wait_until(self, target: float) -> bool:
        del target
        return not self.stop_event.is_set()


def make_plan(events: list[PlannedEvent], duration: float):
    return SimpleNamespace(
        events=events,
        duration=duration,
        page_switch_delay=0.220,
        mode="stable",
        page_switches=0,
    )


def test_octave_state_uses_complete_tap() -> None:
    player = MidiPlayer()
    sender = FakeSender()
    player.sender = sender

    player._handle_event(
        PlannedEvent(time=0.0, priority=-20, kind="state", state=1)
    )

    assert sender.taps == ["shift"]
    assert player.current_state == 1
    assert not sender.held


def test_page_switch_uses_complete_tap() -> None:
    player = MidiPlayer()
    sender = FakeSender()
    player.sender = sender

    player._handle_event(
        PlannedEvent(time=0.0, priority=-30, kind="page", page=2)
    )

    assert sender.taps == ["."]
    assert player.current_page == 2
    assert not sender.held


def test_sustain_toggles_only_when_state_changes() -> None:
    player = MidiPlayer()
    sender = FakeSender()
    player.sender = sender

    player._handle_event(
        PlannedEvent(time=0.0, priority=10, kind="pedal", pedal_on=True)
    )
    player._handle_event(
        PlannedEvent(time=0.1, priority=10, kind="pedal", pedal_on=True)
    )
    player._handle_event(
        PlannedEvent(time=0.2, priority=10, kind="pedal", pedal_on=False)
    )

    assert sender.taps == ["space", "space"]
    assert player.pedal_on is False


def test_run_preserves_note_event_order() -> None:
    player = ImmediatePlayer()
    sender = FakeSender()
    player.sender = sender
    statuses: list[tuple[str, float]] = []
    finished: list[str | None] = []

    events = [
        PlannedEvent(time=0.0, priority=20, kind="note_on", key="a"),
        PlannedEvent(time=0.1, priority=0, kind="note_off", key="a"),
        PlannedEvent(time=0.2, priority=20, kind="note_on", key="s"),
        PlannedEvent(time=0.3, priority=0, kind="note_off", key="s"),
    ]

    player._run(
        make_plan(events, duration=0.3),
        0.0,
        lambda text, progress: statuses.append((text, progress)),
        finished.append,
    )

    assert sender.actions[:4] == [
        ("down", "a"),
        ("up", "a"),
        ("down", "s"),
        ("up", "s"),
    ]
    assert statuses[-1] == ("Playback completed", 1.0)
    assert finished == [None]


def test_dense_events_do_not_spam_ui_status() -> None:
    player = ImmediatePlayer()
    sender = FakeSender()
    player.sender = sender
    statuses: list[tuple[str, float]] = []
    finished: list[str | None] = []

    events: list[PlannedEvent] = []
    for serial in range(200):
        key = "a" if serial % 2 == 0 else "s"
        events.append(
            PlannedEvent(
                time=0.0,
                priority=20,
                kind="note_on",
                key=key,
                serial=serial,
            )
        )
        events.append(
            PlannedEvent(
                time=0.0,
                priority=0,
                kind="note_off",
                key=key,
                serial=serial,
            )
        )

    player._run(
        make_plan(events, duration=0.001),
        0.0,
        lambda text, progress: statuses.append((text, progress)),
        finished.append,
    )

    assert len(statuses) <= 3
    assert statuses[-1] == ("Playback completed", 1.0)
    assert finished == [None]


def test_stable_start_rejects_page_event_before_input_initializes() -> None:
    plan = make_plan(
        [PlannedEvent(time=0.0, priority=-30, kind="page", page=0)],
        duration=0.1,
    )
    plan.page_switches = 1

    with pytest.raises(ValueError, match="Stable playback"):
        MidiPlayer().start(plan, 0.0, lambda *_args: None, lambda _error: None)


def test_visualizer_playhead_moves_continuously_and_freezes_while_paused(monkeypatch) -> None:
    player = MidiPlayer()
    player.position = 1.0
    player._clock_started_at = 100.0
    player._clock_paused_total = 1.0
    player._clock_duration = 10.0
    monkeypatch.setattr(player_module.time, "perf_counter", lambda: 106.0)

    assert player.playback_position == pytest.approx(5.0)

    player._clock_pause_started_at = 104.0
    assert player.playback_position == pytest.approx(3.0)


def test_focus_guard_tracks_the_countdown_target_process(monkeypatch) -> None:
    player = MidiPlayer()
    player._focus_guard_enabled = True
    player._target_process_id = 1234
    monkeypatch.setattr(player_module, "foreground_process_id", lambda: 1234)
    assert player._target_has_focus(force=True)

    monkeypatch.setattr(player_module, "foreground_process_id", lambda: 5678)
    assert not player._target_has_focus(force=True)
