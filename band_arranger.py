from __future__ import annotations

import contextvars
import threading
from collections import OrderedDict, defaultdict
from dataclasses import dataclass, fields
from statistics import median
from typing import Any, Literal

import midi_engine as me
import playback_adaptive as adaptive


BandPart = Literal["keyboard", "guitar", "bass", "drums"]
BAND_ARRANGEMENT_VERSION = 1

PART_LABELS: dict[str, BandPart] = {
    "Piano / Keyboard": "keyboard",
    "Guitar": "guitar",
    "Bass": "bass",
    "Drums (mapping pending)": "drums",
}
PART_LABELS_REVERSE = {value: label for label, value in PART_LABELS.items()}


@dataclass(slots=True)
class BandPlanOptions(adaptive.AdaptivePlanOptions):
    band_enabled: bool = False
    band_part: BandPart = "keyboard"
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


@dataclass(frozen=True, slots=True)
class _StreamStats:
    median_pitch: float
    chord_ratio: float
    program: int
    track_name: str


_previous_extract: Any = None
_previous_build_plan: Any = None
_band_context: contextvars.ContextVar[_BandContext] = contextvars.ContextVar(
    "bpsr_band_context", default=_BandContext(False, "keyboard")
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


def split_band_notes(
    notes: list[me.SourceNote], metadata: dict[int, adaptive.SourceMeta]
) -> dict[BandPart, list[me.SourceNote]]:
    """Split one source MIDI deterministically into complementary band parts.

    The split never changes timing and never assigns one source note to two
    players. Explicit MIDI roles/programs win first. Ambiguous streams are then
    separated by register and chord texture. A final outer-voice fallback keeps
    Piano useful on chord-only reductions and keeps Guitar useful on one-track
    chord arrangements without duplicating notes.
    """

    result: dict[BandPart, list[me.SourceNote]] = {
        "keyboard": [],
        "guitar": [],
        "bass": [],
        "drums": [],
    }
    if not notes:
        return result

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
        inferred = _unknown_stream_part(stats_by_stream.get(key, _StreamStats(60.0, 0.0, -1, "")))
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
        # top voice -> Piano, remaining chord tones -> Guitar. Monophonic notes
        # stay with Piano rather than being alternated arbitrarily.
        stream_notes = unresolved_by_stream[unresolved_keys[0]]
        for group in _attack_groups(stream_notes):
            top = max(group, key=lambda note: (note.pitch, note.velocity, -note.serial))
            for note in group:
                assignment[note.serial] = "keyboard" if note.serial == top.serial else "guitar"

    for note in notes:
        part = assignment.get(note.serial, "keyboard")
        result[part].append(note)

    # Chord-only MIDI can be explicitly tagged Harmony. Recover a top Piano
    # voice by moving (not duplicating) the highest note of polyphonic attacks.
    # Never steal a monophonic, explicitly guitar-like line merely because the
    # source contains no separate Piano track.
    if not result["keyboard"] and result["guitar"]:
        guitar_groups = _attack_groups(result["guitar"])
        if any(len(group) >= 2 for group in guitar_groups):
            move_to_keyboard: set[int] = set()
            for group in guitar_groups:
                if len(group) < 2:
                    continue
                top = max(group, key=lambda note: (note.pitch, note.velocity, -note.serial))
                move_to_keyboard.add(top.serial)
            result["keyboard"] = [
                note for note in result["guitar"] if note.serial in move_to_keyboard
            ]
            result["guitar"] = [
                note for note in result["guitar"] if note.serial not in move_to_keyboard
            ]

    # The reverse case occurs with one explicitly melodic polyphonic stream.
    # Keep its top voice on Piano and move lower simultaneous tones to Guitar.
    if not result["guitar"] and result["keyboard"]:
        move_to_guitar: set[int] = set()
        for group in _attack_groups(result["keyboard"]):
            if len(group) < 2:
                continue
            top = max(group, key=lambda note: (note.pitch, note.velocity, -note.serial))
            move_to_guitar.update(note.serial for note in group if note.serial != top.serial)
        if move_to_guitar:
            result["guitar"] = [note for note in result["keyboard"] if note.serial in move_to_guitar]
            result["keyboard"] = [note for note in result["keyboard"] if note.serial not in move_to_guitar]

    for part in result:
        result[part].sort(key=lambda note: (note.start, note.serial))
    return result


def _band_extract_notes_and_pedal(path: Any, ignore_percussion: bool):
    assert _previous_extract is not None
    context = _band_context.get()
    if not context.enabled:
        return _previous_extract(path, ignore_percussion)

    # Band splitting needs channel 10 even when the selected part is not Drums;
    # otherwise per-part counts would depend on which client generated them.
    # The selected non-drum part still contains no percussion after the split.
    data = list(_previous_extract(path, False))
    notes = list(data[0])
    metadata = adaptive._metadata_context.get() or {}
    split = split_band_notes(notes, metadata)
    selected = list(split[context.part])
    selected_serials = {note.serial for note in selected}

    if metadata:
        for serial in tuple(metadata):
            if serial not in selected_serials:
                metadata.pop(serial, None)
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
    )
    _band_split_context.set(stats)

    data[0] = selected
    # Keep intentional band routing separate from physical filtering metrics.
    data[2] = 0
    data[3] = len(selected_tracks)
    return tuple(data)


def _coerce_band_options(options: Any | None) -> BandPlanOptions:
    if isinstance(options, BandPlanOptions):
        return options
    values: dict[str, Any] = {}
    if options is not None:
        for field in fields(adaptive.AdaptivePlanOptions):
            if hasattr(options, field.name):
                values[field.name] = getattr(options, field.name)
    return BandPlanOptions(**values)


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
    context = _BandContext(bool(requested.band_enabled), requested.band_part)
    token_context = _band_context.set(context)
    token_stats = _band_split_context.set(None)
    try:
        plan = _previous_build_plan(path, requested)
        stats = _band_split_context.get()
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
        return BandPlanOptions(
            **values,
            band_enabled=enabled,
            band_part=part,
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
