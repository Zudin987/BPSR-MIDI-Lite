from __future__ import annotations

from bisect import bisect_right
from collections import defaultdict, deque
from collections.abc import Iterable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal

import mido

PlaybackMode = Literal["stable", "full", "ensemble"]
MappingMethod = Literal["octave", "nearest", "transpose", "skip"]
InstrumentCode = Literal["keyboard", "guitar", "bass"]
UnlockTier = Literal["tier1", "tier2", "tier3", "tier4"]

GAME_MIN_PITCH = 21   # A0
GAME_MAX_PITCH = 108  # C8
STABLE_MIN_PITCH = 36  # C2, middle page + Ctrl
STABLE_MAX_PITCH = 95  # B6, middle page + Shift
BASE_KEYBOARD_MIN = 48  # C3
BASE_KEYBOARD_MAX = 83  # B5
CHORD_ONSET_WINDOW_SECONDS = 0.015
MIN_PHYSICAL_PRESS_SECONDS = 0.020
TRANSITION_AFTER_ONSET_GAP_SECONDS = 0.005

PITCH_TO_KEY: dict[int, str] = {
    # C3-B3
    48: "z", 49: "1", 50: "x", 51: "2", 52: "c", 53: "v",
    54: "3", 55: "b", 56: "4", 57: "n", 58: "5", 59: "m",
    # C4-B4
    60: "a", 61: "6", 62: "s", 63: "7", 64: "d", 65: "f",
    66: "8", 67: "g", 68: "9", 69: "h", 70: "0", 71: "j",
    # C5-B5
    72: "q", 73: "i", 74: "w", 75: "o", 76: "e", 77: "r",
    78: "p", 79: "t", 80: "[", 81: "y", 82: "]", 83: "u",
}


@dataclass(frozen=True, slots=True)
class KeyboardState:
    page: int  # 0 left, 1 middle, 2 right
    octave: int  # -1 Ctrl, 0 Default, +1 Shift
    layout: str = "chromatic36"


@dataclass(frozen=True, slots=True)
class UnlockProfile:
    instrument: InstrumentCode
    code: UnlockTier
    label: str
    low: int
    high: int
    full_states: tuple[KeyboardState, ...]
    stable_states: tuple[KeyboardState, ...]


# Standard 36-key chromatic layout used by keyboard and guitar.
# Bass uses two instrument-specific layouts reconstructed from the in-game UI.
BASS_DEFAULT_PITCH_TO_KEY: dict[int, str] = {
    # In-game labels: E1-B2.
    28: "d", 29: "f", 30: "8", 31: "g", 32: "9", 33: "h",
    34: "0", 35: "j", 36: "q", 37: "i", 38: "w", 39: "o",
    40: "e", 41: "r", 42: "p", 43: "t", 44: "[", 45: "y",
    46: "]", 47: "u",
}

BASS_HIGH_PITCH_TO_KEY: dict[int, str] = {
    # In-game High Octave layout: E1-B3.
    28: "c", 29: "v", 30: "3", 31: "b", 32: "4", 33: "n",
    34: "5", 35: "m", 36: "a", 37: "6", 38: "s", 39: "7",
    40: "d", 41: "f", 42: "8", 43: "g", 44: "9", 45: "h",
    46: "0", 47: "j", 48: "q", 49: "i", 50: "w", 51: "o",
    52: "e", 53: "r", 54: "p", 55: "t", 56: "[", 57: "y",
    58: "]", 59: "u",
}


def _full_chromatic_states() -> tuple[KeyboardState, ...]:
    return tuple(
        KeyboardState(page, octave, "chromatic36")
        for page in (1, 0, 2)
        for octave in (0, -1, 1)
    )


INSTRUMENT_UNLOCK_PROFILES: dict[InstrumentCode, dict[UnlockTier, UnlockProfile]] = {
    "keyboard": {
        "tier1": UnlockProfile(
            instrument="keyboard", code="tier1", label="Tier 1 — C3–B4",
            low=48, high=71,
            full_states=(KeyboardState(1, 0),),
            stable_states=(KeyboardState(1, 0),),
        ),
        "tier2": UnlockProfile(
            instrument="keyboard", code="tier2", label="Tier 2 — C3–B6",
            low=48, high=95,
            full_states=(KeyboardState(1, 0), KeyboardState(1, 1)),
            stable_states=(KeyboardState(1, 0), KeyboardState(1, 1)),
        ),
        "tier3": UnlockProfile(
            instrument="keyboard", code="tier3", label="Tier 3 — C2–B6",
            low=36, high=95,
            full_states=(KeyboardState(1, -1), KeyboardState(1, 0), KeyboardState(1, 1)),
            stable_states=(KeyboardState(1, -1), KeyboardState(1, 0), KeyboardState(1, 1)),
        ),
        "tier4": UnlockProfile(
            instrument="keyboard", code="tier4", label="Category 4 safe playback — C2–B6",
            low=36, high=95,
            # Category 4 unlocks outer piano notes in-game, but playback stays
            # on the middle page so this selectable profile never uses < / >.
            full_states=(KeyboardState(1, -1), KeyboardState(1, 0), KeyboardState(1, 1)),
            stable_states=(KeyboardState(1, -1), KeyboardState(1, 0), KeyboardState(1, 1)),
        ),
    },
    "guitar": {
        "tier1": UnlockProfile(
            instrument="guitar", code="tier1", label="Tier 1 — C3–B4",
            low=48, high=71,
            full_states=(KeyboardState(1, 0),),
            stable_states=(KeyboardState(1, 0),),
        ),
        "tier2": UnlockProfile(
            instrument="guitar", code="tier2", label="Tier 2 — E2–B4",
            low=40, high=71,
            full_states=(KeyboardState(1, -1), KeyboardState(1, 0)),
            stable_states=(KeyboardState(1, -1), KeyboardState(1, 0)),
        ),
        "tier3": UnlockProfile(
            instrument="guitar", code="tier3", label="Tier 3 — E2–D6",
            low=40, high=86,
            full_states=(KeyboardState(1, -1), KeyboardState(1, 0), KeyboardState(1, 1)),
            stable_states=(KeyboardState(1, -1), KeyboardState(1, 0), KeyboardState(1, 1)),
        ),
        "tier4": UnlockProfile(
            instrument="guitar", code="tier4", label="Experimental full range — A0–C8",
            low=21, high=108,
            full_states=_full_chromatic_states(),
            stable_states=(KeyboardState(1, 0), KeyboardState(1, -1), KeyboardState(1, 1)),
        ),
    },
    "bass": {
        "tier1": UnlockProfile(
            instrument="bass", code="tier1", label="Tier 1 — E1–B2",
            low=28, high=47,
            full_states=(KeyboardState(1, 0, "bass_default"),),
            stable_states=(KeyboardState(1, 0, "bass_default"),),
        ),
        "tier2": UnlockProfile(
            instrument="bass", code="tier2", label="Tier 2 — E1–B3",
            low=28, high=59,
            # High Octave (Shift) exposes the entire E1-B3 bass layout.
            full_states=(KeyboardState(1, 1, "bass_high"),),
            stable_states=(KeyboardState(1, 1, "bass_high"),),
        ),
    },
}

