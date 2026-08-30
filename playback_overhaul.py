from __future__ import annotations

import contextvars
import ctypes
import math
import os
import sys
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Literal

import midi_engine as me
import player as legacy_player
import profiles as profile_module
import suitability as suitability_module
import win_input as wi

ArticulationMode = Literal["musical", "balanced", "dense", "raw"]
SustainMode = Literal["native", "simulated", "off"]


@dataclass(frozen=True, slots=True)
class TimingProfile:
    musical_min_ms: int
    hard_floor_ms: int
    retrigger_gap_ms: int
    short_tail_ms: int
    control_tap_ms: int = 16


TIMING_PROFILES: dict[str, TimingProfile] = {
    "keyboard": TimingProfile(90, 40, 24, 20),
    "guitar": TimingProfile(105, 45, 26, 25),
    "bass": TimingProfile(120, 50, 28, 30),
}


@dataclass(slots=True)
class EnhancedPlanOptions:
    instrument: me.InstrumentCode = "keyboard"
    mode: me.PlaybackMode = "stable"
    speed_percent: int = 100
    note_length_percent: int = 100
    minimum_note_ms: int = 0
    repeated_release_gap_ms: int = 0
    octave_switch_lead_ms: int = 55
    page_switch_delay_ms: int = 220
    unlocked_min_pitch: int = me.GAME_MIN_PITCH
    unlocked_max_pitch: int = me.STABLE_MAX_PITCH
    unlock_tier: me.UnlockTier | None = None
    mapping_method: me.MappingMethod = "octave"
    max_notes_per_chord: int = 0
    use_sustain_pedal: bool = False
    ignore_percussion: bool = True
    melody_only: bool = False
    hard_press_floor_ms: int = 0
    short_note_tail_ms: int = 0
    articulation_mode: ArticulationMode = "balanced"
    sustain_mode: SustainMode = "native"
    attack_cluster_ms: int = 15

    def timing_profile(self) -> TimingProfile:
        return TIMING_PROFILES[self.instrument]

    @property
    def resolved_minimum_note_ms(self) -> int:
        return self.minimum_note_ms or self.timing_profile().musical_min_ms

    @property
    def resolved_release_gap_ms(self) -> int:
        return self.repeated_release_gap_ms or self.timing_profile().retrigger_gap_ms

    @property
    def resolved_hard_floor_ms(self) -> int:
        return self.hard_press_floor_ms or self.timing_profile().hard_floor_ms

    @property
    def resolved_short_tail_ms(self) -> int:
        return self.short_note_tail_ms or self.timing_profile().short_tail_ms

    @property
    def resolved_control_tap_ms(self) -> int:
        return self.timing_profile().control_tap_ms

    def validate(self) -> None:
        if self.instrument not in me.INSTRUMENT_UNLOCK_PROFILES:
            raise ValueError("Instrument must be keyboard, guitar, or bass.")
        if self.mode not in {"stable", "full", "ensemble"}:
            raise ValueError("Playback mode must be stable, full, or ensemble.")
        if not 25 <= self.speed_percent <= 200:
            raise ValueError("Speed must be between 25% and 200%.")
        if not 50 <= self.note_length_percent <= 300:
            raise ValueError("Note length must be between 50% and 300%.")
        if self.minimum_note_ms and not 20 <= self.minimum_note_ms <= 1000:
            raise ValueError("Minimum note length must be 0 (Auto) or 20-1000 ms.")
        if self.repeated_release_gap_ms and not 1 <= self.repeated_release_gap_ms <= 300:
            raise ValueError("Repeated-note release gap must be 0 (Auto) or 1-300 ms.")
        if self.hard_press_floor_ms and not 15 <= self.hard_press_floor_ms <= 500:
            raise ValueError("Hard press floor must be 0 (Auto) or 15-500 ms.")
        if self.short_note_tail_ms and not 1 <= self.short_note_tail_ms <= 250:
            raise ValueError("Short-note tail must be 0 (Auto) or 1-250 ms.")
        if not 10 <= self.octave_switch_lead_ms <= 500:
            raise ValueError("Octave switch lead must be between 10 and 500 ms.")
        if not 40 <= self.page_switch_delay_ms <= 1000:
            raise ValueError("Page switch delay must be between 40 and 1000 ms.")
        if self.unlock_tier is not None and self.unlock_tier not in me.INSTRUMENT_UNLOCK_PROFILES[self.instrument]:
            allowed = ", ".join(me.INSTRUMENT_UNLOCK_PROFILES[self.instrument])
            raise ValueError(f"Unlock tier for {self.instrument} must be one of: {allowed}.")
        if self.mapping_method not in {"octave", "nearest", "transpose", "skip"}:
            raise ValueError("Mapping method must be octave, nearest, transpose, or skip.")
        if not 0 <= self.max_notes_per_chord <= 12:
            raise ValueError("Maximum notes per chord must be between 0 and 12.")
        if not me.GAME_MIN_PITCH <= self.unlocked_min_pitch <= me.GAME_MAX_PITCH:
            raise ValueError("Unlocked minimum pitch is outside the game range.")
        if not me.GAME_MIN_PITCH <= self.unlocked_max_pitch <= me.GAME_MAX_PITCH:
            raise ValueError("Unlocked maximum pitch is outside the game range.")
        if self.unlocked_min_pitch > self.unlocked_max_pitch:
            raise ValueError("Unlocked minimum pitch must not exceed maximum pitch.")
        if self.articulation_mode not in {"musical", "balanced", "dense", "raw"}:
            raise ValueError("Articulation must be musical, balanced, dense, or raw.")
        if self.sustain_mode not in {"native", "simulated", "off"}:
            raise ValueError("Sustain mode must be native, simulated, or off.")
        if not 5 <= self.attack_cluster_ms <= 50:
            raise ValueError("Attack cluster must be between 5 and 50 ms.")
        if self.resolved_hard_floor_ms > self.resolved_minimum_note_ms and self.articulation_mode != "raw":
            raise ValueError("Hard press floor cannot exceed the musical minimum note length.")


@dataclass(slots=True)
class EnhancedMidiPlan:
    events: list[me.PlannedEvent]
    instrument: me.InstrumentCode
    duration: float
    mode: me.PlaybackMode
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
    unlock_tier: me.UnlockTier | None
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
    retrigger_compressed_notes: int = 0
    simulated_sustain_notes: int = 0
    attack_cluster_locks: int = 0
    active_tail_switch_avoids: int = 0
    articulation_mode: str = "balanced"
    sustain_mode: str = "off"
    timing_profile: str = ""


