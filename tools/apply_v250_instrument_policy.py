from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"Expected text not found in {path}: {old[:120]!r}")
    p.write_text(text.replace(old, new, 1), encoding="utf-8")


# --- midi_engine.py -------------------------------------------------------
p = Path("midi_engine.py")
text = p.read_text(encoding="utf-8")

old = '''def _auto_transpose_notes(\n    notes: list[SourceNote],\n    low: int,\n    high: int,\n) -> tuple[list[SourceNote], int]:\n    """Choose one song-wide semitone shift before any local range handling.\n\n    A global transpose preserves intervals better than independently folding every\n    outlier. Remaining notes may still require the selected local mapping policy.\n    """\n    if not notes:\n        return notes, 0\n\n    best_shift = 0\n    best_score: tuple[int, int, int, float] | None = None\n    for shift in range(-36, 37):\n        outside_count = 0\n        outside_distance = 0\n        center_distance = 0.0\n        for note in notes:\n            value = note.pitch + shift\n            if value < low:\n                outside_count += 1\n                outside_distance += low - value\n            elif value > high:\n                outside_count += 1\n                outside_distance += value - high\n            center_distance += abs(value - ((low + high) / 2.0))\n\n        # Never change a song's key merely to center notes that already fit.\n        # First minimize outliers, then their distance, then the shift itself.\n        score = (outside_count, outside_distance, abs(shift), center_distance)\n        if best_score is None or score < best_score:\n            best_score = score\n            best_shift = shift\n\n    if best_shift == 0:\n        return notes, 0\n\n    shifted = [\n        SourceNote(\n            start=note.start,\n            end=note.end,\n            pitch=note.pitch + best_shift,\n            velocity=note.velocity,\n            serial=note.serial,\n        )\n        for note in notes\n    ]\n    return shifted, best_shift\n'''

