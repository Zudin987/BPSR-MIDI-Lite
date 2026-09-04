from __future__ import annotations

import contextvars
import threading
from collections import OrderedDict, defaultdict
from dataclasses import dataclass, fields, replace
from statistics import median
from typing import Any, Iterable, Literal

import midi_engine as me
import playback_adaptive as adaptive


BandPart = Literal["keyboard", "guitar", "bass", "drums"]
BAND_ARRANGEMENT_VERSION = 2

PART_ORDER: tuple[BandPart, ...] = ("keyboard", "guitar", "bass", "drums")
DEFAULT_ACTIVE_PARTS: tuple[BandPart, ...] = PART_ORDER
PART_LABELS: dict[str, BandPart] = {
    "Piano / Keyboard": "keyboard",
    "Guitar": "guitar",
    "Bass": "bass",
    "Drums": "drums",
}
PART_LABELS_REVERSE = {value: label for label, value in PART_LABELS.items()}

DRUM_MIN_PITCH = 60  # C4
DRUM_MAX_PITCH = 83  # B5
GM_DRUM_BASE_PITCH = 35
DRUM_SLOT_COUNT = DRUM_MAX_PITCH - DRUM_MIN_PITCH + 1


def normalize_active_parts(parts: Iterable[str] | None) -> tuple[BandPart, ...]:
    if parts is None:
        return DEFAULT_ACTIVE_PARTS
    requested = {str(part) for part in parts}
    normalized = tuple(part for part in PART_ORDER if part in requested)
    if not normalized:
        raise ValueError("Band lineup must contain at least one instrument.")
    return normalized


def normalize_drum_pitch(pitch: int) -> int:
    """Map a MIDI percussion note into BPSR Drums' verified C4-B5 span.

    BPSR exposes 24 fixed drum note slots and does not need High/Low Octave.
    Notes already authored for C4-B5 stay unchanged. Standard GM percussion
    notes outside that span are wrapped across the 24 slots with GM note 35 as
    the first slot, preserving the relative drum-note ordering deterministically.
    """
    value = int(pitch)
    if DRUM_MIN_PITCH <= value <= DRUM_MAX_PITCH:
        return value
    return DRUM_MIN_PITCH + ((value - GM_DRUM_BASE_PITCH) % DRUM_SLOT_COUNT)


@dataclass(slots=True)
class BandPlanOptions(adaptive.AdaptivePlanOptions):
    band_enabled: bool = False
    band_part: BandPart = "keyboard"
    band_active_parts: tuple[BandPart, ...] = DEFAULT_ACTIVE_PARTS
    band_arrangement_version: int = BAND_ARRANGEMENT_VERSION


@dataclass(frozen=True, slots=True)
class BandSplitStats:
    original_notes: int
    keyboard_notes: int
    guitar_notes: int
    bass_notes: int
    drums_notes: int
    selected_notes: int
    selected_tracks: int
    part: BandPart
    active_parts: tuple[BandPart, ...] = DEFAULT_ACTIVE_PARTS
    drum_remapped_notes: int = 0

    @property
    def omitted_notes(self) -> int:
        return max(0, self.original_notes - self.selected_notes)


@dataclass(frozen=True, slots=True)
class BandPlanInfo:
    part: BandPart
    arrangement_version: int
    stats: BandSplitStats


@dataclass(frozen=True, slots=True)
class _BandContext:
    enabled: bool
    part: BandPart
    active_parts: tuple[BandPart, ...]


@dataclass(frozen=True, slots=True)
class _StreamStats:
    median_pitch: float
    chord_ratio: float
    program: int
    track_name: str


_previous_extract: Any = None
_previous_build_plan: Any = None
_band_context: contextvars.ContextVar[_BandContext] = contextvars.ContextVar(
    "bpsr_band_context",
    default=_BandContext(False, "keyboard", DEFAULT_ACTIVE_PARTS),
)
_band_split_context: contextvars.ContextVar[BandSplitStats | None] = contextvars.ContextVar(
    "bpsr_band_split_stats", default=None
)
_plan_info_lock = threading.RLock()
_plan_info_cache: OrderedDict[int, tuple[Any, BandPlanInfo]] = OrderedDict()
_PLAN_INFO_CACHE_LIMIT = 32


