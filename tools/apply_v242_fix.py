from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected exactly 1 match, got {count}: {old[:80]!r}")
    p.write_text(text.replace(old, new), encoding="utf-8")


# 1) Use the stable whole-song fitting strategy for Guitar/Bass higher categories.
replace_once(
    "profiles.py",
    'summary="Uses the cumulative safe range E2–B4 and automatically fits anything outside it.",\n            mode="stable", unlock_tier="tier2", mapping="octave", chord_limit=3,',
    'summary="Uses E2–B4 with stable whole-song fitting first, then only local octave adjustment when still needed.",\n            mode="stable", unlock_tier="tier2", mapping="transpose", chord_limit=3,',
)
replace_once(
    "profiles.py",
    'summary="Uses the complete no-page range E2–D6 with automatic Ctrl/Shift switching.",\n            mode="stable", unlock_tier="tier3", mapping="octave", chord_limit=0,',
    'summary="Uses the complete E2–D6 no-page range with stable whole-song fitting and automatic Ctrl/Shift switching.",\n            mode="stable", unlock_tier="tier3", mapping="transpose", chord_limit=0,',
)
replace_once(
    "profiles.py",
    'summary="Uses the complete safe E1–B3 range and switches High Octave automatically when needed.",\n            mode="stable", unlock_tier="tier2", mapping="octave", chord_limit=1,',
    'summary="Uses E1–B3 with stable whole-song fitting and switches High Octave automatically when needed.",\n            mode="stable", unlock_tier="tier2", mapping="transpose", chord_limit=1,',
)

# 2) Track the real number of played notes whose pitch differs from the source.
replace_once(
    "midi_engine.py",
    '    folded_notes: int\n    skipped_notes: int\n',
    '    folded_notes: int\n    remapped_notes: int\n    skipped_notes: int\n',
)
replace_once(
    "midi_engine.py",
    '    source_note_count = len(source_notes)\n    source_groups = _group_notes_by_start(source_notes)\n',
    '    source_note_count = len(source_notes)\n    original_pitch_by_serial = {note.serial: note.pitch for note in source_notes}\n    source_groups = _group_notes_by_start(source_notes)\n',
)
replace_once(
    "midi_engine.py",
    '    planned_notes, merged_count = _merge_simultaneous_duplicates(planned_notes)\n    max_planned_chord = max(\n',
    '    planned_notes, merged_count = _merge_simultaneous_duplicates(planned_notes)\n    remapped_count = sum(\n        1\n        for note in planned_notes\n        if original_pitch_by_serial.get(note.serial) != note.pitch\n    )\n    max_planned_chord = max(\n',
)
replace_once(
    "midi_engine.py",
    '        folded_notes=folded_count,\n        skipped_notes=skipped_count,\n',
    '        folded_notes=folded_count,\n        remapped_notes=remapped_count,\n        skipped_notes=skipped_count,\n',
)

# 3) Show true remap count and explain coherent whole-song shifts in Song Check.
replace_once(
    "modern_ui.py",
    '    remapped = 0 if self._profile_code() == "raw" else plan.folded_notes\n    metrics = f"Remapped: {remapped:,} • Skipped: {plan.skipped_notes:,} • Filtered/simplified: {plan.filtered_notes:,}"\n',
    '    remapped = plan.remapped_notes\n    metrics = f"Remapped: {remapped:,} • Skipped: {plan.skipped_notes:,} • Filtered/simplified: {plan.filtered_notes:,}"\n',
)
replace_once(
    "modern_ui.py",
    '    elif remapped:\n        explanation = "Remapped notes were moved into the range available for your selected category."\n    else:\n',
    '    elif plan.transposed_semitones:\n        direction = "+" if plan.transposed_semitones > 0 else ""\n        explanation = (\n            f"Whole-song shift: {direction}{plan.transposed_semitones} semitones to fit this category. "\n            "This keeps the song intervals together; any remaining local fitting is minimized."\n        )\n    elif remapped:\n        explanation = "Remapped notes were moved into the range available for your selected category."\n    else:\n',
)

# 4) Keep legacy analysis/dry-run terminology accurate too.
replace_once(
    "app.py",
    '        if plan.folded_notes:\n            changes.append(f"{plan.folded_notes:,} remapped")\n',
    '        if plan.remapped_notes:\n            changes.append(f"{plan.remapped_notes:,} remapped")\n',
)
replace_once(
    "app.py",
    '    print(f"Remapped/folded notes: {plan.folded_notes}")\n',
    '    print(f"Remapped notes: {plan.remapped_notes}")\n    print(f"Local octave-folded notes: {plan.folded_notes}")\n',
)

# 5) Regression coverage.
profiles_test = Path("tests/test_profiles.py")
text = profiles_test.read_text(encoding="utf-8")
text += '''\n\ndef test_guitar_and_bass_higher_categories_use_stable_whole_song_fit() -> None:\n    assert get_fixed_profile("guitar", "tier1").mapping == "transpose"\n    assert get_fixed_profile("guitar", "tier2").mapping == "transpose"\n    assert get_fixed_profile("guitar", "tier3").mapping == "transpose"\n    assert get_fixed_profile("bass", "tier1").mapping == "transpose"\n    assert get_fixed_profile("bass", "tier2").mapping == "transpose"\n'''
profiles_test.write_text(text, encoding="utf-8")