# Backwards-compatible alias used by older code/tests.
UNLOCK_PROFILES = INSTRUMENT_UNLOCK_PROFILES["keyboard"]


def get_unlock_profile(
    code: UnlockTier,
    instrument: InstrumentCode = "keyboard",
) -> UnlockProfile:
    try:
        return INSTRUMENT_UNLOCK_PROFILES[instrument][code]
    except KeyError as exc:
        raise ValueError(f"Unknown {instrument} unlock tier: {code}") from exc


def available_unlock_tiers(instrument: InstrumentCode) -> tuple[UnlockTier, ...]:
    return tuple(INSTRUMENT_UNLOCK_PROFILES[instrument])


@dataclass(slots=True)
class SourceNote:
    start: float
    end: float
    pitch: int
    velocity: int
    serial: int


@dataclass(slots=True)
class PlannedNote:
    source_start: float
    source_end: float
    start: float
    end: float
    pitch: int
    page: int
    octave: int
    key: str
    velocity: int
    serial: int


@dataclass(slots=True)
class PlannedEvent:
    time: float
    priority: int
    kind: Literal["page", "state", "note_on", "note_off", "pedal"]
    key: str | None = None
    page: int | None = None
    state: int | None = None
    pedal_on: bool | None = None
    serial: int = 0


@dataclass(slots=True)
class MidiPlan:
    events: list[PlannedEvent]
    instrument: InstrumentCode
    duration: float
    mode: PlaybackMode
    note_count: int
    source_min_pitch: int | None
    source_max_pitch: int | None
    planned_min_pitch: int | None
    planned_max_pitch: int | None
    page_switches: int
    octave_switches: int
    folded_notes: int
    remapped_notes: int
    skipped_notes: int
    merged_notes: int
    retrigger_merged_notes: int
    retrigger_dropped_notes: int
    filtered_notes: int
    transposed_semitones: int
    added_delay: float
    page_switch_delay: float
    unlock_tier: UnlockTier | None
    configured_min_pitch: int
    configured_max_pitch: int
    effective_min_pitch: int
    effective_max_pitch: int
    source_note_count: int
    source_duration: float
    source_track_count: int
    source_percussion_notes: int
    max_source_chord: int
    max_planned_chord: int
    max_simultaneous_keys: int
    chord_removed_notes: int


@dataclass(slots=True)
class PlanOptions:
    instrument: InstrumentCode = "keyboard"
    mode: PlaybackMode = "stable"
    speed_percent: int = 100
    note_length_percent: int = 100
    minimum_note_ms: int = 70
    repeated_release_gap_ms: int = 16
    octave_switch_lead_ms: int = 55
    page_switch_delay_ms: int = 220
    unlocked_min_pitch: int = GAME_MIN_PITCH
    unlocked_max_pitch: int = STABLE_MAX_PITCH
    unlock_tier: UnlockTier | None = None
    mapping_method: MappingMethod = "octave"
    max_notes_per_chord: int = 0
    use_sustain_pedal: bool = False
    ignore_percussion: bool = True
    melody_only: bool = False  # backwards-compatible alias for max_notes_per_chord=1

    def validate(self) -> None:
        if self.instrument not in INSTRUMENT_UNLOCK_PROFILES:
            raise ValueError("Instrument must be keyboard, guitar, or bass.")
        if self.mode not in {"stable", "full", "ensemble"}:
            raise ValueError("Playback mode must be stable, full, or ensemble.")
        if not 25 <= self.speed_percent <= 200:
            raise ValueError("Speed must be between 25% and 200%.")
        if not 50 <= self.note_length_percent <= 300:
            raise ValueError("Note length must be between 50% and 300%.")
        if not 20 <= self.minimum_note_ms <= 1000:
            raise ValueError("Minimum note length must be between 20 and 1000 ms.")
        if not 1 <= self.repeated_release_gap_ms <= 300:
            raise ValueError("Repeated-note release gap must be between 1 and 300 ms.")
        if not 10 <= self.octave_switch_lead_ms <= 500:
            raise ValueError("Octave switch lead must be between 10 and 500 ms.")
        if not 40 <= self.page_switch_delay_ms <= 1000:
            raise ValueError("Page switch delay must be between 40 and 1000 ms.")
        if self.unlock_tier is not None:
            if self.unlock_tier not in INSTRUMENT_UNLOCK_PROFILES[self.instrument]:
                allowed = ", ".join(INSTRUMENT_UNLOCK_PROFILES[self.instrument])
                raise ValueError(
                    f"Unlock tier for {self.instrument} must be one of: {allowed}."
                )
        if self.mapping_method not in {"octave", "nearest", "transpose", "skip"}:
            raise ValueError("Mapping method must be octave, nearest, transpose, or skip.")
        if not 0 <= self.max_notes_per_chord <= 12:
            raise ValueError("Maximum notes per chord must be between 0 and 12.")
        if not GAME_MIN_PITCH <= self.unlocked_min_pitch <= GAME_MAX_PITCH:
            raise ValueError("Unlocked minimum pitch is outside the game range.")
        if not GAME_MIN_PITCH <= self.unlocked_max_pitch <= GAME_MAX_PITCH:
            raise ValueError("Unlocked maximum pitch is outside the game range.")
        if self.unlocked_min_pitch > self.unlocked_max_pitch:
            raise ValueError("Unlocked minimum pitch must not exceed maximum pitch.")


