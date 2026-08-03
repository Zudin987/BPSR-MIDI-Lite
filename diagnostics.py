from __future__ import annotations

import platform
from datetime import datetime
from typing import Any


def system_summary() -> str:
    system = platform.system() or "Unknown OS"
    release = platform.release() or "Unknown release"
    machine = platform.machine() or "Unknown architecture"
    return f"{system} {release} ({machine})"


def build_diagnostic_text(
    *,
    app_name: str,
    app_version: str,
    instrument: str,
    profile: str,
    input_backend: str,
    midi_name: str,
    administrator: bool,
    plan: Any | None,
    suitability: Any | None,
    last_input_test: str,
    last_error: str | None,
) -> str:
    lines = [
        f"{app_name} diagnostic report",
        f"Generated: {datetime.now().astimezone().isoformat(timespec='seconds')}",
        f"App version: {app_version}",
        f"OS: {system_summary()}",
        f"Access mode: {'Administrator' if administrator else 'Standard'}",
        f"Instrument: {instrument}",
        f"Profile: {profile}",
        f"Input method: {input_backend}",
        f"Selected MIDI: {midi_name or 'None'}",
        f"Last input test: {last_input_test}",
        f"Last error: {last_error or 'None'}",
    ]

    if plan is None:
        lines.append("Song analysis: Not available")
        return "\n".join(lines)

    source_range = f"{plan.source_min_pitch}-{plan.source_max_pitch}"
    played_range = f"{plan.planned_min_pitch}-{plan.planned_max_pitch}"
    lines.extend(
        [
            "",
            "Song analysis:",
            f"  Suitability: {getattr(suitability, 'label', 'Unknown')}",
            f"  Suitability reasons: {', '.join(getattr(suitability, 'reasons', ())) or 'None'}",
            f"  Note density: {getattr(suitability, 'notes_per_second', 0.0):.2f} notes/sec",
            f"  Changed-note ratio: {getattr(suitability, 'changed_ratio', 0.0):.1%}",
            f"  Played notes: {plan.note_count}",
            f"  Source notes: {plan.source_note_count}",
            f"  Duration: {plan.duration:.2f}s",
            f"  Source range (MIDI numbers): {source_range}",
            f"  Played range (MIDI numbers): {played_range}",
            f"  Source note tracks: {plan.source_track_count}",
            f"  Source percussion notes: {plan.source_percussion_notes}",
            f"  Largest source chord: {plan.max_source_chord}",
            f"  Largest played chord: {plan.max_planned_chord}",
            f"  Remapped/folded: {plan.folded_notes}",
            f"  Skipped: {plan.skipped_notes}",
            f"  Chord-filtered: {plan.chord_removed_notes}",
            f"  Other filtered/merged: {plan.filtered_notes + plan.merged_notes - plan.chord_removed_notes}",
            f"  Page-key presses: {plan.page_switches}",
            f"  Ctrl/Shift switches: {plan.octave_switches}",
            f"  Song transpose: {plan.transposed_semitones:+d} semitones",
        ]
    )
    return "\n".join(lines)