def _stream_key(meta: adaptive.SourceMeta) -> tuple[int, int, int]:
    return meta.track_index, meta.channel, meta.program


def _attack_groups(notes: list[me.SourceNote]) -> list[list[me.SourceNote]]:
    groups: list[list[me.SourceNote]] = []
    anchor: float | None = None
    for note in sorted(notes, key=lambda item: (item.start, item.serial)):
        if anchor is None or note.start - anchor > me.CHORD_ONSET_WINDOW_SECONDS:
            groups.append([])
            anchor = note.start
        groups[-1].append(note)
    return groups


def _stream_statistics(
    notes: list[me.SourceNote], metadata: dict[int, adaptive.SourceMeta]
) -> dict[tuple[int, int, int], _StreamStats]:
    by_stream: dict[tuple[int, int, int], list[me.SourceNote]] = defaultdict(list)
    meta_by_stream: dict[tuple[int, int, int], adaptive.SourceMeta] = {}
    for note in notes:
        meta = metadata.get(note.serial)
        if meta is None:
            continue
        key = _stream_key(meta)
        by_stream[key].append(note)
        meta_by_stream[key] = meta

    result: dict[tuple[int, int, int], _StreamStats] = {}
    for key, stream_notes in by_stream.items():
        groups = _attack_groups(stream_notes)
        clustered = sum(len(group) for group in groups if len(group) > 1)
        meta = meta_by_stream[key]
        result[key] = _StreamStats(
            median_pitch=float(median(note.pitch for note in stream_notes)),
            chord_ratio=clustered / max(1, len(stream_notes)),
            program=int(meta.program),
            track_name=str(meta.track_name),
        )
    return result


def _explicit_part(meta: adaptive.SourceMeta) -> BandPart | None:
    if meta.role == "drums" or meta.channel == 9:
        return "drums"
    if meta.role == "bass" or 32 <= meta.program <= 39:
        return "bass"
    if meta.role == "melody" or 80 <= meta.program <= 87:
        return "keyboard"
    if meta.role == "harmony" or 24 <= meta.program <= 31:
        return "guitar"
    return None


def _unknown_stream_part(stats: _StreamStats) -> BandPart | None:
    name = stats.track_name.casefold()
    if any(word in name for word in ("guitar", "rhythm", "chord", "accomp", "pad")):
        return "guitar"
    if any(word in name for word in ("lead", "melody", "solo", "vocal", "voice")):
        return "keyboard"
    if stats.chord_ratio >= 0.24:
        return "guitar"
    if stats.median_pitch >= 64.0:
        return "keyboard"
    if stats.median_pitch <= 52.0:
        return "guitar"
    return None


def _redirect_inactive_part(
    part: BandPart,
    active_parts: tuple[BandPart, ...],
) -> BandPart | None:
    if part in active_parts:
        return part
    if part == "drums":
        # Percussion is never converted into pitched accompaniment when no
        # drummer is present. It is intentionally omitted instead.
        return None
    preferences: dict[BandPart, tuple[BandPart, ...]] = {
        # Piano is the best fallback for the low line when Bass is absent.
        "bass": ("keyboard", "guitar"),
        # Guitar is the best melodic fallback when no Piano player is present.
        "keyboard": ("guitar", "bass"),
        # Piano is the best harmony fallback when no Guitar player is present.
        "guitar": ("keyboard", "bass"),
        "drums": (),
    }
    for candidate in preferences[part]:
        if candidate in active_parts:
            return candidate
    return None


def _adapt_split_to_active_parts(
    split: dict[BandPart, list[me.SourceNote]],
    active_parts: tuple[BandPart, ...],
) -> dict[BandPart, list[me.SourceNote]]:
    result: dict[BandPart, list[me.SourceNote]] = {part: [] for part in PART_ORDER}
    for source_part in PART_ORDER:
        target = _redirect_inactive_part(source_part, active_parts)
        if target is None:
            continue
        result[target].extend(split[source_part])
    for part in PART_ORDER:
        result[part].sort(key=lambda note: (note.start, note.serial))
    return result