def fold_pitch_to_range(pitch: int, low: int, high: int) -> int:
    """Move a pitch by octaves until it is inside an inclusive range."""
    if low > high:
        raise ValueError("Invalid pitch range.")
    value = pitch
    while value < low:
        value += 12
    while value > high:
        value -= 12
    if not low <= value <= high:
        # This can only occur for an unusually narrow edge intersection.
        value = min(max(value, low), high)
    return value


def state_range(state: KeyboardState) -> tuple[int, int]:
    if state.page not in (0, 1, 2) or state.octave not in (-1, 0, 1):
        raise ValueError(f"Invalid keyboard state: {state}")
    if state.layout == "bass_default":
        return min(BASS_DEFAULT_PITCH_TO_KEY), max(BASS_DEFAULT_PITCH_TO_KEY)
    if state.layout == "bass_high":
        return min(BASS_HIGH_PITCH_TO_KEY), max(BASS_HIGH_PITCH_TO_KEY)
    if state.layout != "chromatic36":
        raise ValueError(f"Unknown key layout: {state.layout}")
    offset = (state.page - 1) * 36 + state.octave * 12
    return BASE_KEYBOARD_MIN + offset, BASE_KEYBOARD_MAX + offset


def key_for_pitch(pitch: int, state: KeyboardState) -> str:
    if state.layout == "bass_default":
        mapping = BASS_DEFAULT_PITCH_TO_KEY
        try:
            return mapping[pitch]
        except KeyError as exc:
            raise ValueError(f"Bass pitch {pitch} cannot be mapped in Default mode.") from exc
    if state.layout == "bass_high":
        mapping = BASS_HIGH_PITCH_TO_KEY
        try:
            return mapping[pitch]
        except KeyError as exc:
            raise ValueError(f"Bass pitch {pitch} cannot be mapped in High Octave mode.") from exc
    base_pitch = pitch - (state.page - 1) * 36 - state.octave * 12
    try:
        return PITCH_TO_KEY[base_pitch]
    except KeyError as exc:
        raise ValueError(f"Pitch {pitch} cannot be mapped in state {state}.") from exc



def _extract_notes_and_pedal(
    path: Path,
    ignore_percussion: bool,
) -> tuple[list[SourceNote], list[tuple[float, bool]], int, int, int, float]:
    midi = mido.MidiFile(path)
    source_track_count = 0
    source_percussion_notes = 0
    for track in midi.tracks:
        has_notes = False
        for track_message in track:
            if track_message.type == "note_on" and track_message.velocity > 0:
                has_notes = True
                if int(getattr(track_message, "channel", 0)) == 9:
                    source_percussion_notes += 1
        if has_notes:
            source_track_count += 1
    absolute_time = 0.0
    final_time = 0.0
    active: dict[tuple[int, int], deque[tuple[float, int, int]]] = defaultdict(deque)
    notes: list[SourceNote] = []
    pedal_events: list[tuple[float, bool]] = []
    serial = 0
    filtered = 0

    for message in midi:
        absolute_time += float(message.time)
        final_time = max(final_time, absolute_time)
        channel = int(getattr(message, "channel", 0))

        if ignore_percussion and channel == 9 and message.type in {"note_on", "note_off"}:
            if message.type == "note_on" and message.velocity > 0:
                filtered += 1
            continue

        if message.type == "note_on" and message.velocity > 0:
            active[(channel, int(message.note))].append(
                (absolute_time, int(message.velocity), serial)
            )
            serial += 1
        elif message.type == "note_off" or (
            message.type == "note_on" and message.velocity == 0
        ):
            queue = active[(channel, int(message.note))]
            if queue:
                start, velocity, note_serial = queue.popleft()
                notes.append(
                    SourceNote(
                        start=start,
                        end=max(start + 0.001, absolute_time),
                        pitch=int(message.note),
                        velocity=velocity,
                        serial=note_serial,
                    )
                )
        elif message.type == "control_change" and message.control == 64:
            pedal_events.append((absolute_time, message.value >= 64))

    # Gracefully close malformed/dangling notes instead of silently dropping them.
    for (_, pitch), queue in active.items():
        while queue:
            start, velocity, note_serial = queue.popleft()
            notes.append(
                SourceNote(
                    start=start,
                    end=max(start + 0.120, min(final_time, start + 0.500)),
                    pitch=pitch,
                    velocity=velocity,
                    serial=note_serial,
                )
            )

    notes.sort(key=lambda note: (note.start, note.serial))
    return (
        notes,
        pedal_events,
        filtered,
        source_track_count,
        source_percussion_notes,
        final_time,
    )


def _group_notes_by_start(notes: Iterable[SourceNote]) -> list[list[SourceNote]]:
    groups: list[list[SourceNote]] = []
    current_key: int | None = None
    for note in notes:
        key = round(note.start * 1_000_000)
        if current_key != key:
            groups.append([])
            current_key = key
        groups[-1].append(note)
    return groups


def _group_notes_by_onset_window(notes: Iterable[SourceNote]) -> list[list[SourceNote]]:
    """Cluster lightly-humanized chord attacks without chaining arpeggios.

    Each cluster is anchored to its first onset, so notes at 0, 10 and 20 ms
    cannot all become one chord through a rolling-window chain.
    """
    groups: list[list[SourceNote]] = []
    cluster_start: float | None = None
    for note in sorted(notes, key=lambda item: (item.start, item.serial)):
        if cluster_start is None or note.start - cluster_start > CHORD_ONSET_WINDOW_SECONDS:
            groups.append([])
            cluster_start = note.start
        groups[-1].append(note)
    return groups


def _limit_notes_per_chord(
    notes: list[SourceNote],
    maximum: int,
    instrument: InstrumentCode = "keyboard",
) -> tuple[list[SourceNote], int]:
    """Keep melody and bass while reducing chords that exceed ``maximum`` notes."""
    if maximum <= 0:
        return notes, 0

    kept: list[SourceNote] = []
    removed = 0
    for group in _group_notes_by_onset_window(notes):
        if len(group) <= maximum:
            kept.extend(group)
            continue

        ordered = sorted(group, key=lambda note: (note.pitch, note.velocity, -note.serial))
        if instrument == "bass":
            # Bass profiles should preserve the lowest line rather than the melody.
            selected = ordered[:maximum]
        elif maximum == 1:
            selected = [max(group, key=lambda note: (note.pitch, note.velocity, -note.serial))]
        else:
            # Preserve one bass note and use the remaining slots for the highest notes.
            bass = ordered[0]
            upper = sorted(
                ordered[1:],
                key=lambda note: (note.pitch, note.velocity, -note.serial),
                reverse=True,
            )[: maximum - 1]
            selected = [bass, *upper]

        selected_serials = {note.serial for note in selected}
        kept.extend(note for note in group if note.serial in selected_serials)
        removed += len(group) - len(selected)

    kept.sort(key=lambda note: (note.start, note.serial))
    return kept, removed