_legacy_build_plan = me.build_plan
_legacy_extract_notes_and_pedal = me._extract_notes_and_pedal
_legacy_evaluate_suitability = suitability_module.evaluate_song_suitability
_legacy_main: Any = None

_context_options: contextvars.ContextVar[EnhancedPlanOptions | None] = contextvars.ContextVar(
    "bpsr_overhaul_options", default=None
)
_context_metrics: contextvars.ContextVar[dict[str, int] | None] = contextvars.ContextVar(
    "bpsr_overhaul_metrics", default=None
)


def _coerce_options(options: Any | None) -> EnhancedPlanOptions:
    if options is None:
        return EnhancedPlanOptions()
    if isinstance(options, EnhancedPlanOptions):
        return options
    values: dict[str, Any] = {}
    for name in EnhancedPlanOptions.__dataclass_fields__:
        if hasattr(options, name):
            values[name] = getattr(options, name)
    return EnhancedPlanOptions(**values)


def _desired_note_duration(source_duration: float, options: EnhancedPlanOptions) -> float:
    source_duration = max(0.001, float(source_duration))
    scaled = source_duration * (options.note_length_percent / 100.0)
    floor = options.resolved_hard_floor_ms / 1000.0
    musical_min = options.resolved_minimum_note_ms / 1000.0
    tail = options.resolved_short_tail_ms / 1000.0
    if options.articulation_mode == "raw":
        return max(scaled, floor)
    if options.articulation_mode == "dense":
        effective_min = max(floor, musical_min * 0.70)
        tail_scale = 0.35
    elif options.articulation_mode == "musical":
        effective_min = musical_min
        tail_scale = 1.0
    else:
        effective_min = musical_min
        tail_scale = 0.75
    if source_duration < 0.120:
        compensated = scaled + tail * tail_scale
    elif source_duration < 0.250:
        compensated = scaled + tail * tail_scale * 0.5
    else:
        compensated = scaled
    return max(compensated, effective_min, floor)


def _enhanced_apply_note_lengths(notes: list[me.PlannedNote], options: Any) -> list[me.PlannedNote]:
    enhanced = _coerce_options(options)
    stretched = [
        replace(note, end=note.start + _desired_note_duration(max(0.001, note.end - note.start), enhanced))
        for note in notes
    ]
    stretched.sort(key=lambda item: (item.start, item.serial))
    return stretched


def _enhanced_resolve_retrigger_conflicts(
    notes: list[me.PlannedNote], options: Any
) -> tuple[list[me.PlannedNote], int, int]:
    enhanced = _coerce_options(options)
    hard_floor = enhanced.resolved_hard_floor_ms / 1000.0
    release_gap = enhanced.resolved_release_gap_ms / 1000.0
    impossible_cycle = hard_floor + release_gap
    musical_floor = hard_floor if enhanced.articulation_mode == "raw" else enhanced.resolved_minimum_note_ms / 1000.0
    by_key: dict[str, list[me.PlannedNote]] = defaultdict(list)
    for note in notes:
        by_key[note.key].append(note)
    resolved: list[me.PlannedNote] = []
    merged = dropped = compressed = 0
    for key_notes in by_key.values():
        kept: list[me.PlannedNote] = []
        for current in sorted(key_notes, key=lambda item: (item.start, item.serial)):
            if not kept:
                kept.append(current)
                continue
            previous = kept[-1]
            onset_interval = current.start - previous.start
            if onset_interval + 1e-9 < impossible_cycle:
                if current.pitch == previous.pitch and current.page == previous.page and current.octave == previous.octave:
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
                new_end = max(previous.start + hard_floor, latest_end)
                if new_end + 1e-9 < previous.start + musical_floor:
                    compressed += 1
                kept[-1] = replace(previous, end=new_end)
            kept.append(current)
        resolved.extend(kept)
    metrics = _context_metrics.get()
    if metrics is not None:
        metrics["retrigger_compressed_notes"] = compressed
    resolved.sort(key=lambda item: (item.start, item.serial))
    return resolved, merged, dropped


def _harmonic_importance(note: me.SourceNote, bass_pitch: int, top_pitch: int) -> float:
    interval = (note.pitch - bass_pitch) % 12
    harmonic = {0: 5.0, 7: 4.2, 3: 3.6, 4: 3.6, 10: 3.0, 11: 2.8, 5: 2.2, 9: 2.0}.get(interval, 1.0)
    duration = min(2.0, max(0.0, note.end - note.start) * 3.0)
    velocity = max(0.0, min(2.0, note.velocity / 64.0))
    return harmonic + duration + velocity + (8.0 if note.pitch == top_pitch else 0.0) + (8.0 if note.pitch == bass_pitch else 0.0)


def _enhanced_limit_notes_per_chord(
    notes: list[me.SourceNote], maximum: int, instrument: me.InstrumentCode = "keyboard"
) -> tuple[list[me.SourceNote], int]:
    if maximum <= 0:
        return notes, 0
    kept: list[me.SourceNote] = []
    removed = 0
    for group in me._group_notes_by_onset_window(notes):
        if len(group) <= maximum:
            kept.extend(group)
            continue
        ordered = sorted(group, key=lambda note: (note.pitch, note.serial))
        if instrument == "bass":
            selected = ordered[:maximum]
        elif maximum == 1:
            selected = [max(group, key=lambda note: (note.pitch, note.velocity, -note.serial))]
        else:
            bass_pitch = min(note.pitch for note in group)
            top_pitch = max(note.pitch for note in group)
            selected_by_serial: dict[int, me.SourceNote] = {}
            bass = min(group, key=lambda note: (note.pitch, -note.velocity, note.serial))
            top = max(group, key=lambda note: (note.pitch, note.velocity, -note.serial))
            selected_by_serial[bass.serial] = bass
            if len(selected_by_serial) < maximum:
                selected_by_serial[top.serial] = top
            candidates = [note for note in group if note.serial not in selected_by_serial]
            candidates.sort(
                key=lambda note: (_harmonic_importance(note, bass_pitch, top_pitch), note.pitch, note.velocity),
                reverse=True,
            )
            for note in candidates:
                if len(selected_by_serial) >= maximum:
                    break
                selected_by_serial[note.serial] = note
            selected = list(selected_by_serial.values())
        selected_serials = {note.serial for note in selected}
        kept.extend(note for note in group if note.serial in selected_serials)
        removed += len(group) - len(selected)
    kept.sort(key=lambda note: (note.start, note.serial))
    return kept, removed


