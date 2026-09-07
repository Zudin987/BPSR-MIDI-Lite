"""Install the Studio-only BPSR audibility arranger layer."""
from __future__ import annotations

import sys
from collections import defaultdict
from typing import Any

from .fusion import reject
from .gameplay_clarity import clarify_part

_INSTALLED = False


def _collapse_other_duplicates(master: Any, result: dict) -> int:
    """Give ambiguous `other` material one audible Band owner by default."""
    other_ids = {
        event.event_id for event in master.events
        if event.source == "other" and event.event_id
    }
    if not other_ids:
        return 0

    occurrences: dict[str, list[tuple[str, Any]]] = defaultdict(list)
    for part in ("piano", "guitar", "bass"):
        for event in result.get("parts", {}).get(part, []):
            if event.event_id in other_ids:
                occurrences[event.event_id].append((part, event))

    collapsed = 0
    for event_id, copies in occurrences.items():
        targets = {part for part, _ in copies}
        if len(targets) <= 1:
            continue
        reference = max((event for _, event in copies), key=lambda event: event.confidence)
        if "bass" in targets and reference.pitch is not None and reference.pitch <= 50:
            owner = "bass"
        elif "guitar" in targets and reference.role in {"HARMONY", "RHYTHM", "DECORATION"}:
            owner = "guitar"
        elif "piano" in targets:
            owner = "piano"
        else:
            owner = sorted(targets)[0]

        for part, event in copies:
            if part == owner:
                continue
            result["parts"][part] = [
                current for current in result["parts"][part]
                if current.event_id != event_id
            ]
            result.setdefault("removed", []).append({
                **reject(event, "ingame_duplicate_accompaniment_owner"),
                "part": part,
            })
            summary = result.get("summary", {}).get(part)
            if isinstance(summary, dict):
                summary["notes"] = len(result["parts"][part])
                summary["simplified"] = int(summary.get("simplified", 0)) + 1
            collapsed += 1
    return collapsed


def _clarify_arrangement(master: Any, result: dict, settings: Any) -> dict:
    collapsed = _collapse_other_duplicates(master, result)
    removed_total = 0
    shortened_total = 0
    for part in ("piano", "guitar"):
        current = list(result.get("parts", {}).get(part, []))
        clarified, removed, metrics = clarify_part(
            current,
            part,
            int(settings.polyphony[part]),
        )
        result["parts"][part] = clarified
        for record in removed:
            result.setdefault("removed", []).append({**record, "part": part})
        summary = result.get("summary", {}).get(part)
        if isinstance(summary, dict):
            summary["notes"] = len(clarified)
            summary["simplified"] = int(summary.get("simplified", 0)) + len(removed)
            summary.update(metrics)
        removed_total += int(metrics.get("ingame_clarity_removed", 0))
        shortened_total += int(metrics.get("ingame_tails_shortened", 0))

    result["arranger_version"] = "band4-audio2-ingame-clarity"
    result["ingame_clarity"] = {
        "shared_accompaniment_copies_removed": collapsed,
        "dense_accompaniment_notes_removed": removed_total,
        "accompaniment_tails_shortened": shortened_total,
        "policy": "protect melody/riffs; do not rely on MIDI velocity for BPSR mix balance",
    }
    return result


def apply_gameplay_clarity() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    from . import arrange as arrange_module

    original = arrange_module.arrange
    if getattr(original, "_bpsr_ingame_clarity", False):
        _INSTALLED = True
        return

    def arranged(master, settings, drum_profile):
        result = original(master, settings, drum_profile)
        return _clarify_arrangement(master, result, settings)

    arranged._bpsr_ingame_clarity = True
    arranged._bpsr_original_arrange = original
    arrange_module.arrange = arranged

    # Some modules import `arrange` by value. Patch already-loaded references;
    # modules imported later will naturally receive arrange_module.arrange.
    for name in ("studio_band.pipeline", "studio_band.export"):
        module = sys.modules.get(name)
        if module is not None and hasattr(module, "arrange"):
            module.arrange = arranged
    _INSTALLED = True