def _melody_only(notes: list[SourceNote]) -> tuple[list[SourceNote], int]:
    """Compatibility wrapper retained for older configs/tests."""
    return _limit_notes_per_chord(notes, 1)


def _auto_transpose_notes(
    notes: list[SourceNote],
    low: int,
    high: int,
    instrument: InstrumentCode = "keyboard",
) -> tuple[list[SourceNote], int]:
    """Choose one coherent song-wide shift before local range handling.

    Piano keeps the established neutral policy. Guitar uses melody-aware
    tie-breaking: when two shifts leave the same number/distance of outliers,
    prefer the one that keeps the upper voice in range. Bass keeps the neutral
    global shift because its local octave choice is handled by a contour-aware
    pass below.
    """
    if not notes:
        return notes, 0

    guitar_weight_by_serial: dict[int, float] = {}
    if instrument == "guitar":
        for group in _group_notes_by_start(notes):
            if not group:
                continue
            highest = max(note.pitch for note in group)
            lowest = min(note.pitch for note in group)
            for note in group:
                if note.pitch == highest:
                    guitar_weight_by_serial[note.serial] = 3.0
                elif note.pitch == lowest and highest != lowest:
                    guitar_weight_by_serial[note.serial] = 1.25
                else:
                    guitar_weight_by_serial[note.serial] = 1.0

    best_shift = 0
    best_score: tuple[float, ...] | None = None
    for shift in range(-36, 37):
        outside_count = 0
        outside_distance = 0
        weighted_outside = 0.0
        weighted_distance = 0.0
        center_distance = 0.0
        for note in notes:
            value = note.pitch + shift
            distance = 0
            if value < low:
                outside_count += 1
                distance = low - value
            elif value > high:
                outside_count += 1
                distance = value - high
            outside_distance += distance
            if distance:
                weight = guitar_weight_by_serial.get(note.serial, 1.0)
                weighted_outside += weight
                weighted_distance += distance * weight
            center_distance += abs(value - ((low + high) / 2.0))

        # Never increase the raw outlier count just to protect one voice. Guitar
        # priority is a tie-breaker only, so the policy remains conservative.
        if instrument == "guitar":
            score = (
                float(outside_count),
                float(outside_distance),
                weighted_outside,
                weighted_distance,
                float(abs(shift)),
                center_distance,
            )
        else:
            score = (
                float(outside_count),
                float(outside_distance),
                float(abs(shift)),
                center_distance,
            )
        if best_score is None or score < best_score:
            best_score = score
            best_shift = shift

    if best_shift == 0:
        return notes, 0

    shifted = [
        SourceNote(
            start=note.start,
            end=note.end,
            pitch=note.pitch + best_shift,
            velocity=note.velocity,
            serial=note.serial,
        )
        for note in notes
    ]
    return shifted, best_shift


def _bass_octave_candidates(pitch: int, low: int, high: int) -> list[int]:
    """Return every octave-equivalent pitch available in the Bass safe range."""
    candidates = [value for value in range(low, high + 1) if value % 12 == pitch % 12]
    if candidates:
        return candidates
    # Fixed Bass ranges are wider than one octave, so this is defensive only.
    return [min(max(pitch, low), high)]


def _fit_bass_contour_notes(
    notes: list[SourceNote],
    low: int,
    high: int,
) -> tuple[list[SourceNote], int]:
    """Octave-fit a monophonic Bass line while preserving its contour.

    Bass normal profiles reduce simultaneous chords to the lowest note first.
    When a remaining pitch is outside E1-B2/E1-B3, several octave-equivalent
    notes can be legal. A small dynamic program chooses the sequence that avoids
    register ping-pong, direction reversals, and unnecessarily high Bass notes.
    Exact in-range pitches remain strongly preferred.
    """
    if not notes:
        return notes, 0

    ordered = sorted(notes, key=lambda note: (note.start, note.serial))
    candidate_rows = [_bass_octave_candidates(note.pitch, low, high) for note in ordered]
    dp: list[dict[int, tuple[float, int | None]]] = []

    for index, (note, candidates) in enumerate(zip(ordered, candidate_rows)):
        row: dict[int, tuple[float, int | None]] = {}
        source_in_range = low <= note.pitch <= high
        for candidate in candidates:
            changed = candidate != note.pitch
            local_cost = abs(candidate - note.pitch) * 2.0
            if source_in_range and changed:
                local_cost += 400.0
            # Bass sounds more natural when equally-good octave choices stay low.
            local_cost += (candidate - low) * 0.05

            if index == 0:
                row[candidate] = (local_cost, None)
                continue

            source_interval = note.pitch - ordered[index - 1].pitch
            best: tuple[float, int | None] | None = None
            for previous_candidate, (previous_cost, _) in dp[index - 1].items():
                mapped_interval = candidate - previous_candidate
                transition = abs(mapped_interval - source_interval) * 6.0
                if source_interval and mapped_interval and source_interval * mapped_interval < 0:
                    transition += 120.0
                transition += max(0, abs(mapped_interval) - 7) * 12.0
                total = previous_cost + local_cost + transition
                if best is None or total < best[0]:
                    best = (total, previous_candidate)
            if best is not None:
                row[candidate] = best
        dp.append(row)

    final_pitch = min(dp[-1], key=lambda pitch: dp[-1][pitch][0])
    selected = [final_pitch]
    for index in range(len(ordered) - 1, 0, -1):
        previous = dp[index][selected[-1]][1]
        if previous is None:
            raise RuntimeError("Bass contour reconstruction failed.")
        selected.append(previous)
    selected.reverse()

    changed_count = 0
    fitted: list[SourceNote] = []
    for note, pitch in zip(ordered, selected):
        if pitch != note.pitch:
            changed_count += 1
        fitted.append(
            SourceNote(
                start=note.start,
                end=note.end,
                pitch=pitch,
                velocity=note.velocity,
                serial=note.serial,
            )
        )
    return fitted, changed_count