def _apply_simulated_sustain(
    notes: list[me.SourceNote], pedal_events: list[tuple[float, bool]], final_time: float
) -> tuple[list[me.SourceNote], int]:
    if not notes or not pedal_events:
        return notes, 0
    intervals: list[tuple[float, float]] = []
    down_at: float | None = None
    for event_time, pedal_on in sorted(pedal_events):
        if pedal_on and down_at is None:
            down_at = event_time
        elif not pedal_on and down_at is not None:
            intervals.append((down_at, max(down_at, event_time)))
            down_at = None
    if down_at is not None:
        intervals.append((down_at, max(down_at, final_time)))
    changed = 0
    result: list[me.SourceNote] = []
    for note in notes:
        new_end = note.end
        for start, end in intervals:
            if start - 1e-9 <= note.end < end - 1e-9:
                new_end = max(new_end, end)
                break
        if new_end > note.end + 1e-9:
            changed += 1
            result.append(replace(note, end=new_end))
        else:
            result.append(note)
    return result, changed


def _enhanced_extract_notes_and_pedal(path: Path, ignore_percussion: bool):
    data = _legacy_extract_notes_and_pedal(path, ignore_percussion)
    notes, pedal_events, filtered, tracks, percussion, final_time = data
    options = _context_options.get()
    if options is None or not options.use_sustain_pedal:
        return data
    if options.sustain_mode == "off":
        return notes, [], filtered, tracks, percussion, final_time
    if options.sustain_mode == "simulated":
        notes, changed = _apply_simulated_sustain(notes, pedal_events, final_time)
        metrics = _context_metrics.get()
        if metrics is not None:
            metrics["simulated_sustain_notes"] = changed
        return notes, [], filtered, tracks, percussion, final_time
    return data


def _mapped_voice_pitch(mapped: me._MappedGroup, *, high: bool) -> int | None:
    pitches = [pitch for pitch in mapped.pitches if pitch is not None]
    return (max(pitches) if high else min(pitches)) if pitches else None


def _source_voice_pitch(group: list[me.SourceNote], *, high: bool) -> int:
    values = [note.pitch for note in group]
    return max(values) if high else min(values)


def _voice_continuity_cost(
    previous_group: list[me.SourceNote], previous_mapped: me._MappedGroup,
    current_group: list[me.SourceNote], current_mapped: me._MappedGroup,
    instrument: me.InstrumentCode,
) -> float:
    if instrument == "bass":
        return 0.0
    total = 0.0
    voices = ((True, 2.2), (False, 1.2 if instrument == "guitar" else 0.9))
    for high, weight in voices:
        prev_pitch = _mapped_voice_pitch(previous_mapped, high=high)
        cur_pitch = _mapped_voice_pitch(current_mapped, high=high)
        if prev_pitch is None or cur_pitch is None:
            continue
        source_interval = _source_voice_pitch(current_group, high=high) - _source_voice_pitch(previous_group, high=high)
        mapped_interval = cur_pitch - prev_pitch
        total += abs(mapped_interval - source_interval) * weight
        if source_interval and mapped_interval and source_interval * mapped_interval < 0:
            total += 18.0 * weight
        total += max(0, abs(mapped_interval) - 12) * 1.5 * weight
    return total


def _mapping_cost(mapped: me._MappedGroup, options: EnhancedPlanOptions) -> float:
    cost = me._mapping_cost(mapped, options)
    pitches = [pitch for pitch in mapped.pitches if pitch is not None]
    return cost + (len(pitches) - len(set(pitches))) * 12.0


def _predicted_group_tail(group: list[me.SourceNote], options: EnhancedPlanOptions) -> float:
    speed_ratio = options.speed_percent / 100.0
    group_start = group[0].start / speed_ratio
    tail = group_start
    for note in group:
        source_duration = max(0.001, (note.end - note.start) / speed_ratio)
        tail = max(tail, group_start + _desired_note_duration(source_duration, options))
    return tail


def _enhanced_choose_group_states(
    groups: list[list[me.SourceNote]], options: Any
) -> list[me._MappedGroup]:
    enhanced = _coerce_options(options)
    states = me._candidate_states(enhanced)
    global_low, global_high = me._global_range(enhanced)
    speed_ratio = enhanced.speed_percent / 100.0
    cluster_window = enhanced.attack_cluster_ms / 1000.0
    mapped_by_group: list[dict[me.KeyboardState, me._MappedGroup]] = []
    for group in groups:
        choices: dict[me.KeyboardState, me._MappedGroup] = {}
        for state in states:
            mapped = me._map_group(group, state, global_low, global_high, enhanced.mapping_method, enhanced.instrument)
            if mapped is not None:
                choices[state] = mapped
        if not choices:
            raise ValueError("A MIDI chord cannot be mapped to the configured keyboard range.")
        mapped_by_group.append(choices)
    initial = me._initial_state(enhanced)
    dp: list[dict[me.KeyboardState, tuple[float, me.KeyboardState | None]]] = []
    tails: list[float] = []
    running_tail = 0.0
    cluster_anchor = 0.0
    cluster_ids: list[int] = []
    cluster_id = -1
    for index, group in enumerate(groups):
        start = group[0].start / speed_ratio
        if index == 0 or start - cluster_anchor > cluster_window:
            cluster_id += 1
            cluster_anchor = start
        cluster_ids.append(cluster_id)
        tails.append(running_tail)
        running_tail = max(running_tail, _predicted_group_tail(group, enhanced))
    metrics = _context_metrics.get()
    for index, group in enumerate(groups):
        current_row: dict[me.KeyboardState, tuple[float, me.KeyboardState | None]] = {}
        current_start = group[0].start / speed_ratio
        previous_start = groups[index - 1][0].start / speed_ratio if index else 0.0
        onset_gap = max(0.0, current_start - previous_start)
        prior_tail = tails[index]
        for state, mapped in mapped_by_group[index].items():
            base_cost = _mapping_cost(mapped, enhanced)
            best_cost = float("inf")
            best_previous: me.KeyboardState | None = None
            if index == 0:
                best_cost = base_cost + me._transition_cost(initial, state, current_start, 0, enhanced)
            else:
                for previous_state, (previous_cost, _) in dp[index - 1].items():
                    changing = state.page != previous_state.page or state.octave != previous_state.octave
                    if changing and cluster_ids[index] == cluster_ids[index - 1]:
                        if metrics is not None:
                            metrics["attack_cluster_locks"] = metrics.get("attack_cluster_locks", 0) + 1
                        continue
                    page_steps = abs(state.page - previous_state.page)
                    octave_change = state.octave != previous_state.octave
                    required = 0.0
                    if enhanced.mode == "ensemble" and page_steps:
                        required += page_steps * enhanced.page_switch_delay_ms / 1000.0
                    if enhanced.mode in {"stable", "ensemble"} and octave_change:
                        required += enhanced.octave_switch_lead_ms / 1000.0
                    if required and current_start - prior_tail + 1e-9 < required + me.TRANSITION_AFTER_ONSET_GAP_SECONDS:
                        if metrics is not None:
                            metrics["active_tail_switch_avoids"] = metrics.get("active_tail_switch_avoids", 0) + 1
                        continue
                    transition = me._transition_cost(previous_state, state, onset_gap, index, enhanced)
                    if math.isinf(transition):
                        continue
                    transition += _voice_continuity_cost(
                        groups[index - 1], mapped_by_group[index - 1][previous_state], group, mapped, enhanced.instrument
                    )
                    total = previous_cost + base_cost + transition
                    if total < best_cost:
                        best_cost = total
                        best_previous = previous_state
            if best_cost < float("inf"):
                current_row[state] = (best_cost, best_previous)
        if not current_row:
            if index == 0:
                fallback_states = [state for state in states if state.page == 1]
            else:
                fallback_states = [state for state in states if state in dp[index - 1]]
            for state in fallback_states:
                mapped = mapped_by_group[index].get(state)
                if mapped is None:
                    continue
                if index == 0:
                    current_row[state] = (_mapping_cost(mapped, enhanced) + 100.0, None)
                else:
                    current_row[state] = (dp[index - 1][state][0] + _mapping_cost(mapped, enhanced) + 100.0, state)
        if not current_row:
            raise RuntimeError("No timing-safe keyboard state can represent this MIDI group.")
        dp.append(current_row)
    final_state = min(dp[-1], key=lambda state: dp[-1][state][0])
    selected = [final_state]
    for index in range(len(groups) - 1, 0, -1):
        previous = dp[index][selected[-1]][1]
        if previous is None:
            raise RuntimeError("Planner state reconstruction failed.")
        selected.append(previous)
    selected.reverse()
    return [mapped_by_group[index][state] for index, state in enumerate(selected)]


