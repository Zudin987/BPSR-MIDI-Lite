from __future__ import annotations

import heapq
import threading
import time
from collections.abc import Callable

from midi_engine import MidiPlan, PlannedEvent
from win_input import WindowsKeySender


StatusCallback = Callable[[str, float], None]
FinishedCallback = Callable[[str | None], None]


class MidiPlayer:
    """Play a prepared MIDI timeline without blocking it on control-key taps."""

    TAP_HOLD_SECONDS = 0.012
    PAGE_GUARD_SECONDS = 0.050
    STATUS_INTERVAL_SECONDS = 0.100
    LATE_WARNING_SECONDS = 0.005

    def __init__(self) -> None:
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None
        self.sender: WindowsKeySender | None = None
        self.current_page = 1
        self.current_state = 0
        self.pedal_on = False
        self.page_step_delay = 0.220
        self._key_counts: dict[str, int] = {}
        self._pending_tap_releases: list[tuple[float, int, str]] = []
        self._tap_serial = 0
        self._page_ready_at = 0.0
        self.last_max_lateness_ms = 0.0
        self.last_late_events = 0
        self.last_page_guard_added_ms = 0.0

    @property
    def is_playing(self) -> bool:
        return bool(self.thread and self.thread.is_alive())

    def start(
        self,
        plan: MidiPlan,
        start_delay: float,
        on_status: StatusCallback,
        on_finished: FinishedCallback,
        input_backend: str = "scan",
    ) -> None:
        if self.is_playing:
            raise RuntimeError("Playback is already running.")
        self.stop_event.clear()
        self.current_page = 1
        self.current_state = 0
        self.pedal_on = False
        self.page_step_delay = max(0.040, float(plan.page_switch_delay))
        self._key_counts.clear()
        self._pending_tap_releases.clear()
        self._tap_serial = 0
        self._page_ready_at = 0.0
        self.last_max_lateness_ms = 0.0
        self.last_late_events = 0
        self.last_page_guard_added_ms = 0.0
        self.sender = WindowsKeySender(input_backend)
        self.thread = threading.Thread(
            target=self._run,
            args=(plan, start_delay, on_status, on_finished),
            daemon=True,
        )
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()

    def _wait_until(self, target: float) -> bool:
        while not self.stop_event.is_set():
            remaining = target - time.perf_counter()
            if remaining <= 0:
                return True
            if remaining > 0.010:
                self.stop_event.wait(min(max(remaining - 0.004, 0.001), 0.050))
            else:
                time.sleep(min(remaining, 0.001))
        return False

    def _queue_tap(self, key: str, hold_seconds: float | None = None) -> None:
        """Press now and schedule release without sleeping on the MIDI thread."""
        assert self.sender is not None
        duration = self.TAP_HOLD_SECONDS if hold_seconds is None else hold_seconds
        self.sender.key_down(key)
        self._tap_serial += 1
        heapq.heappush(
            self._pending_tap_releases,
            (time.perf_counter() + max(0.001, duration), self._tap_serial, key),
        )

    def _release_due_taps(self, now: float) -> None:
        assert self.sender is not None
        while self._pending_tap_releases:
            release_at, _serial, key = self._pending_tap_releases[0]
            if release_at > now:
                break
            heapq.heappop(self._pending_tap_releases)
            self.sender.key_up(key)

    def _switch_page(self, target_page: int, wait_between_steps: bool = False) -> None:
        assert self.sender is not None
        if target_page not in (0, 1, 2):
            raise ValueError(f"Invalid page: {target_page}")

        first_step = True
        while self.current_page < target_page:
            if wait_between_steps and not first_step:
                time.sleep(self.page_step_delay)
            if wait_between_steps:
                self.sender.tap(".")
            else:
                self._queue_tap(".")
                self._page_ready_at = max(
                    self._page_ready_at,
                    time.perf_counter() + self.PAGE_GUARD_SECONDS,
                )
            self.current_page += 1
            first_step = False
        while self.current_page > target_page:
            if wait_between_steps and not first_step:
                time.sleep(self.page_step_delay)
            if wait_between_steps:
                self.sender.tap(",")
            else:
                self._queue_tap(",")
                self._page_ready_at = max(
                    self._page_ready_at,
                    time.perf_counter() + self.PAGE_GUARD_SECONDS,
                )
            self.current_page -= 1
            first_step = False

    def _switch_state(self, target_state: int, blocking: bool = False) -> None:
        assert self.sender is not None
        if target_state == self.current_state:
            return

        key: str
        if target_state == 1:
            key = "shift"
        elif target_state == -1:
            key = "ctrl"
        elif target_state == 0:
            if self.current_state == 1:
                key = "shift"
            elif self.current_state == -1:
                key = "ctrl"
            else:
                return
        else:
            raise ValueError(f"Invalid octave state: {target_state}")

        if blocking:
            self.sender.tap(key)
        else:
            self._queue_tap(key)
        self.current_state = target_state

    def _handle_event(self, event: PlannedEvent) -> None:
        assert self.sender is not None

        if event.kind == "page":
            if event.page is not None:
                self._switch_page(event.page)
            return

        if event.kind == "state":
            if event.state is not None:
                self._switch_state(event.state)
            return

        if event.kind == "pedal":
            desired = bool(event.pedal_on)
            if desired != self.pedal_on:
                self._queue_tap("space")
                self.pedal_on = desired
            return

        if not event.key:
            return
        if event.kind == "note_on":
            count = self._key_counts.get(event.key, 0)
            if count == 0:
                self.sender.key_down(event.key)
            self._key_counts[event.key] = count + 1
        elif event.kind == "note_off":
            count = self._key_counts.get(event.key, 0)
            if count <= 1:
                self._key_counts.pop(event.key, None)
                self.sender.key_up(event.key)
            else:
                self._key_counts[event.key] = count - 1

    @staticmethod
    def _must_wait_for_page(event: PlannedEvent) -> bool:
        # Note releases remain immediate to avoid stuck or overlong notes. Inputs
        # that select a mode or make sound wait until the page animation is safe.
        return event.kind in {"state", "pedal", "note_on"}

    def _cleanup(self) -> None:
        if self.sender is None:
            return
        try:
            # Stop pending asynchronous taps and held notes before issuing the
            # slower, best-effort commands that restore the default game state.
            self._pending_tap_releases.clear()
            self.sender.release_all()
            if self.pedal_on:
                self.sender.tap("space")
                self.pedal_on = False
            if self.current_state != 0:
                self._switch_state(0, blocking=True)
            if self.current_page != 1:
                # Cleanup is not timeline-scheduled, so respect the configured
                # animation delay between two physical page presses.
                self._switch_page(1, wait_between_steps=True)
        finally:
            self.sender.release_all()
            self._key_counts.clear()
            self._pending_tap_releases.clear()
            self._page_ready_at = 0.0

    def _run(
        self,
        plan: MidiPlan,
        start_delay: float,
        on_status: StatusCallback,
        on_finished: FinishedCallback,
        input_backend: str = "scan",
    ) -> None:
        del input_backend  # Kept for backwards-compatible direct calls.
        error: str | None = None
        try:
            countdown_end = time.perf_counter() + max(0.0, start_delay)
            while not self.stop_event.is_set():
                remaining = countdown_end - time.perf_counter()
                if remaining <= 0:
                    break
                on_status(f"Starting in {remaining:.1f}s — switch to the game", 0.0)
                self.stop_event.wait(min(0.10, remaining))
            if self.stop_event.is_set():
                return

            start = time.perf_counter()
            total = max(plan.duration, 0.001)
            event_index = 0
            timeline_shift = 0.0
            last_status_at = float("-inf")

            while not self.stop_event.is_set() and (
                event_index < len(plan.events) or self._pending_tap_releases
            ):
                next_event_target = float("inf")
                if event_index < len(plan.events):
                    event = plan.events[event_index]
                    next_event_target = start + event.time + timeline_shift

                    # A page key may have been sent at the same timestamp as the
                    # following note or modifier. Add only the missing part of the
                    # 50 ms guard, then carry that delay into every later event.
                    if (
                        self._must_wait_for_page(event)
                        and self._page_ready_at > next_event_target
                    ):
                        added = self._page_ready_at - next_event_target
                        timeline_shift += added
                        self.last_page_guard_added_ms += added * 1000.0
                        next_event_target += added

                next_release_target = (
                    self._pending_tap_releases[0][0]
                    if self._pending_tap_releases
                    else float("inf")
                )
                if not self._wait_until(min(next_event_target, next_release_target)):
                    break

                now = time.perf_counter()
                self._release_due_taps(now)

                if event_index >= len(plan.events):
                    continue
                event = plan.events[event_index]
                target = start + event.time + timeline_shift
                if target > now:
                    continue

                lateness = max(0.0, now - target)
                self.last_max_lateness_ms = max(
                    self.last_max_lateness_ms,
                    lateness * 1000.0,
                )
                if lateness >= self.LATE_WARNING_SECONDS:
                    self.last_late_events += 1

                self._handle_event(event)
                event_index += 1

                status_now = time.perf_counter()
                progress = min(1.0, event.time / total)
                if (
                    status_now - last_status_at >= self.STATUS_INTERVAL_SECONDS
                    or event_index >= len(plan.events)
                ):
                    on_status(
                        f"Playing {event.time:,.1f}s / {plan.duration:,.1f}s — F10 stops",
                        progress,
                    )
                    last_status_at = status_now

            if not self.stop_event.is_set():
                on_status("Playback completed", 1.0)
        except Exception as exc:  # noqa: BLE001
            error = str(exc)
        finally:
            try:
                self._cleanup()
            finally:
                on_finished(error)