def _configured_range(options: PlanOptions) -> tuple[int, int]:
    if options.unlock_tier is not None:
        profile = get_unlock_profile(options.unlock_tier, options.instrument)
        return profile.low, profile.high
    return options.unlocked_min_pitch, options.unlocked_max_pitch


def _candidate_states(options: PlanOptions) -> list[KeyboardState]:
    if options.unlock_tier is not None:
        profile = get_unlock_profile(options.unlock_tier, options.instrument)
        return list(profile.stable_states if options.mode == "stable" else profile.full_states)

    # Custom ranges still respect each instrument's physical layout.
    if options.instrument == "bass":
        states = [
            KeyboardState(1, 0, "bass_default"),
            KeyboardState(1, 1, "bass_high"),
        ]
    elif options.mode == "stable":
        states = [KeyboardState(1, octave) for octave in (0, -1, 1)]
    else:
        states = list(_full_chromatic_states())

    usable: list[KeyboardState] = []
    for state in states:
        low, high = state_range(state)
        if max(low, options.unlocked_min_pitch) <= min(high, options.unlocked_max_pitch):
            usable.append(state)
    return usable


def _global_range(options: PlanOptions) -> tuple[int, int]:
    configured_low, configured_high = _configured_range(options)
    if options.mode != "stable":
        return configured_low, configured_high

    # Stable mode never leaves the middle page. Limit mapping to the union of
    # the middle-page states actually available at the selected unlock tier.
    states = _candidate_states(options)
    low = max(configured_low, min(state_range(state)[0] for state in states))
    high = min(configured_high, max(state_range(state)[1] for state in states))
    if low > high:
        raise ValueError("The selected unlock tier has no notes available in Stable mode.")
    return low, high


@dataclass(slots=True)
class _MappedGroup:
    state: KeyboardState
    pitches: list[int | None]
    folded_count: int
    skipped_count: int
    semitone_displacement: int
    priority_fold_penalty: float
    priority_displacement: float


def _map_group(
    group: list[SourceNote],
    state: KeyboardState,
    global_low: int,
    global_high: int,
    mapping_method: MappingMethod,
    instrument: InstrumentCode = "keyboard",
) -> _MappedGroup | None:
    state_low, state_high = state_range(state)
    low = max(state_low, global_low)
    high = min(state_high, global_high)
    if low > high:
        return None

    pitches: list[int | None] = []
    folded = 0
    skipped = 0
    displacement = 0
    priority_fold_penalty = 0.0
    priority_displacement = 0.0

    guitar_weight_by_serial: dict[int, float] = {}
    if instrument == "guitar" and group:
        highest = max(note.pitch for note in group)
        lowest = min(note.pitch for note in group)
        for note in group:
            if note.pitch == highest:
                guitar_weight_by_serial[note.serial] = 3.0
            elif note.pitch == lowest and highest != lowest:
                guitar_weight_by_serial[note.serial] = 1.25
            else:
                guitar_weight_by_serial[note.serial] = 1.0

    for note in group:
        if mapping_method == "skip":
            if not (global_low <= note.pitch <= global_high and low <= note.pitch <= high):
                pitches.append(None)
                skipped += 1
                continue
            effective = note.pitch
        elif mapping_method == "nearest":
            normalized = min(max(note.pitch, global_low), global_high)
            effective = min(max(normalized, low), high)
        else:
            # "octave" and "transpose" both use octave folding after any
            # optional song-wide transpose has already been applied.
            normalized = fold_pitch_to_range(note.pitch, global_low, global_high)
            effective = fold_pitch_to_range(normalized, low, high)

        pitches.append(effective)
        weight = guitar_weight_by_serial.get(note.serial, 1.0)
        if effective != note.pitch:
            folded += 1
            priority_fold_penalty += weight
        note_displacement = abs(effective - note.pitch)
        displacement += note_displacement
        priority_displacement += note_displacement * weight

    if all(pitch is None for pitch in pitches) and mapping_method != "skip":
        return None

    return _MappedGroup(
        state=state,
        pitches=pitches,
        folded_count=folded,
        skipped_count=skipped,
        semitone_displacement=displacement,
        priority_fold_penalty=priority_fold_penalty,
        priority_displacement=priority_displacement,
    )


def _mapping_cost(mapped: _MappedGroup, options: PlanOptions) -> float:
    # Full-range mode strongly prioritizes literal pitches; stable/ensemble still
    # prefer fewer folds but are willing to simplify to protect timing.
    fold_weight = 8000.0 if options.mode == "full" else 2500.0
    displacement_weight = 12.0 if options.mode == "full" else 6.0
    skip_weight = 5000.0 if options.mode == "ensemble" else 20_000.0
    cost = (
        mapped.folded_count * fold_weight
        + mapped.skipped_count * skip_weight
        + mapped.semitone_displacement * displacement_weight
    )
    if options.instrument == "guitar":
        # Same number of folds still has a musical preference: protect the upper
        # voice/chord identity before inner accompaniment. The base fold count
        # remains dominant, so this cannot casually trade one extra remap for it.
        cost += mapped.priority_fold_penalty * 20.0
        cost += mapped.priority_displacement * 0.25
    return cost


def _transition_cost(
    previous: KeyboardState,
    target: KeyboardState,
    group_gap: float,
    group_index: int,
    options: PlanOptions,
) -> float:
    page_steps = abs(target.page - previous.page)
    octave_change = target.octave != previous.octave

    if group_index > 0:
        required = 0.0
        if options.mode == "ensemble" and page_steps:
            required += page_steps * options.page_switch_delay_ms / 1000.0
        if options.mode in {"stable", "ensemble"} and octave_change:
            required += options.octave_switch_lead_ms / 1000.0
        # Timeline-preserving modes may only change physical keyboard state
        # when the authored gap already contains the required switch lead.
        # Otherwise the DP must remain in the current state and fold locally.
        if required:
            required += TRANSITION_AFTER_ONSET_GAP_SECONDS
            if group_gap + 1e-9 < required:
                return float("inf")

    page_weight = 12.0 if options.mode == "full" else 25.0
    cost = page_steps * page_weight
    if octave_change:
        cost += 2.0
    if target.page != previous.page:
        cost += 1.0
    else:
        cost -= 0.25  # prefer staying on the current page when mappings tie
    if target.octave == previous.octave:
        cost -= 0.05
    if target.page == 1:
        cost -= 0.10  # then prefer the middle page
    cost += abs(target.page - 1) * 0.001 + abs(target.octave) * 0.0001
    return cost