def _enhanced_build_notes_and_transitions(
    groups: list[list[me.SourceNote]], mapped_groups: list[me._MappedGroup], options: Any
):
    enhanced = _coerce_options(options)
    speed_ratio = enhanced.speed_percent / 100.0
    page_delay = enhanced.page_switch_delay_ms / 1000.0
    octave_lead = enhanced.octave_switch_lead_ms / 1000.0
    current_state = me._initial_state(enhanced)
    timeline_offset = added_delay = previous_group_start = active_tail_end = 0.0
    page_switches = octave_switches = 0
    notes: list[me.PlannedNote] = []
    transitions: list[me.PlannedEvent] = []
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
        earliest_transition = max(
            previous_group_start + (me.TRANSITION_AFTER_ONSET_GAP_SECONDS if index else 0.0),
            active_tail_end + (0.002 if index and total_lead else 0.0),
        )
        missing_lead = max(0.0, earliest_transition - (group_start - total_lead)) if total_lead else 0.0
        if missing_lead > 0:
            if enhanced.mode == "full" or index == 0:
                timeline_offset += missing_lead
                added_delay += missing_lead
                group_start += missing_lead
                offset_markers.append((source_start, timeline_offset))
            else:
                raise RuntimeError("Planner produced an unsafe active-note keyboard-state transition.")
        transition_start = max(0.0, group_start - total_lead, earliest_transition if index else 0.0)
        if page_steps:
            direction = 1 if target.page > current_state.page else -1
            for step_index in range(page_steps):
                transitions.append(me.PlannedEvent(
                    time=transition_start + step_index * page_delay,
                    priority=-30, kind="page",
                    page=current_state.page + direction * (step_index + 1),
                    serial=group[0].serial,
                ))
            page_switches += page_steps
        if state_change:
            state_time = max(transition_start + page_steps * page_delay, group_start - state_lead)
            transitions.append(me.PlannedEvent(
                time=state_time, priority=-20, kind="state", state=target.octave, serial=group[0].serial
            ))
            octave_switches += 1
        group_tail = active_tail_end
        for source_note, pitch in zip(group, mapped.pitches):
            if pitch is None:
                continue
            source_duration = max(0.001, (source_note.end - source_note.start) / speed_ratio)
            notes.append(me.PlannedNote(
                source_start=source_start, source_end=source_note.end / speed_ratio,
                start=group_start, end=group_start + source_duration,
                pitch=pitch, page=target.page, octave=target.octave,
                key=me.key_for_pitch(pitch, target), velocity=source_note.velocity, serial=source_note.serial,
            ))
            group_tail = max(group_tail, group_start + _desired_note_duration(source_duration, enhanced))
        active_tail_end = group_tail
        previous_group_start = group_start
        current_state = target
    notes.sort(key=lambda note: (note.start, note.serial))
    transitions.sort(key=lambda event: (event.time, event.priority, event.serial))
    offset_markers.sort()
    return notes, transitions, page_switches, octave_switches, added_delay, offset_markers


def enhanced_build_plan(path: str | Path, options: Any | None = None) -> EnhancedMidiPlan:
    enhanced = _coerce_options(options)
    enhanced.validate()
    metrics = {
        "retrigger_compressed_notes": 0,
        "simulated_sustain_notes": 0,
        "attack_cluster_locks": 0,
        "active_tail_switch_avoids": 0,
    }
    token_options = _context_options.set(enhanced)
    token_metrics = _context_metrics.set(metrics)
    try:
        plan = _legacy_build_plan(path, enhanced)
    finally:
        _context_options.reset(token_options)
        _context_metrics.reset(token_metrics)
    plan.retrigger_compressed_notes = metrics["retrigger_compressed_notes"]
    plan.simulated_sustain_notes = metrics["simulated_sustain_notes"]
    plan.attack_cluster_locks = metrics["attack_cluster_locks"]
    plan.active_tail_switch_avoids = metrics["active_tail_switch_avoids"]
    plan.articulation_mode = enhanced.articulation_mode
    plan.sustain_mode = enhanced.sustain_mode if enhanced.use_sustain_pedal else "off"
    plan.timing_profile = enhanced.instrument
    return plan


