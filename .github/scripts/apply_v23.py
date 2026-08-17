from __future__ import annotations

from pathlib import Path
import re


def must_replace(text: str, old: str, new: str, label: str, count: int = 1) -> str:
    found = text.count(old)
    if found < count:
        raise SystemExit(f"missing patch target {label}: found {found}")
    return text.replace(old, new, count)


# Engine: Piano Category 4 is progression metadata only for this app. Playback
# stays within the C2-B6 middle-page Ctrl/Default/Shift envelope.
p = Path("midi_engine.py")
s = p.read_text(encoding="utf-8")
s = must_replace(
    s,
    'instrument="keyboard", code="tier4", label="Experimental full range — A0–C8",',
    'instrument="keyboard", code="tier4", label="Category 4 safe playback — C2–B6",',
    "keyboard tier4 label",
)
s = must_replace(
    s,
    "            low=21, high=108,\n"
    "            full_states=_full_chromatic_states(),\n"
    "            stable_states=(KeyboardState(1, 0), KeyboardState(1, -1), KeyboardState(1, 1)),",
    "            low=36, high=95,\n"
    "            # Category 4 unlocks outer piano notes in-game, but playback stays\n"
    "            # on the middle page so this selectable profile never uses < / >.\n"
    "            full_states=(KeyboardState(1, -1), KeyboardState(1, 0), KeyboardState(1, 1)),\n"
    "            stable_states=(KeyboardState(1, -1), KeyboardState(1, 0), KeyboardState(1, 1)),",
    "keyboard tier4 range",
)
p.write_text(s, encoding="utf-8")


# Controller compatibility shell. modern_ui.py exposes only the simplified
# category/raw UI, but keeping legacy variables avoids config/CLI breakage.
p = Path("app.py")
s = p.read_text(encoding="utf-8")
s = s.replace('APP_VERSION = "1.1.1"', 'APP_VERSION = "2.3.0"')
s = must_replace(
    s,
    '        "Tier 1 — C3–B4": "tier1",\n'
    '        "Tier 2 — C3–B6": "tier2",\n'
    '        "Tier 3 — C2–B6 (no < / >)": "tier3",\n'
    '        "Experimental full range — A0–C8": "tier4",',
    '        "Category 1 safe — C3–B4": "tier1",\n'
    '        "Category 2 safe — C3–B6": "tier2",\n'
    '        "Category 3 safe — C2–B6": "tier3",\n'
    '        "Category 4 safe — C2–B6": "tier4",',
    "keyboard unlock labels",
)
s = must_replace(
    s,
    '        "Tier 1 — C3–B4": "tier1",\n'
    '        "Tier 2 — E2–B4": "tier2",\n'
    '        "Tier 3 — E2–D6 (no < / >)": "tier3",\n'
    '        "Experimental full range — A0–C8": "tier4",',
    '        "Category 1 safe — C3–B4": "tier1",\n'
    '        "Category 2 safe — E2–B4": "tier2",\n'
    '        "Category 3 safe — E2–D6": "tier3",',
    "guitar unlock labels",
)
s = must_replace(
    s,
    '        "Tier 1 — E1–B2": "tier1",\n        "Tier 2 — E1–B3": "tier2",',
    '        "Category 1 safe — E1–B2": "tier1",\n        "Category 2 safe — E1–B3": "tier2",',
    "bass unlock labels",
)
s = s.replace(
    '"keyboard": {\n        "mode": "stable", "unlock_tier": "tier3", "mapping": "octave",\n'
    '        "chord_limit": 0, "speed": 100',
    '"keyboard": {\n        "mode": "stable", "unlock_tier": "tier4", "mapping": "octave",\n'
    '        "chord_limit": 0, "speed": 100',
    1,
)
s = s.replace('self._active_profile_code = "tier3"', 'self._active_profile_code = "tier4"', 1)
s = s.replace(
    '"keyboard": "tier3", "guitar": "tier3", "bass": "tier2"',
    '"keyboard": "tier4", "guitar": "tier3", "bass": "tier2"',
    1,
)
s = s.replace('profile_label_for("keyboard", "tier3")', 'profile_label_for("keyboard", "tier4")', 1)
s = s.replace(
    'self.unlock_var = tk.StringVar(value="Tier 3 — C2–B6 (no < / >)")',
    'self.unlock_var = tk.StringVar(value="Category 4 safe — C2–B6")',
    1,
)
s = s.replace('self.minimize_var = tk.BooleanVar(value=True)', 'self.minimize_var = tk.BooleanVar(value=False)', 1)
s = s.replace('        self.minimize_var.trace_add("write", lambda *_args: self._save_config_if_ready())\n', '')
s = must_replace(
    s,
    '    def _unlock_code(self) -> str:\n'
    '        default = "tier2" if self._instrument_code() == "bass" else "tier3"\n'
    '        return self._unlock_labels().get(self.unlock_var.get(), default)',
    '    def _unlock_code(self) -> str:\n'
    '        instrument = self._instrument_code()\n'
    '        default = "tier2" if instrument == "bass" else ("tier4" if instrument == "keyboard" else "tier3")\n'
    '        return self._unlock_labels().get(self.unlock_var.get(), default)',
    "unlock fallback",
)
# No visible chord widget remains in the modern UI.
s = s.replace('        self.chord_combo.configure(values=list(self._chord_labels()))\n', '')
s = s.replace('self.speed_var.set(int(settings.get("speed", 85)))', 'self.speed_var.set(int(settings.get("speed", 100)))')
s = s.replace('self.length_var.set(int(settings.get("length", 150)))', 'self.length_var.set(int(settings.get("length", 100)))')
s = s.replace('self.minimum_note_var.set(int(settings.get("minimum_note", 120)))', 'self.minimum_note_var.set(int(settings.get("minimum_note", 70)))')
# Old versions treated tier4 as custom page mode. It is now a real category.
s = re.sub(
    r'\n\s*if old_profile == "tier4":\n\s*old_profile = "custom"\n'
    r'\s*self\._custom_settings_by_instrument\["keyboard"\]\.update\(\n'
    r'\s*\{"mode": "full", "unlock_tier": "tier4"\}\n\s*\)\n',
    '\n',
    s,
    count=1,
)
s = s.replace('        self.minimize_var.set(bool(data.get("minimize", True)))', '        self.minimize_var.set(False)')
s = s.replace('            "minimize": self.minimize_var.get(),\n', '')
# Remove every automatic minimize path (input test + normal Play).
s = s.replace('        if self.minimize_var.get():\n            self.after(250, self.iconify)\n', '')
reset_pattern = re.compile(
    r'    def _reset_defaults\(self\) -> None:\n.*?\n    def _on_close\(self\) -> None:',
    re.S,
)
reset_replacement = '''    def _reset_defaults(self) -> None:
        instrument = self._instrument_code()
        default_code = default_profile_code(instrument)  # type: ignore[arg-type]
        self.profile_var.set(profile_label_for(instrument, default_code))  # type: ignore[arg-type]
        self._profile_changed()
        self.speed_var.set(100)
        self.start_delay_var.set(3.0)
        self.minimize_var.set(False)
        self.input_backend_var.set(INPUT_BACKEND_LABELS_REVERSE["scan"])
        self._save_config()

    def _on_close(self) -> None:'''