engine_test = Path("tests/test_engine.py")
text = engine_test.read_text(encoding="utf-8")
text += '''\n\ndef _plan_fixed_profile(path: Path, instrument: str, code: str):\n    from profiles import get_fixed_profile\n\n    profile = get_fixed_profile(instrument, code)\n    return build_plan(\n        path,\n        PlanOptions(\n            instrument=instrument,\n            mode=profile.mode,\n            unlock_tier=profile.unlock_tier,\n            mapping_method=profile.mapping,\n            max_notes_per_chord=profile.chord_limit,\n            speed_percent=100,\n            note_length_percent=100,\n        ),\n    )\n\n\ndef test_remapped_count_includes_whole_song_transpose(tmp_path: Path) -> None:\n    midi_path = tmp_path / "global_shift.mid"\n    make_test_midi(midi_path, [72, 76, 79], gap_ticks=240, duration_ticks=120)\n    plan = build_plan(\n        midi_path,\n        PlanOptions(\n            mode="stable",\n            mapping_method="transpose",\n            unlocked_min_pitch=48,\n            unlocked_max_pitch=71,\n            speed_percent=100,\n        ),\n    )\n    assert plan.transposed_semitones != 0\n    assert plan.folded_notes == 0\n    assert plan.remapped_notes == 3\n\n\ndef test_guitar_unlocks_reduce_or_hold_local_pitch_distortion(tmp_path: Path) -> None:\n    midi_path = tmp_path / "guitar_progression.mid"\n    make_test_midi(midi_path, [40, 43, 47, 52, 55, 59, 64, 67, 71, 76, 79, 83], gap_ticks=240)\n    tier1 = _plan_fixed_profile(midi_path, "guitar", "tier1")\n    tier2 = _plan_fixed_profile(midi_path, "guitar", "tier2")\n    tier3 = _plan_fixed_profile(midi_path, "guitar", "tier3")\n    assert tier2.folded_notes <= tier1.folded_notes\n    assert tier3.folded_notes <= tier2.folded_notes\n    assert tier1.page_switches == tier2.page_switches == tier3.page_switches == 0\n\n\ndef test_bass_unlocks_reduce_or_hold_local_pitch_distortion(tmp_path: Path) -> None:\n    midi_path = tmp_path / "bass_progression.mid"\n    make_test_midi(midi_path, [28, 31, 35, 40, 43, 47, 52, 55, 59, 64], gap_ticks=240)\n    tier1 = _plan_fixed_profile(midi_path, "bass", "tier1")\n    tier2 = _plan_fixed_profile(midi_path, "bass", "tier2")\n    assert tier2.folded_notes <= tier1.folded_notes\n    assert tier1.page_switches == tier2.page_switches == 0\n'''
engine_test.write_text(text, encoding="utf-8")

replace_once(
    "tests/test_ui_contract.py",
    '    assert "Remapped:" in source\n',
    '    assert "Remapped:" in source\n    assert "plan.remapped_notes" in source\n    assert "Whole-song shift:" in source\n',
)

# 6) Version/docs.
for path in ("app.py", "modern_launcher.py", "build_exe.bat", "version_info.txt"):
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    text = text.replace("2.4.1", "2.4.2")
    if path == "version_info.txt":
        text = text.replace("(2, 4, 1, 0)", "(2, 4, 2, 0)")
    p.write_text(text, encoding="utf-8")

changelog = Path("CHANGELOG.md")
text = changelog.read_text(encoding="utf-8")
entry = '''# Changelog\n\n## v2.4.2\n\n- Fixed Guitar/Bass higher Categories using a less stable per-note octave-folding strategy than their lower Categories.\n- Guitar Categories 1–3 and Bass Categories 1–2 now use the same stable whole-song fitting strategy before any unavoidable local octave adjustment.\n- Kept Keyboard profile behavior unchanged because its current Category progression is already stable in testing.\n- Added a true **Remapped** count that includes whole-song transposition as well as local pitch fitting.\n- Song Check now explains whole-song semitone shifts separately so a coherent transposition is not confused with unstable per-note folding.\n- Kept suitability focused on local distortion/removal rather than penalizing a coherent whole-song key shift as if it were crowding.\n- Added Guitar/Bass progression regressions ensuring larger unlock ranges do not increase local pitch-fold distortion on representative melodies.\n\n'''
if not text.startswith("# Changelog\n\n"):
    raise SystemExit("Unexpected changelog header")
changelog.write_text(entry + text[len("# Changelog\n\n"):], encoding="utf-8")

readme = Path("README.md")
text = readme.read_text(encoding="utf-8")
text = text.replace(
    "automatically fits notes to the selected unlock Category, switches Ctrl/Shift octave modes when needed,",
    "automatically fits notes to the selected unlock Category, uses stable whole-song fitting for Guitar/Bass before local octave adjustment, switches Ctrl/Shift octave modes when needed,",
)
text = text.replace(
    "- **Remapped** — notes moved into the selected Category's playable range",
    "- **Remapped** — played notes whose final pitch differs from the source MIDI, including a coherent whole-song shift when one is used",
)
readme.write_text(text, encoding="utf-8")