def enhanced_evaluate_song_suitability(plan: Any):
    base = _legacy_evaluate_suitability(plan)
    source_count = max(1, int(getattr(plan, "source_note_count", 1)))
    compressed = int(getattr(plan, "retrigger_compressed_notes", 0))
    merged = int(getattr(plan, "retrigger_merged_notes", 0))
    dropped = int(getattr(plan, "retrigger_dropped_notes", 0))
    retrigger_ratio = (compressed + merged + dropped) / source_count
    duration = max(float(getattr(plan, "duration", 0.0)), 0.001)
    octave_rate = float(getattr(plan, "octave_switches", 0)) / max(duration / 60.0, 0.001)
    score = int(base.score)
    reasons = list(base.reasons)
    if retrigger_ratio >= 0.15:
        score += 3
        reasons.append(f"high rapid-note pressure ({retrigger_ratio:.0%} compressed/merged/dropped)")
    elif retrigger_ratio >= 0.06:
        score += 2
        reasons.append(f"rapid-note pressure ({retrigger_ratio:.0%} compressed/merged/dropped)")
    elif retrigger_ratio >= 0.02:
        score += 1
        reasons.append(f"some rapid-note pressure ({retrigger_ratio:.0%})")
    if octave_rate >= 24:
        score += 2
        reasons.append(f"frequent Ctrl/Shift changes ({octave_rate:.1f}/min)")
    elif octave_rate >= 10:
        score += 1
        reasons.append(f"some Ctrl/Shift changes ({octave_rate:.1f}/min)")
    if score >= 7 or retrigger_ratio >= 0.25:
        code, label = "complex", "Very complex"
        summary = "Likely to need a simpler arrangement or Dense articulation in BPSR."
    elif score >= 3:
        code, label = "busy", "Busy"
        summary = "Playable, but timing/remap pressure may make parts sound crowded in-game."
    else:
        code, label = "good", "Good fit"
        summary = "Should translate cleanly with the selected instrument and timing profile."
    return suitability_module.SuitabilityResult(
        code=code, label=label, summary=summary, score=score,
        notes_per_second=base.notes_per_second, changed_ratio=base.changed_ratio,
        reasons=tuple(reasons),
    )


@dataclass(frozen=True, slots=True)
class _RuntimeAction:
    time: float
    priority: int
    kind: Literal["note_on", "note_off", "control_down", "control_up"]
    key: str
    serial: int = 0
    effect: str | None = None
    value: int | bool | None = None


def _input_event(sender: wi.WindowsKeySender, key: str, key_up: bool, use_scan_code: bool) -> wi.INPUT:
    virtual_key = sender._virtual_key(key)
    scan_code = sender._scan_code(key)
    flags = wi.KEYEVENTF_KEYUP if key_up else 0
    if use_scan_code:
        flags |= wi.KEYEVENTF_SCANCODE
        w_vk, w_scan = 0, scan_code
    else:
        w_vk, w_scan = virtual_key, 0
    return wi.INPUT(
        type=wi.INPUT_KEYBOARD,
        ki=wi.KEYBDINPUT(wVk=w_vk, wScan=w_scan, dwFlags=flags, time=0, dwExtraInfo=0),
    )


def _send_physical_batch(sender: Any, actions: list[tuple[str, bool]]) -> int:
    if not actions:
        return 0
    lock = getattr(sender, "_lock", None) or threading.RLock()
    with lock:
        held = set(getattr(sender, "_held", set()))
        effective: list[tuple[str, bool]] = []
        next_held = set(held)
        for key, key_down in actions:
            key = key.lower()
            if key_down:
                if key in next_held:
                    continue
                next_held.add(key)
            else:
                if key not in next_held:
                    continue
                next_held.discard(key)
            effective.append((key, key_down))
        if not effective:
            return 0
        backend = getattr(sender, "backend", "")
        if backend in {"scan", "virtual"} and os.name == "nt" and wi.user32 is not None:
            use_scan = backend == "scan"
            array_type = wi.INPUT * len(effective)
            array = array_type(*[
                _input_event(sender, key, key_up=not down, use_scan_code=use_scan)
                for key, down in effective
            ])
            ctypes.set_last_error(0)
            sent = wi.user32.SendInput(len(effective), array, ctypes.sizeof(wi.INPUT))
            if sent != len(effective):
                sender._raise_sendinput_error()
        else:
            for key, down in effective:
                if hasattr(sender, "_send"):
                    sender._send(key, key_up=not down)
                elif hasattr(sender, "events"):
                    sender.events.append((key, down))
                else:
                    raise RuntimeError("Input sender does not support batched events.")
        if hasattr(sender, "_held"):
            sender._held.clear()
            sender._held.update(next_held)
        return len(effective)


def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(len(ordered) * fraction) - 1))
    return ordered[index]