def split_band_notes(
    notes: list[me.SourceNote],
    metadata: dict[int, adaptive.SourceMeta],
    active_parts: Iterable[str] | None = None,
) -> dict[BandPart, list[me.SourceNote]]:
    """Split one source MIDI deterministically into complementary active parts.

    Explicit MIDI roles/programs win first. Ambiguous streams are separated by
    register and chord texture. The full four-role split is then adapted to the
    host-selected lineup: missing melodic instruments hand their material to a
    sensible active fallback, while missing Drums simply omits percussion.
    One source note is never assigned to two players.
    """

    active = normalize_active_parts(active_parts)
    full: dict[BandPart, list[me.SourceNote]] = {part: [] for part in PART_ORDER}
    if not notes:
        return full

    stats_by_stream = _stream_statistics(notes, metadata)
    assignment: dict[int, BandPart] = {}
    unresolved_by_stream: dict[tuple[int, int, int], list[me.SourceNote]] = defaultdict(list)

    for note in sorted(notes, key=lambda item: (item.start, item.serial)):
        meta = metadata.get(note.serial)
        if meta is None:
            unresolved_by_stream[(-1, -1, -1)].append(note)
            continue
        explicit = _explicit_part(meta)
        if explicit is not None:
            assignment[note.serial] = explicit
            continue
        key = _stream_key(meta)
        inferred = _unknown_stream_part(
            stats_by_stream.get(key, _StreamStats(60.0, 0.0, -1, ""))
        )
        if inferred is not None:
            assignment[note.serial] = inferred
        else:
            unresolved_by_stream[key].append(note)

    unresolved_keys = sorted(
        unresolved_by_stream,
        key=lambda key: (
            stats_by_stream.get(key, _StreamStats(60.0, 0.0, -1, "")).median_pitch,
            key,
        ),
    )
    if len(unresolved_keys) >= 2:
        highest = unresolved_keys[-1]
        for key in unresolved_keys:
            target: BandPart = "keyboard" if key == highest else "guitar"
            for note in unresolved_by_stream[key]:
                assignment[note.serial] = target
    elif len(unresolved_keys) == 1:
        # A single ambiguous polyphonic stream is treated as a piano reduction:
        # top voice -> Piano, lower simultaneous tones -> Guitar. Monophonic
        # notes stay with Piano rather than being alternated arbitrarily.
        stream_notes = unresolved_by_stream[unresolved_keys[0]]
        for group in _attack_groups(stream_notes):
            top = max(group, key=lambda note: (note.pitch, note.velocity, -note.serial))
            for note in group:
                assignment[note.serial] = "keyboard" if note.serial == top.serial else "guitar"

    for note in notes:
        full[assignment.get(note.serial, "keyboard")].append(note)

    # Chord-only Harmony material can recover a Piano top voice, but never steal
    # a monophonic explicitly guitar-like line just to fill an empty role.
    if not full["keyboard"] and full["guitar"]:
        guitar_groups = _attack_groups(full["guitar"])
        if any(len(group) >= 2 for group in guitar_groups):
            move_to_keyboard: set[int] = set()
            for group in guitar_groups:
                if len(group) < 2:
                    continue
                top = max(group, key=lambda note: (note.pitch, note.velocity, -note.serial))
                move_to_keyboard.add(top.serial)
            full["keyboard"] = [
                note for note in full["guitar"] if note.serial in move_to_keyboard
            ]
            full["guitar"] = [
                note for note in full["guitar"] if note.serial not in move_to_keyboard
            ]

    # The reverse case occurs with one explicitly melodic polyphonic stream.
    if not full["guitar"] and full["keyboard"]:
        move_to_guitar: set[int] = set()
        for group in _attack_groups(full["keyboard"]):
            if len(group) < 2:
                continue
            top = max(group, key=lambda note: (note.pitch, note.velocity, -note.serial))
            move_to_guitar.update(note.serial for note in group if note.serial != top.serial)
        if move_to_guitar:
            full["guitar"] = [
                note for note in full["keyboard"] if note.serial in move_to_guitar
            ]
            full["keyboard"] = [
                note for note in full["keyboard"] if note.serial not in move_to_guitar
            ]

    result = _adapt_split_to_active_parts(full, active)

    # The verified BPSR Drum instrument has exactly C4-B5 and no octave modes.
    # Normalize only the Drum part, preserving authored C4-B5 notes as-is.
    result["drums"] = [
        replace(note, pitch=normalize_drum_pitch(note.pitch))
        for note in result["drums"]
    ]
    return result