new = '''def _auto_transpose_notes(\n    notes: list[SourceNote],\n    low: int,\n    high: int,\n    instrument: InstrumentCode = "keyboard",\n) -> tuple[list[SourceNote], int]:\n    """Choose one coherent song-wide shift before local range handling.\n\n    Piano keeps the established neutral policy. Guitar uses melody-aware\n    tie-breaking: when two shifts leave the same number/distance of outliers,\n    prefer the one that keeps the upper voice in range. Bass keeps the neutral\n    global shift because its local octave choice is handled by a contour-aware\n    pass below.\n    """\n    if not notes:\n        return notes, 0\n\n    guitar_weight_by_serial: dict[int, float] = {}\n    if instrument == "guitar":\n        for group in _group_notes_by_start(notes):\n            if not group:\n                continue\n            highest = max(note.pitch for note in group)\n            lowest = min(note.pitch for note in group)\n            for note in group:\n                if note.pitch == highest:\n                    guitar_weight_by_serial[note.serial] = 3.0\n                elif note.pitch == lowest and highest != lowest:\n                    guitar_weight_by_serial[note.serial] = 1.25\n                else:\n                    guitar_weight_by_serial[note.serial] = 1.0\n\n    best_shift = 0\n    best_score: tuple[float, ...] | None = None\n    for shift in range(-36, 37):\n        outside_count = 0\n        outside_distance = 0\n        weighted_outside = 0.0\n        weighted_distance = 0.0\n        center_distance = 0.0\n        for note in notes:\n            value = note.pitch + shift\n            distance = 0\n            if value < low:\n                outside_count += 1\n                distance = low - value\n            elif value > high:\n                outside_count += 1\n                distance = value - high\n            outside_distance += distance\n            if distance:\n                weight = guitar_weight_by_serial.get(note.serial, 1.0)\n                weighted_outside += weight\n                weighted_distance += distance * weight\n            center_distance += abs(value - ((low + high) / 2.0))\n\n        # Never increase the raw outlier count just to protect one voice. Guitar\n        # priority is a tie-breaker only, so the policy remains conservative.\n        if instrument == "guitar":\n            score = (\n                float(outside_count),\n                float(outside_distance),\n                weighted_outside,\n                weighted_distance,\n                float(abs(shift)),\n                center_distance,\n            )\n        else:\n            score = (\n                float(outside_count),\n                float(outside_distance),\n                float(abs(shift)),\n                center_distance,\n            )\n        if best_score is None or score < best_score:\n            best_score = score\n            best_shift = shift\n\n    if best_shift == 0:\n        return notes, 0\n\n    shifted = [\n        SourceNote(\n            start=note.start,\n            end=note.end,\n            pitch=note.pitch + best_shift,\n            velocity=note.velocity,\n            serial=note.serial,\n        )\n        for note in notes\n    ]\n    return shifted, best_shift\n\n\ndef _bass_octave_candidates(pitch: int, low: int, high: int) -> list[int]:\n    """Return every octave-equivalent pitch available in the Bass safe range."""\n    candidates = [value for value in range(low, high + 1) if value % 12 == pitch % 12]\n    if candidates:\n        return candidates\n    # Fixed Bass ranges are wider than one octave, so this is defensive only.\n    return [min(max(pitch, low), high)]\n\n\ndef _fit_bass_contour_notes(\n    notes: list[SourceNote],\n    low: int,\n    high: int,\n) -> tuple[list[SourceNote], int]:\n    """Octave-fit a monophonic Bass line while preserving its contour.\n\n    Bass normal profiles reduce simultaneous chords to the lowest note first.\n    When a remaining pitch is outside E1-B2/E1-B3, several octave-equivalent\n    notes can be legal. A small dynamic program chooses the sequence that avoids\n    register ping-pong, direction reversals, and unnecessarily high Bass notes.\n    Exact in-range pitches remain strongly preferred.\n    """\n    if not notes:\n        return notes, 0\n\n    ordered = sorted(notes, key=lambda note: (note.start, note.serial))\n    candidate_rows = [_bass_octave_candidates(note.pitch, low, high) for note in ordered]\n    dp: list[dict[int, tuple[float, int | None]]] = []\n\n    for index, (note, candidates) in enumerate(zip(ordered, candidate_rows)):\n        row: dict[int, tuple[float, int | None]] = {}\n        source_in_range = low <= note.pitch <= high\n        for candidate in candidates:\n            changed = candidate != note.pitch\n            local_cost = abs(candidate - note.pitch) * 2.0\n            if source_in_range and changed:\n                local_cost += 400.0\n            # Bass sounds more natural when equally-good octave choices stay low.\n            local_cost += (candidate - low) * 0.05\n\n            if index == 0:\n                row[candidate] = (local_cost, None)\n                continue\n\n            source_interval = note.pitch - ordered[index - 1].pitch\n            best: tuple[float, int | None] | None = None\n            for previous_candidate, (previous_cost, _) in dp[index - 1].items():\n                mapped_interval = candidate - previous_candidate\n                transition = abs(mapped_interval - source_interval) * 3.0\n                if source_interval and mapped_interval and source_interval * mapped_interval < 0:\n                    transition += 40.0\n                transition += max(0, abs(mapped_interval) - 12) * 8.0\n                total = previous_cost + local_cost + transition\n                if best is None or total < best[0]:\n                    best = (total, previous_candidate)\n            if best is not None:\n                row[candidate] = best\n        dp.append(row)\n\n    final_pitch = min(dp[-1], key=lambda pitch: dp[-1][pitch][0])\n    selected = [final_pitch]\n    for index in range(len(ordered) - 1, 0, -1):\n        previous = dp[index][selected[-1]][1]\n        if previous is None:\n            raise RuntimeError("Bass contour reconstruction failed.")\n        selected.append(previous)\n    selected.reverse()\n\n    changed_count = 0\n    fitted: list[SourceNote] = []\n    for note, pitch in zip(ordered, selected):\n        if pitch != note.pitch:\n            changed_count += 1\n        fitted.append(\n            SourceNote(\n                start=note.start,\n                end=note.end,\n                pitch=pitch,\n                velocity=note.velocity,\n                serial=note.serial,\n            )\n        )\n    return fitted, changed_count\n'''

if old not in text:
    raise SystemExit("_auto_transpose_notes block not found")
text = text.replace(old, new, 1)

old = '''class _MappedGroup:\n    state: KeyboardState\n    pitches: list[int | None]\n    folded_count: int\n    skipped_count: int\n    semitone_displacement: int\n'''
new = '''class _MappedGroup:\n    state: KeyboardState\n    pitches: list[int | None]\n    folded_count: int\n    skipped_count: int\n    semitone_displacement: int\n    priority_fold_penalty: float\n    priority_displacement: float\n'''
if old not in text:
    raise SystemExit("_MappedGroup block not found")
text = text.replace(old, new, 1)

old = '''def _map_group(\n    group: list[SourceNote],\n    state: KeyboardState,\n    global_low: int,\n    global_high: int,\n    mapping_method: MappingMethod,\n) -> _MappedGroup | None:\n'''
new = '''def _map_group(\n    group: list[SourceNote],\n    state: KeyboardState,\n    global_low: int,\n    global_high: int,\n    mapping_method: MappingMethod,\n    instrument: InstrumentCode = "keyboard",\n) -> _MappedGroup | None:\n'''
if old not in text:
    raise SystemExit("_map_group signature not found")