class EnhancedMidiPlayer(legacy_player.MidiPlayer):
    GROUP_WINDOW_SECONDS = 0.00075

    def __init__(self) -> None:
        super().__init__()
        self.last_timing_stats: dict[str, float] = {}
        self.last_timing_summary = ""
        self._control_tap_seconds = 0.016

    def start(self, plan: Any, *args: Any, **kwargs: Any) -> None:
        timing = TIMING_PROFILES.get(getattr(plan, "instrument", "keyboard"), TIMING_PROFILES["keyboard"])
        self._control_tap_seconds = timing.control_tap_ms / 1000.0
        self.last_timing_stats = {}
        self.last_timing_summary = ""
        super().start(plan, *args, **kwargs)

    def _expand_actions(self, plan: Any) -> list[_RuntimeAction]:
        actions: list[_RuntimeAction] = []
        predicted_page = 1
        predicted_state = 0
        predicted_pedal = False
        hold = self._control_tap_seconds
        for event in plan.events:
            if event.kind == "note_on" and event.key:
                actions.append(_RuntimeAction(event.time, 20, "note_on", event.key, event.serial))
            elif event.kind == "note_off" and event.key:
                actions.append(_RuntimeAction(event.time, 0, "note_off", event.key, event.serial))
            elif event.kind == "page" and event.page is not None and event.page != predicted_page:
                key = "." if event.page > predicted_page else ","
                actions.append(_RuntimeAction(event.time, event.priority, "control_down", key, event.serial, "page", event.page))
                actions.append(_RuntimeAction(event.time + hold, event.priority + 1, "control_up", key, event.serial))
                predicted_page = event.page
            elif event.kind == "state" and event.state is not None and event.state != predicted_state:
                if event.state == 1:
                    key = "shift"
                elif event.state == -1:
                    key = "ctrl"
                elif predicted_state == 1:
                    key = "shift"
                else:
                    key = "ctrl"
                actions.append(_RuntimeAction(event.time, event.priority, "control_down", key, event.serial, "state", event.state))
                actions.append(_RuntimeAction(event.time + hold, event.priority + 1, "control_up", key, event.serial))
                predicted_state = event.state
            elif event.kind == "pedal":
                desired = bool(event.pedal_on)
                if desired != predicted_pedal:
                    down_time = max(0.0, event.time - hold)
                    actions.append(_RuntimeAction(down_time, 9, "control_down", "space", event.serial, "pedal", desired))
                    actions.append(_RuntimeAction(event.time, 10, "control_up", "space", event.serial))
                    predicted_pedal = desired
        actions.sort(key=lambda action: (action.time, action.priority, action.serial))
        return actions

    def _handle_action_group(self, group: list[_RuntimeAction]) -> None:
        assert self.sender is not None
        physical: list[tuple[str, bool]] = []
        for action in group:
            if action.kind == "note_off":
                count = self._key_counts.get(action.key, 0)
                if count <= 1:
                    self._key_counts.pop(action.key, None)
                    if not self._keys_temporarily_released:
                        physical.append((action.key, False))
                else:
                    self._key_counts[action.key] = count - 1
            elif action.kind == "note_on":
                count = self._key_counts.get(action.key, 0)
                if count == 0 and not self._keys_temporarily_released:
                    physical.append((action.key, True))
                self._key_counts[action.key] = count + 1
            elif action.kind == "control_down":
                physical.append((action.key, True))
                if action.effect == "page" and isinstance(action.value, int):
                    self.current_page = action.value
                elif action.effect == "state" and isinstance(action.value, int):
                    self.current_state = action.value
                elif action.effect == "pedal":
                    self.pedal_on = bool(action.value)
            elif action.kind == "control_up":
                physical.append((action.key, False))
        _send_physical_batch(self.sender, physical)

    def _release_note_keys_for_pause(self) -> None:
        if self.sender is None or self._keys_temporarily_released:
            return
        held = list(getattr(self.sender, "_held", set()))
        _send_physical_batch(self.sender, [(key, False) for key in held])
        self._keys_temporarily_released = True

    def _restore_note_keys_after_pause(self) -> None:
        if self.sender is None or not self._keys_temporarily_released:
            return
        _send_physical_batch(self.sender, [(key, True) for key in self._key_counts])
        self._keys_temporarily_released = False

    def _finish_telemetry(self, lateness_ms: list[float]) -> None:
        if not lateness_ms:
            self.last_timing_stats = {}
            self.last_timing_summary = ""
            return
        stats = {
            "p50_ms": _percentile(lateness_ms, 0.50),
            "p95_ms": _percentile(lateness_ms, 0.95),
            "p99_ms": _percentile(lateness_ms, 0.99),
            "worst_ms": max(lateness_ms),
            "groups": float(len(lateness_ms)),
        }
        self.last_timing_stats = stats
        self.last_timing_summary = (
            f"Timing p50 {stats['p50_ms']:.2f} ms • p95 {stats['p95_ms']:.2f} ms • "
            f"p99 {stats['p99_ms']:.2f} ms • worst {stats['worst_ms']:.2f} ms"
        )

    def _run(self, plan: Any, start_delay: float, on_status: Any, on_finished: Any, input_backend: str = "scan") -> None:
        del input_backend
        error: str | None = None
        lateness_ms: list[float] = []
        try:
            countdown_end = time.perf_counter() + max(0.0, start_delay)
            while not self.stop_event.is_set():
                if self.pause_event.is_set():
                    countdown_end += self._pause_if_needed(on_status, 0.0)
                    continue
                remaining = countdown_end - time.perf_counter()
                if remaining <= 0:
                    break
                on_status(f"Starting in {remaining:.1f}s — switch to the game", 0.0)
                self.stop_event.wait(min(0.10, remaining))
            if self.stop_event.is_set():
                return
            self._capture_target_process()
            start = time.perf_counter()
            self._clock_started_at = start
            actions = self._expand_actions(plan)
            runtime_duration = max(float(plan.duration), actions[-1].time if actions else 0.0)
            self._clock_duration = max(0.0, runtime_duration)
            paused_total = 0.0
            total = max(float(plan.duration), 0.001)
            last_status_at = float("-inf")
            index = 0
            while index < len(actions) and not self.stop_event.is_set():
                anchor = actions[index].time
                group = [actions[index]]
                index += 1
                while index < len(actions) and actions[index].time - anchor <= self.GROUP_WINDOW_SECONDS:
                    group.append(actions[index])
                    index += 1
                while not self.stop_event.is_set():
                    if self.pause_event.is_set():
                        paused_total += self._pause_if_needed(on_status, min(1.0, self.position / total))
                        continue
                    if not self._target_has_focus():
                        paused_total += self._pause_for_focus(on_status, min(1.0, self.position / total))
                        continue
                    target = start + paused_total + anchor
                    if self._wait_until(target) and self._target_has_focus(force=True):
                        break
                if self.stop_event.is_set():
                    break
                target = start + paused_total + anchor
                lateness_ms.append(max(0.0, (time.perf_counter() - target) * 1000.0))
                self._handle_action_group(group)
                self.position = float(anchor)
                status_now = time.perf_counter()
                if status_now - last_status_at >= self.STATUS_INTERVAL_SECONDS or index >= len(actions):
                    on_status(
                        f"Playing {min(anchor, plan.duration):,.1f}s / {plan.duration:,.1f}s — F10 stops",
                        min(1.0, anchor / total),
                    )
                    last_status_at = status_now
            if not self.stop_event.is_set():
                self.position = float(plan.duration)
                on_status("Playback completed", 1.0)
        except Exception as exc:
            error = str(exc)
        finally:
            self._finish_telemetry(lateness_ms)
            try:
                self._cleanup()
            finally:
                self._clock_started_at = None
                self._clock_pause_started_at = None
                self._focus_guard_enabled = False
                self._target_process_id = None
                self._last_focus_check_at = 0.0
                self._last_focus_check_result = True
                on_finished(error)