def _band_extract_notes_and_pedal(path: Any, ignore_percussion: bool):
    assert _previous_extract is not None
    context = _band_context.get()
    if not context.enabled:
        return _previous_extract(path, ignore_percussion)

    # Band splitting always needs channel 10 so every client computes the same
    # four-role source analysis before adapting it to the chosen lineup.
    data = list(_previous_extract(path, False))
    notes = list(data[0])
    metadata = adaptive._metadata_context.get() or {}
    split = split_band_notes(notes, metadata, context.active_parts)
    selected = list(split[context.part])
    selected_serials = {note.serial for note in selected}

    drum_remapped = 0
    if context.part == "drums":
        original_pitch_by_serial = {note.serial: note.pitch for note in notes}
        drum_remapped = sum(
            original_pitch_by_serial.get(note.serial, note.pitch) != note.pitch
            for note in selected
        )

    if metadata:
        selected_pitch = {note.serial: note.pitch for note in selected}
        for serial in tuple(metadata):
            if serial not in selected_serials:
                metadata.pop(serial, None)
                continue
            if context.part == "drums":
                meta = metadata[serial]
                pitch = selected_pitch.get(serial, meta.pitch)
                if pitch != meta.pitch:
                    metadata[serial] = replace(meta, pitch=pitch)
        adaptive._analysis_context.set(adaptive._analyse_notes(selected, metadata))

    selected_tracks = {
        meta.track_index
        for serial, meta in metadata.items()
        if serial in selected_serials and meta.track_index >= 0
    }
    stats = BandSplitStats(
        original_notes=len(notes),
        keyboard_notes=len(split["keyboard"]),
        guitar_notes=len(split["guitar"]),
        bass_notes=len(split["bass"]),
        drums_notes=len(split["drums"]),
        selected_notes=len(selected),
        selected_tracks=len(selected_tracks),
        part=context.part,
        active_parts=context.active_parts,
        drum_remapped_notes=drum_remapped,
    )
    _band_split_context.set(stats)

    data[0] = selected
    # Intentional Band routing is not a "filtered note" loss.
    data[2] = 0
    data[3] = len(selected_tracks)
    return tuple(data)


def _coerce_band_options(options: Any | None) -> BandPlanOptions:
    if isinstance(options, BandPlanOptions):
        options.band_active_parts = normalize_active_parts(options.band_active_parts)
        return options
    values: dict[str, Any] = {}
    if options is not None:
        for field in fields(adaptive.AdaptivePlanOptions):
            if hasattr(options, field.name):
                values[field.name] = getattr(options, field.name)
        for name in ("band_enabled", "band_part", "band_active_parts", "band_arrangement_version"):
            if hasattr(options, name):
                values[name] = getattr(options, name)
    result = BandPlanOptions(**values)
    result.band_active_parts = normalize_active_parts(result.band_active_parts)
    return result


def _drum_plan_options(options: BandPlanOptions) -> BandPlanOptions:
    """Use the keyboard physical map only as a C4-B5 key transport for Drums."""
    return replace(
        options,
        instrument="keyboard",
        mode="stable",
        unlock_tier="tier2",
        mapping_method="skip",
        use_sustain_pedal=False,
        ignore_percussion=False,
        # Drums are short attacks; allow a moderately dense simultaneous hit
        # while still respecting the established physical input safety model.
        max_notes_per_chord=max(6, int(options.max_notes_per_chord)),
        adaptive_chord_limit=max(6, int(options.adaptive_chord_limit)),
    )


def _remember_plan_info(plan: Any, info: BandPlanInfo) -> None:
    with _plan_info_lock:
        key = id(plan)
        _plan_info_cache[key] = (plan, info)
        _plan_info_cache.move_to_end(key)
        while len(_plan_info_cache) > _PLAN_INFO_CACHE_LIMIT:
            _plan_info_cache.popitem(last=False)


def plan_info(plan: Any) -> BandPlanInfo | None:
    if plan is None:
        return None
    with _plan_info_lock:
        cached = _plan_info_cache.get(id(plan))
        if cached is None or cached[0] is not plan:
            return None
        return cached[1]