def _initial_state(options: PlanOptions) -> KeyboardState:
    if options.instrument == "bass":
        return KeyboardState(1, 0, "bass_default")
    return KeyboardState(1, 0, "chromatic36")


def _choose_group_states(
    groups: list[list[SourceNote]],
    options: PlanOptions,
) -> list[_MappedGroup]:
    states = _candidate_states(options)
    global_low, global_high = _global_range(options)
    speed_ratio = options.speed_percent / 100.0

    mapped_by_group: list[dict[KeyboardState, _MappedGroup]] = []
    for group in groups:
        choices: dict[KeyboardState, _MappedGroup] = {}
        for state in states:
            mapped = _map_group(
                group,
                state,
                global_low,
                global_high,
                options.mapping_method,
                options.instrument,
            )
            if mapped is not None:
                choices[state] = mapped
        if not choices:
            raise ValueError("A MIDI chord cannot be mapped to the configured keyboard range.")
        mapped_by_group.append(choices)

    initial = _initial_state(options)
    dp: list[dict[KeyboardState, tuple[float, KeyboardState | None]]] = []

    for index, group in enumerate(groups):
        current_row: dict[KeyboardState, tuple[float, KeyboardState | None]] = {}
        current_start = group[0].start / speed_ratio
        previous_start = groups[index - 1][0].start / speed_ratio if index else 0.0
        gap = max(0.0, current_start - previous_start)

        for state, mapped in mapped_by_group[index].items():
            base_cost = _mapping_cost(mapped, options)
            best_cost = float("inf")
            best_previous: KeyboardState | None = None

            if index == 0:
                transition = _transition_cost(initial, state, current_start, 0, options)
                best_cost = base_cost + transition
            else:
                for previous_state, (previous_cost, _) in dp[index - 1].items():
                    transition = _transition_cost(previous_state, state, gap, index, options)
                    total = previous_cost + base_cost + transition
                    if total < best_cost:
                        best_cost = total
                        best_previous = previous_state

            if best_cost < float("inf"):
                current_row[state] = (best_cost, best_previous)

        if not current_row:
            # Defensive fallback for an ensemble edge case: force the previous
            # page and let octave folding preserve the global timeline.
            if index == 0:
                fallback_states = [state for state in states if state.page == 1]
            else:
                fallback_pages = {state.page for state in dp[index - 1]}
                fallback_states = [state for state in states if state.page in fallback_pages]
            for state in fallback_states:
                mapped = mapped_by_group[index].get(state)
                if mapped is None:
                    continue
                if index == 0:
                    previous_cost, previous_state = 0.0, None
                else:
                    candidates = [
                        (cost_data[0], prev_state)
                        for prev_state, cost_data in dp[index - 1].items()
                        if prev_state.page == state.page
                    ]
                    if not candidates:
                        continue
                    previous_cost, previous_state = min(candidates, key=lambda item: item[0])
                current_row[state] = (
                    previous_cost + _mapping_cost(mapped, options) + 100.0,
                    previous_state,
                )

        dp.append(current_row)

    final_state = min(dp[-1], key=lambda state: dp[-1][state][0])
    selected_states: list[KeyboardState] = [final_state]
    for index in range(len(groups) - 1, 0, -1):
        previous = dp[index][selected_states[-1]][1]
        if previous is None:
            raise RuntimeError("Planner state reconstruction failed.")
        selected_states.append(previous)
    selected_states.reverse()

    return [
        mapped_by_group[index][state]
        for index, state in enumerate(selected_states)
    ]


def _build_notes_and_transitions(
    groups: list[list[SourceNote]],
    mapped_groups: list[_MappedGroup],
    options: PlanOptions,
) -> tuple[list[PlannedNote], list[PlannedEvent], int, int, float, list[tuple[float, float]]]:
    speed_ratio = options.speed_percent / 100.0
    page_delay = options.page_switch_delay_ms / 1000.0
    octave_lead = options.octave_switch_lead_ms / 1000.0

    current_state = _initial_state(options)
    timeline_offset = 0.0
    added_delay = 0.0
    previous_group_start = 0.0
    page_switches = 0
    octave_switches = 0
    notes: list[PlannedNote] = []
    transitions: list[PlannedEvent] = []
    # Markers map scaled source time to accumulated timeline offset. They are
    # later reused for sustain-pedal events.
    offset_markers: list[tuple[float, float]] = [(0.0, 0.0)]

    for index, (group, mapped) in enumerate(zip(groups, mapped_groups)):
        source_start = group[0].start / speed_ratio
        target = mapped.state
        page_steps = abs(target.page - current_state.page)
        state_change = target.octave != current_state.octave
        page_lead = page_steps * page_delay
        state_lead = octave_lead if state_change else 0.0
        total_lead = page_lead + state_lead

        group_start = source_start + timeline_offset
        earliest_transition = previous_group_start + (
            TRANSITION_AFTER_ONSET_GAP_SECONDS if index else 0.0
        )
        missing_lead = (
            max(0.0, earliest_transition - (group_start - total_lead))
            if total_lead
            else 0.0
        )

        if missing_lead > 0:
            if options.mode == "full" or index == 0:
                timeline_offset += missing_lead
                added_delay += missing_lead
                group_start += missing_lead
                offset_markers.append((source_start, timeline_offset))
            else:
                raise RuntimeError(
                    "Planner produced an unsafe mid-song keyboard-state transition."
                )

        transition_start = max(
            0.0,
            group_start - total_lead,
            earliest_transition if index else 0.0,
        )
        if page_steps:
            # Emit one page event per physical < / > press. Version 0.2 used
            # one event that could tap twice immediately when moving two pages,
            # even though the planner had reserved two animation delays.
            direction = 1 if target.page > current_state.page else -1
            for step_index in range(page_steps):
                intermediate_page = current_state.page + direction * (step_index + 1)
                transitions.append(
                    PlannedEvent(
                        time=transition_start + step_index * page_delay,
                        priority=-30,
                        kind="page",
                        page=intermediate_page,
                        serial=group[0].serial,
                    )
                )
            page_switches += page_steps

        if state_change:
            state_time = max(
                transition_start + page_steps * page_delay,
                group_start - state_lead,
            )
            transitions.append(
                PlannedEvent(
                    time=state_time,
                    priority=-20,
                    kind="state",
                    state=target.octave,
                    serial=group[0].serial,
                )
            )
            octave_switches += 1

        for source_note, pitch in zip(group, mapped.pitches):
            if pitch is None:
                continue
            source_duration = max(0.001, (source_note.end - source_note.start) / speed_ratio)
            notes.append(
                PlannedNote(
                    source_start=source_start,
                    source_end=source_note.end / speed_ratio,
                    start=group_start,
                    end=group_start + source_duration,
                    pitch=pitch,
                    page=target.page,
                    octave=target.octave,
                    key=key_for_pitch(pitch, target),
                    velocity=source_note.velocity,
                    serial=source_note.serial,
                )
            )

        previous_group_start = group_start
        current_state = target

    notes.sort(key=lambda note: (note.start, note.serial))
    transitions.sort(key=lambda event: (event.time, event.priority, event.serial))
    offset_markers.sort()
    return notes, transitions, page_switches, octave_switches, added_delay, offset_markers


