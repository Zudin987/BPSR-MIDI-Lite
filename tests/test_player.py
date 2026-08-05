from __future__ import annotations

import time
from types import SimpleNamespace

from midi_engine import PlannedEvent
from player import MidiPlayer


class FakeSender:
    def __init__(self) -> None:
        self.held: set[str] = set()
        self.actions: list[tuple[str, str, float]] = []
        self.blocking_taps = 0

    def key_down(self, key: str) -> None:
        if key in self.held:
            return
        self.held.add(key)
        self.actions.append(("down", key, time.perf_counter()))

    def key_up(self, key: str) -> None:
        if key not in self.held:
            return
        self.held.remove(key)
        self.actions.append(("up", key, time.perf_counter()))

    def tap(
        self,
        key: str,
        hold_seconds: float = 0.012,
        gap_seconds: float = 0.012,
    ) -> None:
        self.blocking_taps += 1
        self.key_down(key)
        time.sleep(hold_seconds)
        self.key_up(key)
        if gap_seconds > 0:
            time.sleep(gap_seconds)

    def release_all(self) -> None:
        for key in list(self.held):
            self.key_up(key)


def make_plan(events: list[PlannedEvent], duration: float):
    return SimpleNamespace(
        events=events,
        duration=duration,
        page_switch_delay=0.220,
    )


def first_action_time(sender: FakeSender, action: str, key: str) -> float:
    return next(
        timestamp
        for recorded_action, recorded_key, timestamp in sender.actions
        if recorded_action == action and recorded_key == key
    )


def test_control_event_uses_scheduled_release_instead_of_blocking_tap() -> None:
    player = MidiPlayer()
    sender = FakeSender()
    player.sender = sender

    player._handle_event(
        PlannedEvent(time=0.0, priority=0, kind="state", state=1)
    )
    player._handle_event(
        PlannedEvent(time=0.005, priority=2, kind="note_on", key="a")
    )

    assert sender.blocking_taps == 0
    assert "shift" in sender.held
    assert "a" in sender.held
    assert player._pending_tap_releases


def test_page_switch_guards_the_next_note_and_shifts_the_timeline() -> None:
    player = MidiPlayer()
    sender = FakeSender()
    player.sender = sender
    statuses: list[tuple[str, float]] = []
    finished: list[str | None] = []

    events = [
        PlannedEvent(time=0.0, priority=-30, kind="page", page=2),
        PlannedEvent(time=0.0, priority=20, kind="note_on", key="a"),
        PlannedEvent(time=0.010, priority=0, kind="note_off", key="a"),
        PlannedEvent(time=0.020, priority=20, kind="note_on", key="s"),
        PlannedEvent(time=0.030, priority=0, kind="note_off", key="s"),
    ]

    player._run(
        make_plan(events, duration=0.030),
        0.0,
        lambda text, progress: statuses.append((text, progress)),
        finished.append,
    )

    page_time = first_action_time(sender, "down", ".")
    first_note_time = first_action_time(sender, "down", "a")
    second_note_time = first_action_time(sender, "down", "s")

    # Allow a little scheduler tolerance around the intended 50 ms guard.
    assert first_note_time - page_time >= 0.045
    # The later note keeps its original 20 ms spacing instead of rushing to
    # catch up after the guarded page change.
    assert second_note_time - first_note_time >= 0.015
    assert player.last_page_guard_added_ms >= 45.0
    assert finished == [None]


def test_existing_natural_gap_is_reused_without_extra_delay() -> None:
    player = MidiPlayer()
    sender = FakeSender()
    player.sender = sender
    finished: list[str | None] = []

    events = [
        PlannedEvent(time=0.0, priority=-30, kind="page", page=2),
        PlannedEvent(time=0.080, priority=20, kind="note_on", key="a"),
        PlannedEvent(time=0.100, priority=0, kind="note_off", key="a"),
    ]

    player._run(
        make_plan(events, duration=0.100),
        0.0,
        lambda _text, _progress: None,
        finished.append,
    )

    page_time = first_action_time(sender, "down", ".")
    note_time = first_action_time(sender, "down", "a")
    assert note_time - page_time >= 0.070
    assert player.last_page_guard_added_ms < 5.0
    assert finished == [None]


def test_dense_same_time_events_emit_only_a_small_number_of_status_updates() -> None:
    player = MidiPlayer()
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
                priority=2,
                kind="note_on",
                key=key,
                serial=serial,
            )
        )
        events.append(
            PlannedEvent(
                time=0.0,
                priority=1,
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


def test_pending_tap_is_released_without_using_blocking_tap() -> None:
    player = MidiPlayer()
    sender = FakeSender()
    player.sender = sender

    player._queue_tap("shift", hold_seconds=0.003)
    assert "shift" in sender.held
    assert sender.blocking_taps == 0

    time.sleep(0.005)
    player._release_due_taps(time.perf_counter())

    assert "shift" not in sender.held
    assert sender.blocking_taps == 0
