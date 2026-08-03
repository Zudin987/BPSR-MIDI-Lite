from __future__ import annotations

import threading
import time
from collections.abc import Callable

from midi_engine import MidiPlan, PlannedEvent
from win_input import WindowsKeySender


StatusCallback = Callable[[str, float], None]
FinishedCallback = Callable[[str | None], None]


class MidiPlayer:
    def __init__(self) -> None:
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None
        self.sender: WindowsKeySender | None = None
        self.current_page = 1
        self.current_state = 0
        self.pedal_on = False
        self.page_step_delay = 0.220
        self._key_counts: dict[str, int] = {}

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
                self.sender.key_up(event.key)
            else:
                self._key_counts[event.key] = count - 1

    def _cleanup(self) -> None:
        if self.sender is None:
            return
        try:
            if self.pedal_on:
                self.sender.tap("space")
                self.pedal_on = False
            if self.current_state != 0:
                self._switch_state(0)
            if self.current_page != 1:
                # Cleanup is not timeline-scheduled, so respect the measured
                # animation delay between two physical page presses.
                self._switch_page(1, wait_between_steps=True)
        finally:
            self.sender.release_all()
            self._key_counts.clear()

    def _run(
        self,
        plan: MidiPlan,
        start_delay: float,
        on_status: StatusCallback,
        on_finished: FinishedCallback,
        input_backend: str = "scan",
    ) -> None:
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
            for event in plan.events:
                if not self._wait_until(start + event.time):
                    break
                self._handle_event(event)
                progress = min(1.0, event.time / total)
                on_status(
                    f"Playing {event.time:,.1f}s / {plan.duration:,.1f}s — F10 stops",
                    progress,
                )

            if not self.stop_event.is_set():
                on_status("Playback completed", 1.0)
        except Exception as exc:  # noqa: BLE001
            error = str(exc)
        finally:
            try:
                self._cleanup()
            finally:
                on_finished(error)