s, changed = reset_pattern.subn(reset_replacement, s, count=1)
if changed != 1:
    raise SystemExit("reset defaults patch failed")
s = s.replace('parser.add_argument("--speed", type=int, default=85)', 'parser.add_argument("--speed", type=int, default=100)')
s = s.replace('parser.add_argument("--length", type=int, default=150)', 'parser.add_argument("--length", type=int, default=100)')
s = s.replace(
    'default="tier3",\n        help="tier1=C3-B4, tier2=C3-B6, tier3=C2-B6, tier4=Custom full A0-C8",',
    'default="tier4",\n        help="Keyboard tier3/tier4 use safe C2-B6 no-page playback",',
)
p.write_text(s, encoding="utf-8")


p = Path("modern_launcher.py")
p.write_text(p.read_text(encoding="utf-8").replace('app.APP_VERSION = "2.2.0"', 'app.APP_VERSION = "2.3.0"'), encoding="utf-8")
p = Path("version_info.txt")
s = p.read_text(encoding="utf-8").replace('(2, 2, 0, 0)', '(2, 3, 0, 0)').replace("u'2.2.0'", "u'2.3.0'")
p.write_text(s, encoding="utf-8")


Path("tests/test_profiles.py").write_text(
    '''from profiles import FIXED_PROFILES, allowed_modes_for_unlock, default_profile_code, get_fixed_profile, profile_labels_for


def test_categories_and_raw_mode_are_the_only_user_profiles() -> None:
    assert set(FIXED_PROFILES["keyboard"]) == {"tier1", "tier2", "tier3", "tier4", "raw"}
    assert set(FIXED_PROFILES["guitar"]) == {"tier1", "tier2", "tier3", "raw"}
    assert set(FIXED_PROFILES["bass"]) == {"tier1", "tier2", "raw"}
    for instrument in ("keyboard", "guitar", "bass"):
        values = set(profile_labels_for(instrument).values())
        assert "raw" in values
        assert "custom" not in values


def test_category_labels_follow_game_progression() -> None:
    assert get_fixed_profile("keyboard", "tier4").label.startswith("Category 4")
    assert get_fixed_profile("guitar", "tier3").label.startswith("Category 3")
    assert get_fixed_profile("bass", "tier2").label.startswith("Category 2")


def test_raw_is_no_remap_no_chord_limit() -> None:
    for instrument in ("keyboard", "guitar", "bass"):
        raw = get_fixed_profile(instrument, "raw")
        assert raw.mode == "stable"
        assert raw.mapping == "skip"
        assert raw.chord_limit == 0


def test_no_selectable_profile_exposes_page_mode() -> None:
    for profiles in FIXED_PROFILES.values():
        for profile in profiles.values():
            assert profile.mode == "stable"
    for instrument in ("keyboard", "guitar", "bass"):
        for tier in ("tier1", "tier2", "tier3", "tier4"):
            assert allowed_modes_for_unlock(instrument, tier) == ("stable",)


def test_defaults_are_highest_normal_categories() -> None:
    assert default_profile_code("keyboard") == "tier4"
    assert default_profile_code("guitar") == "tier3"
    assert default_profile_code("bass") == "tier2"


def test_bass_normal_profiles_remain_monophonic_but_raw_does_not() -> None:
    assert get_fixed_profile("bass", "tier1").chord_limit == 1
    assert get_fixed_profile("bass", "tier2").chord_limit == 1
    assert get_fixed_profile("bass", "raw").chord_limit == 0


def test_all_profiles_keep_v21_articulation_defaults() -> None:
    for profiles in FIXED_PROFILES.values():
        for profile in profiles.values():
            assert profile.speed == 100
            assert profile.note_length == 100
            assert profile.minimum_note == 70
''',
    encoding="utf-8",
)