def _merge_simultaneous_duplicates(notes: list[PlannedNote]) -> tuple[list[PlannedNote], int]:
    grouped: dict[tuple[int, int, int, int], list[PlannedNote]] = defaultdict(list)
    for note in notes:
        grouped[(round(note.start * 1_000_000), note.pitch, note.page, note.octave)].append(note)

    merged: list[PlannedNote] = []
    removed = 0
    for group in grouped.values():
        chosen = max(group, key=lambda item: (item.end, item.velocity, -item.serial))
        merged.append(
            PlannedNote(
                source_start=chosen.source_start,
                source_end=max(item.source_end for item in group),
                start=chosen.start,
                end=max(item.end for item in group),
                pitch=chosen.pitch,
                page=chosen.page,
                octave=chosen.octave,
                key=chosen.key,
                velocity=max(item.velocity for item in group),
                serial=chosen.serial,
            )
        )
        removed += len(group) - 1

    merged.sort(key=lambda note: (note.start, note.serial))
    return merged, removed


def _apply_note_lengths(notes: list[PlannedNote], options: PlanOptions) -> list[PlannedNote]:
    """Apply only the articulation correction BPSR actually needs.

    Valid MIDI note durations are musical information, so unrelated note
    onsets must never shorten them. The normal path preserves the authored
    duration and only raises genuinely short presses to ``minimum_note_ms``.
    Advanced users can still intentionally scale durations with
    ``note_length_percent``.

    Physical-key retrigger conflicts are resolved separately after stretching,
    so this function cannot create a mathematically valid but unplayable attack.
    """
    length_ratio = options.note_length_percent / 100.0
    minimum_duration = options.minimum_note_ms / 1000.0
    stretched: list[PlannedNote] = []
    for note in notes:
        original_duration = max(0.001, note.end - note.start)
        target_duration = max(original_duration * length_ratio, minimum_duration)
        stretched.append(
            PlannedNote(
                source_start=note.source_start,
                source_end=note.source_end,
                start=note.start,
                end=note.start + target_duration,
                pitch=note.pitch,
                page=note.page,
                octave=note.octave,
                key=note.key,
                velocity=note.velocity,
                serial=note.serial,
            )
        )

    stretched.sort(key=lambda note: (note.start, note.serial))
    return stretched


def _resolve_retrigger_conflicts(
    notes: list[PlannedNote],
    options: PlanOptions,
) -> tuple[list[PlannedNote], int, int]:
    """Make every retained physical-key attack representable in BPSR.

    Same-pitch attacks that arrive before a press+release cycle can complete
    become one sustained note. A different pitch mapped onto the same physical
    key is dropped rather than falsely counted as an attack that Windows will
    never send. No note timing is shifted.
    """
    release_gap = options.repeated_release_gap_ms / 1000.0
    minimum_cycle = MIN_PHYSICAL_PRESS_SECONDS + release_gap
    by_key: dict[str, list[PlannedNote]] = defaultdict(list)
    for note in notes:
        by_key[note.key].append(note)

    resolved: list[PlannedNote] = []
    merged = 0
    dropped = 0
    for key_notes in by_key.values():
        kept: list[PlannedNote] = []
        for current in sorted(key_notes, key=lambda note: (note.start, note.serial)):
            if not kept:
                kept.append(current)
                continue

            previous = kept[-1]
            if current.start - previous.start + 1e-9 < minimum_cycle:
                if (
                    current.pitch == previous.pitch
                    and current.page == previous.page
                    and current.octave == previous.octave
                ):
                    kept[-1] = replace(
                        previous,
                        source_end=max(previous.source_end, current.source_end),
                        end=max(previous.end, current.end),
                        velocity=max(previous.velocity, current.velocity),
                    )
                    merged += 1
                else:
                    dropped += 1
                continue

            latest_end = current.start - release_gap
            if previous.end > latest_end:
                kept[-1] = replace(
                    previous,
                    end=max(previous.start + MIN_PHYSICAL_PRESS_SECONDS, latest_end),
                )
            kept.append(current)
        resolved.extend(kept)

    resolved.sort(key=lambda note: (note.start, note.serial))
    return resolved, merged, dropped


def _maximum_simultaneous_keys(notes: list[PlannedNote]) -> int:
    events: list[tuple[float, int, str]] = []
    for note in notes:
        events.append((note.start, 1, note.key))
        events.append((note.end, 0, note.key))
    events.sort(key=lambda item: (item[0], item[1]))  # release before attack

    held: dict[str, int] = defaultdict(int)
    maximum = 0
    for _time, is_attack, key in events:
        if is_attack:
            held[key] += 1
        else:
            held[key] = max(0, held[key] - 1)
        maximum = max(maximum, sum(count > 0 for count in held.values()))
    return maximum

def _offset_for_source_time(markers: list[tuple[float, float]], source_time: float) -> float:
    times = [marker[0] for marker in markers]
    index = max(0, bisect_right(times, source_time) - 1)
    return markers[index][1]