text = text.replace(old, new, 1)

old = '''    pitches: list[int | None] = []\n    folded = 0\n    skipped = 0\n    displacement = 0\n\n    for note in group:\n'''
new = '''    pitches: list[int | None] = []\n    folded = 0\n    skipped = 0\n    displacement = 0\n    priority_fold_penalty = 0.0\n    priority_displacement = 0.0\n\n    guitar_weight_by_serial: dict[int, float] = {}\n    if instrument == "guitar" and group:\n        highest = max(note.pitch for note in group)\n        lowest = min(note.pitch for note in group)\n        for note in group:\n            if note.pitch == highest:\n                guitar_weight_by_serial[note.serial] = 3.0\n            elif note.pitch == lowest and highest != lowest:\n                guitar_weight_by_serial[note.serial] = 1.25\n            else:\n                guitar_weight_by_serial[note.serial] = 1.0\n\n    for note in group:\n'''
if old not in text:
    raise SystemExit("_map_group counters not found")
text = text.replace(old, new, 1)

old = '''        pitches.append(effective)\n        if effective != note.pitch:\n            folded += 1\n        displacement += abs(effective - note.pitch)\n'''
new = '''        pitches.append(effective)\n        weight = guitar_weight_by_serial.get(note.serial, 1.0)\n        if effective != note.pitch:\n            folded += 1\n            priority_fold_penalty += weight\n        note_displacement = abs(effective - note.pitch)\n        displacement += note_displacement\n        priority_displacement += note_displacement * weight\n'''
if old not in text:
    raise SystemExit("_map_group accounting not found")
text = text.replace(old, new, 1)

old = '''    return _MappedGroup(\n        state=state,\n        pitches=pitches,\n        folded_count=folded,\n        skipped_count=skipped,\n        semitone_displacement=displacement,\n    )\n'''
new = '''    return _MappedGroup(\n        state=state,\n        pitches=pitches,\n        folded_count=folded,\n        skipped_count=skipped,\n        semitone_displacement=displacement,\n        priority_fold_penalty=priority_fold_penalty,\n        priority_displacement=priority_displacement,\n    )\n'''
if old not in text:
    raise SystemExit("_MappedGroup return not found")
text = text.replace(old, new, 1)

old = '''    return (\n        mapped.folded_count * fold_weight\n        + mapped.skipped_count * skip_weight\n        + mapped.semitone_displacement * displacement_weight\n    )\n'''
new = '''    cost = (\n        mapped.folded_count * fold_weight\n        + mapped.skipped_count * skip_weight\n        + mapped.semitone_displacement * displacement_weight\n    )\n    if options.instrument == "guitar":\n        # Same number of folds still has a musical preference: protect the upper\n        # voice/chord identity before inner accompaniment. The base fold count\n        # remains dominant, so this cannot casually trade one extra remap for it.\n        cost += mapped.priority_fold_penalty * 300.0\n        cost += mapped.priority_displacement * 1.5\n    return cost\n'''
if old not in text:
    raise SystemExit("_mapping_cost return not found")
text = text.replace(old, new, 1)

old = '''            mapped = _map_group(\n                group, state, global_low, global_high, options.mapping_method\n            )\n'''
new = '''            mapped = _map_group(\n                group,\n                state,\n                global_low,\n                global_high,\n                options.mapping_method,\n                options.instrument,\n            )\n'''
if old not in text:
    raise SystemExit("_map_group caller not found")
text = text.replace(old, new, 1)

old = '''    transposed_semitones = 0\n    pre_skipped_count = 0\n    if options.mapping_method == "transpose":\n        global_low, global_high = _global_range(options)\n        source_notes, transposed_semitones = _auto_transpose_notes(\n            source_notes, global_low, global_high\n        )\n'''
new = '''    transposed_semitones = 0\n    pre_skipped_count = 0\n    bass_contour_folds = 0\n    if options.mapping_method == "transpose":\n        global_low, global_high = _global_range(options)\n        source_notes, transposed_semitones = _auto_transpose_notes(\n            source_notes, global_low, global_high, options.instrument\n        )\n        if options.instrument == "bass":\n            source_notes, bass_contour_folds = _fit_bass_contour_notes(\n                source_notes, global_low, global_high\n            )\n'''
if old not in text:
    raise SystemExit("transpose build_plan block not found")
