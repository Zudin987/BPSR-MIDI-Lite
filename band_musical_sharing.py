from __future__ import annotations

from typing import Any

import band_arranger
import playback_adaptive as adaptive


# Arrangement v3 changes the musical contract: clearly-authored source roles stay
# exclusive, while genuinely ambiguous accompaniment may intentionally be shared
# by Piano and Guitar instead of being arbitrarily alternated between them.
BAND_SHARED_ARRANGEMENT_VERSION = 3

_DRUM_NAME_WORDS = (
    "drum",
    "drums",
    "drumkit",
    "drum kit",
    "percussion",
    "perc.",
    "perc ",
    "kick",
    "snare",
    "hi-hat",
    "hihat",
    "hi hat",
    "cymbal",
    "tom tom",
    "toms",
)
_GUITAR_NAME_WORDS = (
    "guitar",
    "acoustic guitar",
    "electric guitar",
)
_KEYBOARD_ONLY_NAME_WORDS = (
    "melody",
    "lead",
    "solo",
    "vocal",
    "voice",
    "soprano",
    "theme",
)
_BASS_NAME_WORDS = (
    "bass",
    "contrabass",
    "bassline",
    "low end",
)

_original_split: Any = None
_original_role_from_source: Any = None


def _name_has(name: str, words: tuple[str, ...]) -> bool:
    folded = str(name).casefold()
    return any(word in folded for word in words)


def enhanced_role_from_source(track_name: str, channel: int, program: int) -> adaptive.Role:
    """Recognize authored percussion even when a MIDI exporter did not use channel 10."""
    if int(channel) == 9 or _name_has(track_name, _DRUM_NAME_WORDS):
        return "drums"
    assert _original_role_from_source is not None
    return _original_role_from_source(track_name, channel, program)


def _shareable_keyboard_guitar(meta: adaptive.SourceMeta | None) -> bool:
    """Return True only when a source note has no strong single-instrument ownership."""
    if meta is None:
        return True

    if meta.channel == 9 or meta.role == "drums" or _name_has(meta.track_name, _DRUM_NAME_WORDS):
        return False
    if meta.role == "bass" or 32 <= int(meta.program) <= 39 or _name_has(meta.track_name, _BASS_NAME_WORDS):
        return False
    if meta.role == "melody" or 80 <= int(meta.program) <= 87 or _name_has(meta.track_name, _KEYBOARD_ONLY_NAME_WORDS):
        return False
    if 24 <= int(meta.program) <= 31 or _name_has(meta.track_name, _GUITAR_NAME_WORDS):
        return False

    # Generic Piano/Strings/Pad/Harmony/Chord/Accompaniment and unlabelled
    # material can reasonably reinforce both chordal instruments. Physical
    # range/chord-pressure logic still simplifies each player's local plan.
    return meta.role in {"harmony", "unknown"}


def split_band_notes_shared(
    notes: list[Any],
    metadata: dict[int, adaptive.SourceMeta],
    active_parts: Any = None,
):
    """Build the normal deterministic split, then share compatible Piano/Guitar notes."""
    assert _original_split is not None
    result = _original_split(notes, metadata, active_parts)
    active = band_arranger.normalize_active_parts(active_parts)

    if "keyboard" not in active or "guitar" not in active:
        return result

    keyboard_serials = {note.serial for note in result["keyboard"]}
    guitar_serials = {note.serial for note in result["guitar"]}
    by_serial = {note.serial: note for note in notes}

    shared_serials: set[int] = set()
    for serial in keyboard_serials | guitar_serials:
        if _shareable_keyboard_guitar(metadata.get(serial)):
            shared_serials.add(serial)

    if not shared_serials:
        return result

    for serial in sorted(shared_serials):
        note = by_serial.get(serial)
        if note is None:
            continue
        if serial not in keyboard_serials:
            result["keyboard"].append(note)
            keyboard_serials.add(serial)
        if serial not in guitar_serials:
            result["guitar"].append(note)
            guitar_serials.add(serial)

    result["keyboard"].sort(key=lambda note: (note.start, note.serial))
    result["guitar"].sort(key=lambda note: (note.start, note.serial))
    return result


def install_shared_band_arrangement(app_module: Any) -> None:
    global _original_split, _original_role_from_source
    if getattr(app_module, "_shared_band_arrangement_installed", False):
        return
    if not getattr(app_module, "_band_arranger_installed", False):
        raise RuntimeError("Band arranger must be installed before shared Band arrangement.")

    _original_split = band_arranger.split_band_notes
    _original_role_from_source = adaptive._role_from_source

    adaptive._role_from_source = enhanced_role_from_source
    band_arranger.split_band_notes = split_band_notes_shared
    band_arranger.BAND_ARRANGEMENT_VERSION = BAND_SHARED_ARRANGEMENT_VERSION

    app_module._shared_band_arrangement_installed = True