p = Path("tests/test_engine.py")
s = p.read_text(encoding="utf-8")
tier4_pattern = re.compile(
    r'def test_unlock_tier4_can_preserve_c8_with_right_page\(tmp_path: Path\) -> None:\n.*?(?=\ndef test_stable_mode_uses_safe_subset_of_large_unlock_tier)',
    re.S,
)
tier4_replacement = '''def test_unlock_tier4_stays_c2_b6_and_never_uses_page_keys(tmp_path: Path) -> None:
    midi_path = tmp_path / "tier4.mid"
    make_test_midi(midi_path, [21, 36, 60, 95, 108], gap_ticks=480, duration_ticks=120)
    plan = build_plan(
        midi_path,
        PlanOptions(
            mode="full",
            unlock_tier="tier4",
            speed_percent=100,
            note_length_percent=100,
        ),
    )
    assert plan.effective_min_pitch == 36
    assert plan.effective_max_pitch == 95
    assert 36 <= plan.planned_min_pitch <= plan.planned_max_pitch <= 95
    assert plan.page_switches == 0
    assert all(event.kind != "page" for event in plan.events)

'''
s, changed = tier4_pattern.subn(tier4_replacement, s, count=1)
if changed != 1:
    raise SystemExit("tier4 test patch failed")
s = s.replace(
    '    assert plan.configured_min_pitch == 21\n    assert plan.configured_max_pitch == 108\n',
    '    assert plan.configured_min_pitch == 36\n    assert plan.configured_max_pitch == 95\n',
    1,
)
s += '''


def test_raw_keyboard_skips_out_of_range_without_remapping(tmp_path: Path) -> None:
    from profiles import get_fixed_profile

    midi_path = tmp_path / "raw_keyboard.mid"
    make_test_midi(midi_path, [21, 36, 60, 95, 108], gap_ticks=480, duration_ticks=120)
    profile = get_fixed_profile("keyboard", "raw")
    plan = build_plan(
        midi_path,
        PlanOptions(
            instrument="keyboard",
            mode=profile.mode,
            unlock_tier=profile.unlock_tier,
            mapping_method=profile.mapping,
            max_notes_per_chord=profile.chord_limit,
            speed_percent=100,
            note_length_percent=100,
        ),
    )
    assert plan.folded_notes == 0
    assert plan.skipped_notes == 2
    assert (plan.planned_min_pitch, plan.planned_max_pitch) == (36, 95)
    assert plan.page_switches == 0


def test_every_selectable_profile_is_page_free(tmp_path: Path) -> None:
    from profiles import FIXED_PROFILES

    midi_path = tmp_path / "all_profiles.mid"
    make_test_midi(midi_path, [21, 28, 36, 48, 60, 71, 83, 95, 108], gap_ticks=480)
    for instrument, profiles in FIXED_PROFILES.items():
        for profile in profiles.values():
            plan = build_plan(
                midi_path,
                PlanOptions(
                    instrument=instrument,
                    mode=profile.mode,
                    unlock_tier=profile.unlock_tier,
                    mapping_method=profile.mapping,
                    max_notes_per_chord=profile.chord_limit,
                    speed_percent=100,
                ),
            )
            assert plan.page_switches == 0, (instrument, profile.code)
            assert all(event.kind != "page" for event in plan.events), (instrument, profile.code)
'''
p.write_text(s, encoding="utf-8")