text = text.replace(old, new, 1)

old = '''    folded_count = sum(mapped.folded_count for mapped in mapped_groups)\n'''
new = '''    folded_count = bass_contour_folds + sum(\n        mapped.folded_count for mapped in mapped_groups\n    )\n'''
if old not in text:
    raise SystemExit("folded_count block not found")
text = text.replace(old, new, 1)

p.write_text(text, encoding="utf-8")

# --- profiles.py descriptions --------------------------------------------
replace_once(
    "profiles.py",
    'summary="Uses E2–B4 with stable whole-song fitting first, then only local octave adjustment when still needed.",',
    'summary="Uses E2–B4 with melody-aware fitting that protects the upper voice before local octave adjustment.",',
)
replace_once(
    "profiles.py",
    'summary="Uses the complete E2–D6 no-page range with stable whole-song fitting and automatic Ctrl/Shift switching.",',
    'summary="Uses E2–D6 with melody-aware chord fitting and automatic Ctrl/Shift switching.",',
)
replace_once(
    "profiles.py",
    'summary="Uses E1–B3 with stable whole-song fitting and switches High Octave automatically when needed.",',
    'summary="Uses the single E1–B3 High Octave layout with contour-aware Bass fitting; switches High once and stays there.",',
)

# --- tests ---------------------------------------------------------------
tests = Path("tests/test_engine.py")
t = tests.read_text(encoding="utf-8")
if "test_guitar_transpose_tie_protects_upper_voice" not in t:
    t += r'''


def _make_simultaneous_chord_midi(path: Path, pitches: list[int]) -> None:
    midi = mido.MidiFile(type=1, ticks_per_beat=480)
    track = mido.MidiTrack()
    track.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(120), time=0))
    for index, pitch in enumerate(pitches):
        track.append(mido.Message("note_on", note=pitch, velocity=80, time=120 if index == 0 else 0))
    for index, pitch in enumerate(pitches):
        track.append(mido.Message("note_off", note=pitch, velocity=0, time=120 if index == 0 else 0))
    midi.tracks.append(track)
    midi.save(path)


def test_guitar_transpose_tie_protects_upper_voice(tmp_path: Path) -> None:
    midi_path = tmp_path / "guitar_voice.mid"
    _make_simultaneous_chord_midi(midi_path, [48, 72])  # C3 + C5 around Cat 1 edge
    plan = build_plan(
        midi_path,
        PlanOptions(
            instrument="guitar",
            mode="stable",
            unlock_tier="tier1",
            mapping_method="transpose",
            max_notes_per_chord=0,
        ),
    )

    # Shift down one semitone so the upper voice remains at B4 instead of
    # octave-folding C5 to C4. The lower note takes the local octave adjustment.
    assert plan.transposed_semitones == -1
    assert plan.planned_max_pitch == 71
    assert plan.page_switches == 0


def test_keyboard_transpose_tie_keeps_established_neutral_policy(tmp_path: Path) -> None:
    midi_path = tmp_path / "keyboard_unchanged.mid"
    _make_simultaneous_chord_midi(midi_path, [48, 72])
    plan = build_plan(
        midi_path,
        PlanOptions(
            instrument="keyboard",
            mode="stable",
            unlock_tier="tier1",
            mapping_method="transpose",
            max_notes_per_chord=0,
        ),
    )

    assert plan.transposed_semitones == 0
    assert plan.page_switches == 0


def test_bass_category2_switches_high_once_and_stays_there(tmp_path: Path) -> None:
    midi_path = tmp_path / "bass_high_layout.mid"
    make_test_midi(midi_path, [28, 36, 47, 48, 52, 59], gap_ticks=240, duration_ticks=120)
    plan = build_plan(
        midi_path,
        PlanOptions(
            instrument="bass",
            mode="stable",
            unlock_tier="tier2",
            mapping_method="transpose",
            max_notes_per_chord=1,
        ),
    )

    state_events = [event for event in plan.events if event.kind == "state"]
    assert plan.page_switches == 0
    assert plan.octave_switches == 1
    assert len(state_events) == 1
    assert state_events[0].state == 1


def test_bass_contour_optimizer_preserves_descending_direction() -> None:
    from midi_engine import SourceNote, _fit_bass_contour_notes

    source = [
        SourceNote(start=index * 0.1, end=index * 0.1 + 0.08, pitch=pitch, velocity=80, serial=index)
        for index, pitch in enumerate([72, 71, 69, 67, 65, 64, 62, 60])
    ]
    fitted, changed = _fit_bass_contour_notes(source, 28, 59)
    pitches = [note.pitch for note in fitted]

    assert changed == len(source)
    assert pitches == [48, 47, 45, 43, 41, 40, 38, 36]
    assert all(later <= earlier for earlier, later in zip(pitches, pitches[1:]))
'''
    tests.write_text(t, encoding="utf-8")

