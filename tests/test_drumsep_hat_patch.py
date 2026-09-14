from __future__ import annotations

import pytest

np = pytest.importorskip("numpy")

from studio_band.drumsep_hat_patch import _hat_sustain_ratio


def _hat_wave(tail_level: float):
    audio = np.zeros(500, dtype="float32")
    audio[100:125] = 1.0
    audio[140:240] = tail_level
    return audio


def test_hat_decay_ratio_distinguishes_closed_and_open_envelopes() -> None:
    closed = _hat_sustain_ratio(_hat_wave(.05), 1000, .100)
    opened = _hat_sustain_ratio(_hat_wave(.45), 1000, .100)

    assert closed < .24
    assert opened >= .24
    assert opened > closed * 5