p = Path("CHANGELOG.md")
s = p.read_text(encoding="utf-8")
entry = '''## v2.3.0

- Replaced Advanced setup with explicit BPSR Category choices plus **Raw MIDI — no remap**.
- Piano Category 4 still plays only inside **C2–B6**, so selectable profiles never require `<` / `>`.
- Guitar is capped to **E2–D6** and Bass to **E1–B3** for safe no-page playback.
- Raw MIDI preserves pitches and full chords; physically unavailable pitches are skipped instead of remapped.
- Removed playback-style, mapping, chord, page-delay, note-length, sustain, and percussion controls from the UI; safe defaults are automatic.
- Removed Minimize-after-Play and automatic minimizing. The app stays open while the user returns to BPSR.
- Song speed remains the normal user-facing musical control.
- Play is blocked if a selectable profile ever unexpectedly generates a page-key event.

'''
s = s.replace('# Changelog\n\n', '# Changelog\n\n' + entry, 1)
p.write_text(s, encoding="utf-8")


Path("README.md").write_text(
    '''# 🎹 BPSR MIDI Lite

A small Windows MIDI-to-keyboard player for Blue Protocol: Star Resonance Keyboard, Electric Guitar, and Electric Bass.

## Normal use

1. Choose the instrument.
2. Choose the BPSR **Category** you have unlocked.
3. Add/select a MIDI.
4. Leave **Song speed** at 100% for original tempo, or adjust it.
5. Press **Play in BPSR** and return to the game during the countdown. The app stays open.

F10 always stops playback and releases held keys.

## Safe category ranges

### Piano / Keyboard
- Category 1: starts C3–B4.
- Category 2: unlocks C5–B6; cumulative safe playback C3–B6.
- Category 3: unlocks A0–B2; the app uses C2–B6.
- Category 4: unlocks C7–C8; the app still uses C2–B6.

The C2–B6 cap is intentional so Piano only needs Default/Low/High octave on the middle page and never `<` or `>`.

### Electric Guitar
- Category 1: C3–B4.
- Category 2: unlocks E2–B2; cumulative safe playback E2–B4.
- Category 3: unlocks C5–D6; complete safe playback E2–D6.

### Electric Bass
- Category 1: E1–B2.
- Category 2: complete safe playback E1–B3 using Default/High Octave. Bass has no Low Octave mode.

## Raw MIDI — no remap

Raw MIDI is the last choice for every instrument. It does not transpose or octave-fold pitches and does not simplify large chords. If a pitch is outside the physical safe range, it is skipped because there is no playable no-page key for it. Raw mode still keeps the BPSR-safe short-note/retrigger timing and ignores the drum channel for pitched instruments.

## Octave toggles

Ctrl/Shift are treated as toggles. Pressing the active octave again returns to Default. High and Low can switch directly to each other without a forced Default step.

## More settings

More settings contains only countdown, song-folder/reset helpers, and Troubleshooting/input tools. There is no Advanced fitting panel and no Minimize-after-Play option.

## License

GNU AGPL-3.0. Created by MrEz.
''',
    encoding="utf-8",
)


Path("END_USER_GUIDE.md").write_text(
    '''# BPSR MIDI Lite — Beginner Guide

Choose Instrument → Category → Song → Song speed → Play.

Normal Categories automatically fit out-of-range notes into the safe range. Lower Categories need more remapping because fewer notes are unlocked.

**Keyboard:** Category 1, 2, 3, 4, Raw MIDI. Normal playback never leaves C2–B6.

**Guitar:** Category 1, 2, 3, Raw MIDI. Maximum safe range E2–D6.

**Bass:** Category 1, 2, Raw MIDI. Maximum safe range E1–B3; Bass has no Low Octave.

Raw MIDI does not remap pitches or simplify chords. Physically unavailable notes are skipped and reported by Song check.

The app starts from Default octave, uses Ctrl/Shift when needed, can switch High↔Low directly, and resets to Default after playback. It never needs `<` or `>` for selectable profiles.

The app stays open during playback. More settings contains countdown and troubleshooting only. F10 always stops and releases keys.
''',
    encoding="utf-8",
)
