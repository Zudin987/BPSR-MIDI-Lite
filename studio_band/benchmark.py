"""Small mir_eval transcription benchmark used by the opt-in real-audio gate."""
from __future__ import annotations

from collections import defaultdict


def _value(event, name):
    return event[name] if isinstance(event, dict) else getattr(event, name)


def transcription_benchmark(reference, estimated) -> dict:
    """Return source-level and macro note precision/recall/F1/overlap."""
    import mir_eval
    import numpy as np
    from mir_eval.transcription import precision_recall_f1_overlap

    grouped_reference = defaultdict(list)
    grouped_estimated = defaultdict(list)
    for collection, grouped in ((reference, grouped_reference), (estimated, grouped_estimated)):
        for event in collection:
            pitch = _value(event, "pitch")
            source = _value(event, "source")
            if pitch is not None and source != "drums":
                grouped[source].append(event)
    results = {}
    for source in sorted(grouped_reference):
        truth = grouped_reference[source]
        guesses = grouped_estimated.get(source, [])
        if not truth:
            continue
        if not guesses:
            values = (0.0, 0.0, 0.0, 0.0)
        else:
            reference_intervals = np.asarray(
                [[_value(event, "start"), _value(event, "end")] for event in truth], dtype=float,
            )
            estimated_intervals = np.asarray(
                [[_value(event, "start"), _value(event, "end")] for event in guesses], dtype=float,
            )
            reference_pitches = np.asarray(
                [440 * 2 ** ((_value(event, "pitch")-69) / 12) for event in truth], dtype=float,
            )
            estimated_pitches = np.asarray(
                [440 * 2 ** ((_value(event, "pitch")-69) / 12) for event in guesses], dtype=float,
            )
            values = precision_recall_f1_overlap(
                reference_intervals, reference_pitches, estimated_intervals, estimated_pitches,
            )
        results[source] = {
            "precision": float(values[0]), "recall": float(values[1]),
            "f1": float(values[2]), "overlap": float(values[3]),
            "reference_notes": len(truth), "estimated_notes": len(guesses),
        }
    macro = {
        metric: (sum(values[metric] for values in results.values()) / len(results) if results else 0.0)
        for metric in ("precision", "recall", "f1", "overlap")
    }
    return {"mir_eval_version": mir_eval.__version__, "sources": results, "macro": macro}