def build_calibration_plan(instrument: str = "keyboard") -> EnhancedMidiPlan:
    if instrument not in TIMING_PROFILES:
        raise ValueError("Calibration instrument must be keyboard, guitar, or bass.")
    key = "q" if instrument == "bass" else "a"
    chord_keys = ("q", "i", "w", "o") if instrument == "bass" else ("a", "s", "d", "f")
    events: list[me.PlannedEvent] = []
    serial = 0
    cursor = 0.5
    for hold_ms in (20, 30, 40, 50, 60, 70, 80, 90, 110, 130):
        events.append(me.PlannedEvent(cursor, 20, "note_on", key=key, serial=serial))
        events.append(me.PlannedEvent(cursor + hold_ms / 1000.0, 0, "note_off", key=key, serial=serial))
        cursor += 0.50
        serial += 1
    cursor += 0.5
    for gap_ms in (8, 12, 16, 20, 24, 30, 40):
        for _ in range(2):
            events.append(me.PlannedEvent(cursor, 20, "note_on", key=key, serial=serial))
            events.append(me.PlannedEvent(cursor + 0.080, 0, "note_off", key=key, serial=serial))
            cursor += 0.080 + gap_ms / 1000.0
            serial += 1
        cursor += 0.35
    cursor += 0.5
    for chord_key in chord_keys:
        events.append(me.PlannedEvent(cursor, 20, "note_on", key=chord_key, serial=serial))
        events.append(me.PlannedEvent(cursor + 0.140, 0, "note_off", key=chord_key, serial=serial))
        serial += 1
    duration = cursor + 0.6
    events.sort(key=lambda event: (event.time, event.priority, event.serial))
    return EnhancedMidiPlan(
        events=events, instrument=instrument, duration=duration, mode="stable",
        note_count=serial, source_min_pitch=None, source_max_pitch=None,
        planned_min_pitch=None, planned_max_pitch=None, page_switches=0,
        octave_switches=0, folded_notes=0, remapped_notes=0, skipped_notes=0,
        merged_notes=0, retrigger_merged_notes=0, retrigger_dropped_notes=0,
        filtered_notes=0, transposed_semitones=0, added_delay=0.0,
        page_switch_delay=0.220, unlock_tier=None,
        configured_min_pitch=me.GAME_MIN_PITCH, configured_max_pitch=me.STABLE_MAX_PITCH,
        effective_min_pitch=me.GAME_MIN_PITCH, effective_max_pitch=me.STABLE_MAX_PITCH,
        source_note_count=serial, source_duration=duration, source_track_count=1,
        source_percussion_notes=0, max_source_chord=4, max_planned_chord=4,
        max_simultaneous_keys=4, chord_removed_notes=0,
        articulation_mode="raw", sustain_mode="off", timing_profile=instrument,
    )


def calibration_instructions(instrument: str) -> str:
    return (
        f"BPSR {instrument.title()} calibration: start in the normal Default instrument state.\n"
        "Segment 1: one note each at 20,30,40,50,60,70,80,90,110,130 ms hold.\n"
        "Segment 2: repeated-note release gaps 8,12,16,20,24,30,40 ms.\n"
        "Segment 3: one 4-note batched chord. Note the first values that sound clean/reliable."
    )


def _patch_fixed_profiles(app_module: Any) -> None:
    for instrument, profiles in profile_module.FIXED_PROFILES.items():
        timing = TIMING_PROFILES[instrument]
        for code, profile in list(profiles.items()):
            profiles[code] = replace(profile, minimum_note=timing.hard_floor_ms if code == "raw" else timing.musical_min_ms)
    for instrument, defaults in app_module.CUSTOM_DEFAULTS_BY_INSTRUMENT.items():
        timing = TIMING_PROFILES[instrument]
        defaults["minimum_note"] = timing.musical_min_ms
        defaults["release_gap"] = timing.retrigger_gap_ms
        defaults["articulation"] = "balanced"
        defaults["sustain_mode"] = "native"