def band_build_plan(path: Any, options: Any | None = None):
    assert _previous_build_plan is not None
    requested = _coerce_band_options(options)
    active_parts = normalize_active_parts(requested.band_active_parts)
    if requested.band_enabled and requested.band_part not in active_parts:
        raise ValueError("Your selected Band part is disabled in the current lineup.")

    effective = (
        _drum_plan_options(requested)
        if requested.band_enabled and requested.band_part == "drums"
        else requested
    )
    context = _BandContext(bool(requested.band_enabled), requested.band_part, active_parts)
    token_context = _band_context.set(context)
    token_stats = _band_split_context.set(None)
    try:
        plan = _previous_build_plan(path, effective)
        stats = _band_split_context.get()
        if context.enabled and context.part == "drums":
            if int(getattr(plan, "page_switches", 0)) or any(
                event.kind == "page" for event in getattr(plan, "events", ())
            ):
                raise ValueError("Drums must never use BPSR page keys.")
            if int(getattr(plan, "octave_switches", 0)) or any(
                event.kind == "state" for event in getattr(plan, "events", ())
            ):
                raise ValueError("Drums C4-B5 must never use High/Low Octave.")
        if context.enabled and stats is not None:
            _remember_plan_info(
                plan,
                BandPlanInfo(
                    part=context.part,
                    arrangement_version=requested.band_arrangement_version,
                    stats=stats,
                ),
            )
        return plan
    finally:
        _band_context.reset(token_context)
        _band_split_context.reset(token_stats)


def part_from_label(label: str) -> BandPart:
    return PART_LABELS.get(label, "keyboard")


def part_label(part: BandPart) -> str:
    return PART_LABELS_REVERSE.get(part, "Piano / Keyboard")


def _active_parts_from_app(app: Any) -> tuple[BandPart, ...]:
    variables = getattr(app, "_band_lineup_vars", None)
    if not isinstance(variables, dict):
        return DEFAULT_ACTIVE_PARTS
    selected = [
        part
        for part in PART_ORDER
        if part in variables and bool(variables[part].get())
    ]
    try:
        return normalize_active_parts(selected)
    except ValueError:
        return DEFAULT_ACTIVE_PARTS


def install_band_arranger(app_module: Any) -> None:
    global _previous_extract, _previous_build_plan
    if getattr(app_module, "_band_arranger_installed", False):
        return

    _previous_extract = me._extract_notes_and_pedal
    _previous_build_plan = me.build_plan
    me._extract_notes_and_pedal = _band_extract_notes_and_pedal
    me.PlanOptions = BandPlanOptions
    me.build_plan = band_build_plan
    app_module.PlanOptions = BandPlanOptions
    app_module.build_plan = band_build_plan

    app_class = app_module.App
    original_plan_options = app_class._plan_options

    def plan_options(self: Any) -> BandPlanOptions:
        base = original_plan_options(self)
        values = {
            field.name: getattr(base, field.name)
            for field in fields(adaptive.AdaptivePlanOptions)
            if hasattr(base, field.name)
        }
        enabled_var = getattr(self, "_band_enabled_var", None)
        role_var = getattr(self, "_band_role_var", None)
        enabled = bool(enabled_var.get()) if enabled_var is not None else False
        part = part_from_label(str(role_var.get())) if role_var is not None else "keyboard"
        if enabled and part in {"keyboard", "guitar", "bass"}:
            # The Band part is authoritative. This prevents the underlying
            # single-player Instrument control from accidentally changing a
            # connected player's physical mapping.
            values["instrument"] = part
        return BandPlanOptions(
            **values,
            band_enabled=enabled,
            band_part=part,
            band_active_parts=_active_parts_from_app(self),
            band_arrangement_version=BAND_ARRANGEMENT_VERSION,
        )

    app_class._plan_options = plan_options

    # Online/Studio integrations may hold a direct build_plan reference.
    import sys

    for name in (
        "online_ui",
        "online_integration",
        "online_search_bridge",
        "studio_integration",
    ):
        module = sys.modules.get(name)
        if module is not None and hasattr(module, "build_plan"):
            module.build_plan = band_build_plan

    app_module._band_arranger_installed = True