# --- versions ------------------------------------------------------------
for filename in ("app.py", "modern_launcher.py", "build_exe.bat"):
    p = Path(filename)
    s = p.read_text(encoding="utf-8")
    if "2.4.2" not in s:
        raise SystemExit(f"2.4.2 version not found in {filename}")
    p.write_text(s.replace("2.4.2", "2.5.0"), encoding="utf-8")

p = Path("version_info.txt")
s = p.read_text(encoding="utf-8")
s = s.replace("(2, 4, 2, 0)", "(2, 5, 0, 0)").replace("2.4.2", "2.5.0")
p.write_text(s, encoding="utf-8")

# --- README / CHANGELOG --------------------------------------------------
replace_once(
    "README.md",
    "BPSR MIDI Lite converts normal MIDI notes into the game's keyboard controls, automatically fits notes to the selected unlock Category, uses stable whole-song fitting for Guitar/Bass before local octave adjustment, switches Ctrl/Shift octave modes when needed, and keeps playback inside the safe no-page range so normal profiles never press `<` or `>`.",
    "BPSR MIDI Lite converts normal MIDI notes into the game's keyboard controls, automatically fits notes to the selected unlock Category with instrument-aware musical priorities, switches Ctrl/Shift octave modes when needed, and keeps playback inside the safe no-page range so normal profiles never press `<` or `>`. Piano prioritizes pitch fidelity, Guitar protects the upper melody/chord voice, and Bass preserves the low-line contour.",
)
replace_once(
    "README.md",
    "Bass has no Low Octave mode; the player switches between Default and High only.",
    "Bass has no Low Octave mode. Category 1 uses the E1–B2 Default layout. Category 2 uses the single E1–B3 High Octave layout: the app switches High once at the start and stays there, avoiding mid-song Bass mode switching.",
)
insert = '''\n## Instrument-aware fitting\n\nNormal profiles use one planner but different hidden musical priorities for each BPSR instrument:\n\n- **Keyboard / Piano** — keeps the established fidelity-first behavior because the overlapping C2–B6 Default/Low/High layout already works well.\n- **Electric Guitar** — still minimizes total remapping first, then protects the upper melody/chord voice when equally-good transpose or octave choices exist. This suits the asymmetric E2–D6 Guitar layout without sacrificing extra notes just for the melody.\n- **Electric Bass** — keeps the lowest note from crowded chords and uses contour-aware octave selection so descending/ascending lines do not bounce between registers unnecessarily. Category 2 stays on the E1–B3 High layout for the whole performance.\n\nThese policies are automatic; there is no extra setting to configure.\n'''
readme = Path("README.md")
r = readme.read_text(encoding="utf-8")
marker = "\n## Raw MIDI — no remap\n"
if marker not in r:
    raise SystemExit("README Raw MIDI marker not found")
r = r.replace(marker, insert + marker, 1)
readme.write_text(r, encoding="utf-8")

changelog = Path("CHANGELOG.md")
c = changelog.read_text(encoding="utf-8")
entry = '''## v2.5.0\n\n- Added instrument-aware hidden fitting policies based on the confirmed in-game Piano, Guitar, and Bass layouts.\n- Kept Keyboard/Piano's established fidelity-first mapping unchanged.\n- Guitar now uses melody-aware tie-breaking: total remap count still wins first, then the upper melody/chord voice is protected when equally-good fitting choices exist.\n- Bass now uses contour-aware octave selection after its lowest-note chord reduction, reducing unnatural register ping-pong and direction reversals.\n- Confirmed Bass Category 2 uses one E1–B3 High Octave layout; playback switches High once and stays there instead of bouncing between Default/High.\n- Added regression tests for Guitar upper-voice preservation, unchanged Keyboard behavior, single-switch Bass Category 2 playback, and descending Bass contour preservation.\n- Kept safe no-page ranges, Raw MIDI behavior, key injection, BPSR timing, and the UI unchanged.\n\n'''
if "## v2.5.0" not in c:
    c = c.replace("# Changelog\n\n", "# Changelog\n\n" + entry, 1)
    changelog.write_text(c, encoding="utf-8")

print("Applied v2.5.0 instrument-aware fitting changes")