def build_plan(path: str | Path, options: PlanOptions | None = None) -> MidiPlan:
    midi_path = Path(path)
    if not midi_path.exists():
        raise FileNotFoundError(midi_path)
    if midi_path.suffix.lower() not in {".mid", ".midi"}:
        raise ValueError("Please select a .mid or .midi file.")

    options = options or PlanOptions()
    options.validate()

    (
        source_notes,
        pedal_events,
        filtered_count,
        source_track_count,
        source_percussion_notes,
        source_duration,
    ) = _extract_notes_and_pedal(
        midi_path,
        options.ignore_percussion,
    )
    if not source_notes:
        raise ValueError("The MIDI file does not contain playable notes.")

    # Report the original musical range and complexity before simplification.
    source_min = min(note.pitch for note in source_notes)
    source_max = max(note.pitch for note in source_notes)
    source_note_count = len(source_notes)
    original_pitch_by_serial = {note.serial: note.pitch for note in source_notes}
    source_groups = _group_notes_by_onset_window(source_notes)
    max_source_chord = max((len(group) for group in source_groups), default=0)

    chord_limit = 1 if options.melody_only else options.max_notes_per_chord
    source_notes, chord_removed = _limit_notes_per_chord(source_notes, chord_limit, options.instrument)
    filtered_count += chord_removed

    transposed_semitones = 0
    pre_skipped_count = 0
    bass_contour_folds = 0
    if options.mapping_method == "transpose":
        global_low, global_high = _global_range(options)
        source_notes, transposed_semitones = _auto_transpose_notes(
            source_notes, global_low, global_high, options.instrument
        )
        if options.instrument == "bass":
            source_notes, bass_contour_folds = _fit_bass_contour_notes(
                source_notes, global_low, global_high
            )
    elif options.mapping_method == "skip":
        global_low, global_high = _global_range(options)
        in_range_notes = [
            note for note in source_notes if global_low <= note.pitch <= global_high
        ]
        pre_skipped_count = len(source_notes) - len(in_range_notes)
        source_notes = in_range_notes

    if not source_notes:
        raise ValueError("The selected filtering or mapping settings removed every note.")

    groups = _group_notes_by_start(source_notes)
    mapped_groups = _choose_group_states(groups, options)

    folded_count = bass_contour_folds + sum(
        mapped.folded_count for mapped in mapped_groups
    )
    skipped_count = pre_skipped_count + sum(
        mapped.skipped_count for mapped in mapped_groups
    )
    planned_notes, transitions, page_switches, octave_switches, added_delay, markers = (
        _build_notes_and_transitions(groups, mapped_groups, options)
    )
    planned_notes, merged_count = _merge_simultaneous_duplicates(planned_notes)
    planned_notes = _apply_note_lengths(planned_notes, options)
    planned_notes, retrigger_merged, retrigger_dropped = _resolve_retrigger_conflicts(
        planned_notes,
        options,
    )
    merged_count += retrigger_merged
    filtered_count += retrigger_dropped
    remapped_count = sum(
        1
        for note in planned_notes
        if original_pitch_by_serial.get(note.serial) != note.pitch
    )
    max_onset_chord = max(
        (len(group) for group in _group_notes_by_start(planned_notes)),
        default=0,
    )
    max_simultaneous_keys = _maximum_simultaneous_keys(planned_notes)
    max_planned_chord = max(max_onset_chord, max_simultaneous_keys)
    if not planned_notes:
        raise ValueError("The selected mapping method skipped every playable note.")

    events: list[PlannedEvent] = list(transitions)
    for note in planned_notes:
        events.append(
            PlannedEvent(
                time=note.end,
                priority=0,
                kind="note_off",
                key=note.key,
                serial=note.serial,
            )
        )
        events.append(
            PlannedEvent(
                time=note.start,
                priority=20,
                kind="note_on",
                key=note.key,
                serial=note.serial,
            )
        )

    if options.use_sustain_pedal:
        speed_ratio = options.speed_percent / 100.0
        last_pedal: bool | None = None
        for source_time, pedal_on in pedal_events:
            if pedal_on == last_pedal:
                continue
            last_pedal = pedal_on
            scaled = source_time / speed_ratio
            events.append(
                PlannedEvent(
                    time=scaled + _offset_for_source_time(markers, scaled),
                    priority=10,
                    kind="pedal",
                    pedal_on=pedal_on,
                )
            )

    events.sort(key=lambda event: (event.time, event.priority, event.serial))
    duration = max((event.time for event in events), default=0.0)
    planned_min = min(note.pitch for note in planned_notes)
    planned_max = max(note.pitch for note in planned_notes)

    configured_low, configured_high = _configured_range(options)
    effective_low, effective_high = _global_range(options)

    return MidiPlan(
        events=events,
        instrument=options.instrument,
        duration=duration,
        mode=options.mode,
        note_count=len(planned_notes),
        source_min_pitch=source_min,
        source_max_pitch=source_max,
        planned_min_pitch=planned_min,
        planned_max_pitch=planned_max,
        page_switches=page_switches,
        octave_switches=octave_switches,
        folded_notes=folded_count,
        remapped_notes=remapped_count,
        skipped_notes=skipped_count,
        merged_notes=merged_count,
        retrigger_merged_notes=retrigger_merged,
        retrigger_dropped_notes=retrigger_dropped,
        filtered_notes=filtered_count,
        transposed_semitones=transposed_semitones,
        added_delay=added_delay,
        page_switch_delay=options.page_switch_delay_ms / 1000.0,
        unlock_tier=options.unlock_tier,
        configured_min_pitch=configured_low,
        configured_max_pitch=configured_high,
        effective_min_pitch=effective_low,
        effective_max_pitch=effective_high,
        source_note_count=source_note_count,
        source_duration=source_duration,
        source_track_count=source_track_count,
        source_percussion_notes=source_percussion_notes,
        max_source_chord=max_source_chord,
        max_planned_chord=max_planned_chord,
        max_simultaneous_keys=max_simultaneous_keys,
        chord_removed_notes=chord_removed,
    )


def midi_note_name(pitch: int | None) -> str:
    if pitch is None:
        return "-"
    names = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
    octave = pitch // 12 - 1
    return f"{names[pitch % 12]}{octave}"
