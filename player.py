from __future__ import annotations

import threading
import time
from collections.abc import Callable

from midi_engine import MidiPlan, PlannedEvent
from win_input import WindowsKeySender


StatusCallback = Callable[[str, float], None]
FinishedCallback = Callable[[str | None], None]


class MidiPlayer:
    """Play a prepared MIDI timeline using the established blocking tap behavior."""

    STATUS_INTERVAL_SECONDS = 0.100

    def __init__(self) -> None:
        self.stop_event = threading.Event()
        self.pause_event = threading.Event()
        self.thread: threading.Thread | None = None
        self.sender: WindowsKeySender | None = None
        self.current_page = 1
        self.current_state = 0
        self.pedal_on = False
        self.page_step_delay = 0.220
        self._key_counts: dict[str, int] = {}
        self._keys_temporarily_released = False
        self.position = 0.0

    @property
    def is_playing(self) -> bool:
        return bool(self.thread and self.thread.is_alive())

    @property
    def is_paused(self) -> bool:
        return self.is_playing and self.pause_event.is_set()

    @property
    def active_keys(self) -> tuple[str, ...]:
        try:
            return tuple(self._key_counts)
        except RuntimeError:
            return ()

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
        self.pause_event.clear()
        self.current_page = 1
        self.current_state = 0
        self.pedal_on = False
        self.page_step_delay = max(0.040, float(plan.page_switch_delay))
        self._key_counts.clear()
        self._keys_temporarily_released = False
        self.position = 0.0
        self.sender = WindowsKeySender(input_backend)

        self.thread = threading.Thread(
            target=self._run,
            args=(plan, start_delay, on_status, on_finished),
            daemon=True,
        )
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        self.pause_event.clear()

    def toggle_pause(self) -> bool:
        """Pause/resume without changing the prepared MIDI plan.

        Active note keys are released while paused and restored on resume so a
        long pause cannot leave BPSR sustaining keys indefinitely.
        """
        if not self.is_playing:
            return False
        if self.pause_event.is_set():
            self.pause_event.clear()
            return False
        self.pause_event.set()
        return True

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

    def _switch_page(self, target_page: int, wait_between_steps: bool = False) -> None:
        assert self.sender is not None
        if target_page not in (0, 1, 2):
            raise ValueError(f"Invalid page: {target_page}")

        first_step = True
        while self.current_page < target_page:
            if wait_between_steps and not first_step:
                time.sleep(self.page_step_delay)
            self.sender.tap(".")
            self.current_page += 1
            first_step = False

        while self.current_page > target_page:
            if wait_between_steps and not first_step:
                time.sleep(self.page_step_delay)
            self.sender.tap(",")
            self.current_page -= 1
            first_step = False

    def _switch_state(self, target_state: int) -> None:
        assert self.sender is not None
        if target_state == self.current_state:
            return

        if target_state == 1:
            self.sender.tap("shift")
        elif target_state == -1:
            self.sender.tap("ctrl")
        elif target_state == 0:
            if self.current_state == 1:
                self.sender.tap("shift")
            elif self.current_state == -1:
                self.sender.tap("ctrl")
        else:
            raise ValueError(f"Invalid octave state: {target_state}")

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
                self.sender.tap("space")
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
                if not self._keys_temporarily_released:
                    self.sender.key_up(event.key)
            else:
                self._key_counts[event.key] = count - 1

    def _release_note_keys_for_pause(self) -> None:
        if self.sender is None or self._keys_temporarily_released:
            return
        for key in tuple(self._key_counts):
            self.sender.key_up(key)
        self._keys_temporarily_released = True

    def _restore_note_keys_after_pause(self) -> None:
        if self.sender is None or not self._keys_temporarily_released:
            return
        for key in tuple(self._key_counts):
            self.sender.key_down(key)
        self._keys_temporarily_released = False

    def _pause_if_needed(self, on_status: StatusCallback, progress: float) -> float:
        """Block while paused and return seconds that must be added to the schedule."""
        if not self.pause_event.is_set() or self.stop_event.is_set():
            return 0.0
        self._release_note_keys_for_pause()
        started = time.perf_counter()
        on_status("Paused — press Resume to continue", progress)
        while self.pause_event.is_set() and not self.stop_event.is_set():
            self.stop_event.wait(0.050)
        elapsed = time.perf_counter() - started
        if not self.stop_event.is_set():
            self._restore_note_keys_after_pause()
        return elapsed

    def _cleanup(self) -> None:
        if self.sender is None:
            return

        try:
            self._keys_temporarily_released = False
            if self.pedal_on:
                self.sender.tap("space")
                self.pedal_on = False
            if self.current_state != 0:
                self._switch_state(0)
            if self.current_page != 1:
                # Cleanup is not timeline-scheduled, so respect the configured
                # delay between two physical page presses.
                self._switch_page(1, wait_between_steps=True)
        finally:
            self.sender.release_all()
            self._key_counts.clear()
            self.pause_event.clear()

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
                if self.pause_event.is_set():
                    paused_for = self._pause_if_needed(on_status, 0.0)
                    countdown_end += paused_for
                    continue
                remaining = countdown_end - time.perf_counter()
                if remaining <= 0:
                    break
                on_status(f"Starting in {remaining:.1f}s — switch to the game", 0.0)
                self.stop_event.wait(min(0.10, remaining))

            if self.stop_event.is_set():
                return

            start = time.perf_counter()
            paused_total = 0.0
            total = max(plan.duration, 0.001)
            last_status_at = float("-inf")

            for index, event in enumerate(plan.events):
                while not self.stop_event.is_set():
                    if self.pause_event.is_set():
                        paused_total += self._pause_if_needed(
                            on_status,
                            min(1.0, self.position / total),
                        )
                        continue
                    target = start + paused_total + event.time
                    if self._wait_until(target):
                        break
                if self.stop_event.is_set():
                    break

                self._handle_event(event)
                self.position = float(event.time)

                status_now = time.perf_counter()
                if (
                    status_now - last_status_at >= self.STATUS_INTERVAL_SECONDS
                    or index == len(plan.events) - 1
                ):
                    progress = min(1.0, event.time / total)
                    on_status(
                        f"Playing {event.time:,.1f}s / {plan.duration:,.1f}s — F10 stops",
                        progress,
                    )
                    last_status_at = status_now

            if not self.stop_event.is_set():
                self.position = float(plan.duration)
                on_status("Playback completed", 1.0)
        except Exception as exc:  # noqa: BLE001
            error = str(exc)
        finally:
            try:
                self._cleanup()
            finally:
                on_finished(error)