def _patch_app_methods(app_module: Any) -> None:
    app_class = app_module.App
    if getattr(app_class, "_playback_overhaul_installed", False):
        return
    original_build_custom = app_class._build_custom_settings
    original_attach = app_class._attach_variable_traces
    original_capture = app_class._capture_settings
    original_apply = app_class._apply_settings
    original_plan_options = app_class._plan_options
    original_thread_finished = app_class._thread_finished

    def build_custom_settings(self: Any, settings: Any) -> None:
        if not hasattr(self, "release_gap_var"):
            self.release_gap_var = app_module.tk.IntVar(value=0)
            self.articulation_var = app_module.tk.StringVar(value="Balanced")
            self.sustain_mode_var = app_module.tk.StringVar(value="Native BPSR pedal")
        original_build_custom(self, settings)
        for child in settings.winfo_children():
            try:
                if child.cget("text") == "Use MIDI sustain-pedal events":
                    child.configure(text="Enable MIDI sustain")
            except Exception:
                pass
        app_module.ttk.Label(settings, text="Retrigger gap").grid(row=5, column=2, sticky="w", padx=(22, 8), pady=4)
        app_module.ttk.Spinbox(
            settings, from_=0, to=300, increment=1, textvariable=self.release_gap_var, width=7,
        ).grid(row=5, column=3, sticky="w")
        app_module.ttk.Label(settings, text="ms (0 = Auto)").grid(row=5, column=3, sticky="w", padx=(62, 0))
        app_module.ttk.Label(settings, text="Articulation").grid(row=7, column=0, sticky="w", pady=(7, 0))
        app_module.ttk.Combobox(
            settings, textvariable=self.articulation_var,
            values=("Musical", "Balanced", "Dense / Fast", "Raw MIDI"), state="readonly", width=18,
        ).grid(row=7, column=1, sticky="w", pady=(7, 0))
        app_module.ttk.Label(settings, text="Sustain behavior").grid(row=7, column=2, sticky="w", padx=(22, 8), pady=(7, 0))
        app_module.ttk.Combobox(
            settings, textvariable=self.sustain_mode_var,
            values=("Native BPSR pedal", "Simulated note hold", "Off"), state="readonly", width=20,
        ).grid(row=7, column=3, sticky="w", pady=(7, 0))

    def attach_variable_traces(self: Any) -> None:
        original_attach(self)
        for variable in (self.release_gap_var, self.articulation_var, self.sustain_mode_var):
            variable.trace_add("write", self._custom_variable_changed)

    def capture_settings(self: Any) -> dict[str, object]:
        data = original_capture(self)
        data.update({
            "release_gap": int(self.release_gap_var.get()),
            "articulation": {"Musical": "musical", "Balanced": "balanced", "Dense / Fast": "dense", "Raw MIDI": "raw"}.get(self.articulation_var.get(), "balanced"),
            "sustain_mode": {"Native BPSR pedal": "native", "Simulated note hold": "simulated", "Off": "off"}.get(self.sustain_mode_var.get(), "native"),
        })
        return data

    def apply_settings(self: Any, settings: dict[str, object]) -> None:
        original_apply(self, settings)
        timing = TIMING_PROFILES[self._instrument_code()]
        self.release_gap_var.set(int(settings.get("release_gap", timing.retrigger_gap_ms)))
        self.articulation_var.set({"musical": "Musical", "balanced": "Balanced", "dense": "Dense / Fast", "raw": "Raw MIDI"}.get(str(settings.get("articulation", "balanced")), "Balanced"))
        self.sustain_mode_var.set({"native": "Native BPSR pedal", "simulated": "Simulated note hold", "off": "Off"}.get(str(settings.get("sustain_mode", "native")), "Native BPSR pedal"))

    def plan_options(self: Any) -> EnhancedPlanOptions:
        legacy = original_plan_options(self)
        timing = TIMING_PROFILES[self._instrument_code()]
        profile_code = self._profile_code()
        if profile_code == "custom":
            articulation = {"Musical": "musical", "Balanced": "balanced", "Dense / Fast": "dense", "Raw MIDI": "raw"}.get(self.articulation_var.get(), "balanced")
            release_gap = int(self.release_gap_var.get())
            sustain_mode = {"Native BPSR pedal": "native", "Simulated note hold": "simulated", "Off": "off"}.get(self.sustain_mode_var.get(), "native")
        else:
            articulation = "raw" if profile_code == "raw" else "balanced"
            release_gap = timing.retrigger_gap_ms
            sustain_mode = "native"
        return EnhancedPlanOptions(
            instrument=legacy.instrument, mode=legacy.mode,
            speed_percent=legacy.speed_percent, note_length_percent=legacy.note_length_percent,
            minimum_note_ms=int(self.minimum_note_var.get()) or timing.musical_min_ms,
            repeated_release_gap_ms=release_gap,
            octave_switch_lead_ms=legacy.octave_switch_lead_ms,
            page_switch_delay_ms=legacy.page_switch_delay_ms,
            unlocked_min_pitch=legacy.unlocked_min_pitch, unlocked_max_pitch=legacy.unlocked_max_pitch,
            unlock_tier=legacy.unlock_tier, mapping_method=legacy.mapping_method,
            max_notes_per_chord=legacy.max_notes_per_chord,
            use_sustain_pedal=legacy.use_sustain_pedal, ignore_percussion=legacy.ignore_percussion,
            melody_only=legacy.melody_only, hard_press_floor_ms=timing.hard_floor_ms,
            short_note_tail_ms=timing.short_tail_ms, articulation_mode=articulation, sustain_mode=sustain_mode,
        )

    def thread_finished(self: Any, error: str | None) -> None:
        original_thread_finished(self, error)
        if error is None and getattr(self.player, "last_timing_summary", ""):
            self.ui_queue.put(("status", (self.player.last_timing_summary, 1.0)))

    app_class._build_custom_settings = build_custom_settings
    app_class._attach_variable_traces = attach_variable_traces
    app_class._capture_settings = capture_settings
    app_class._apply_settings = apply_settings
    app_class._plan_options = plan_options
    app_class._thread_finished = thread_finished
    app_class._playback_overhaul_installed = True


def _patch_main_for_calibration(app_module: Any) -> None:
    global _legacy_main
    if _legacy_main is None:
        _legacy_main = app_module.main
    if getattr(app_module, "_playback_calibration_cli_installed", False):
        return

    def main() -> int:
        if "--calibrate" not in sys.argv:
            return _legacy_main()
        index = sys.argv.index("--calibrate")
        instrument = sys.argv[index + 1].lower() if index + 1 < len(sys.argv) else "keyboard"
        if instrument not in TIMING_PROFILES:
            print("--calibrate accepts keyboard, guitar, or bass", file=sys.stderr)
            return 2
        if os.name != "nt":
            print("BPSR calibration playback is Windows-only.", file=sys.stderr)
            return 2
        print(calibration_instructions(instrument))
        plan = build_calibration_plan(instrument)
        player = EnhancedMidiPlayer()
        done = threading.Event()
        result: dict[str, str | None] = {"error": None}
        def status(text: str, _progress: float) -> None:
            print(text)
        def finished(error: str | None) -> None:
            result["error"] = error
            done.set()
        player.start(plan, 3.0, status, finished, input_backend="scan")
        while not done.wait(0.05):
            pass
        if result["error"]:
            print(f"Calibration failed: {result['error']}", file=sys.stderr)
            return 1
        if player.last_timing_summary:
            print(player.last_timing_summary)
        return 0

    app_module.main = main
    app_module._playback_calibration_cli_installed = True


def install_playback_overhaul(app_module: Any) -> None:
    if getattr(app_module, "_playback_overhaul_module_installed", False):
        return
    me.PlanOptions = EnhancedPlanOptions
    me.MidiPlan = EnhancedMidiPlan
    me._extract_notes_and_pedal = _enhanced_extract_notes_and_pedal
    me._limit_notes_per_chord = _enhanced_limit_notes_per_chord
    me._apply_note_lengths = _enhanced_apply_note_lengths
    me._resolve_retrigger_conflicts = _enhanced_resolve_retrigger_conflicts
    me._choose_group_states = _enhanced_choose_group_states
    me._build_notes_and_transitions = _enhanced_build_notes_and_transitions
    me.build_plan = enhanced_build_plan
    suitability_module.evaluate_song_suitability = enhanced_evaluate_song_suitability
    app_module.PlanOptions = EnhancedPlanOptions
    app_module.build_plan = enhanced_build_plan
    app_module.evaluate_song_suitability = enhanced_evaluate_song_suitability
    app_module.MidiPlayer = EnhancedMidiPlayer
    for name in ("online_ui", "online_integration", "online_search_bridge"):
        module = sys.modules.get(name)
        if module is None:
            continue
        if hasattr(module, "build_plan"):
            module.build_plan = enhanced_build_plan
        if hasattr(module, "evaluate_song_suitability"):
            module.evaluate_song_suitability = enhanced_evaluate_song_suitability
    _patch_fixed_profiles(app_module)
    _patch_app_methods(app_module)
    _patch_main_for_calibration(app_module)
    app_module._playback_overhaul_module_installed = True
