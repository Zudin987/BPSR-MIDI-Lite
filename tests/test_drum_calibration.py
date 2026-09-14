import json

import band_audit_hardening as hardening
import studio_band.arrange as drum_arrange
import studio_band.pipeline as drum_pipeline
from band_audit_hardening import CALIBRATED_DRUM_PITCHES, calibrated_drum_pitch
from studio_band.arrange import load_drum_profile


def test_video_calibrated_profile_targets_only_audible_bpsr_pads():
    profile = load_drum_profile()
    audible = set(CALIBRATED_DRUM_PITCHES)

    assert profile["calibrated"] is True
    assert set(profile["usable_pitches"]) == audible
    assert set(profile["silent_pitches"]) == set(range(60, 84)) - audible
    assert set(profile["mapping"].values()) <= audible
    assert profile["mapping"] == {
        "KICK": 65,
        "SNARE": 72,
        "CLOSED_HAT": 62,
        "OPEN_HAT": 79,
        "CRASH": 81,
        "RIDE": 77,
        "TOM": 74,
        "PERCUSSION": 76,
    }


def test_band_drum_transport_never_targets_a_silent_key():
    audible = set(CALIBRATED_DRUM_PITCHES)
    assert all(calibrated_drum_pitch(pitch) in audible for pitch in range(128))

    assert calibrated_drum_pitch(35) == 65  # acoustic bass drum -> kick
    assert calibrated_drum_pitch(38) == 72  # acoustic snare -> snare
    assert calibrated_drum_pitch(42) == 62  # closed hat
    assert calibrated_drum_pitch(46) == 79  # open hat
    assert calibrated_drum_pitch(49) == 81  # crash
    assert calibrated_drum_pitch(51) == 77  # ride
    assert calibrated_drum_pitch(41) == 69  # low tom
    assert calibrated_drum_pitch(48) == 76  # high tom


def _legacy_provisional_profile() -> dict:
    profile = dict(drum_arrange.load_drum_profile())
    profile["version"] = "bpsr-drums-provisional-1"
    profile["calibrated"] = False
    profile["mapping"] = {
        "KICK": 61,
        "SNARE": 63,
        "CLOSED_HAT": 67,
        "OPEN_HAT": 71,
        "CRASH": 74,
        "RIDE": 76,
        "TOM": 70,
        "PERCUSSION": 64,
    }
    return profile


def test_stale_provisional_user_profile_uses_calibrated_bundled_map(tmp_path):
    target = tmp_path / "bpsr_drums.json"
    target.write_text(json.dumps(_legacy_provisional_profile()), encoding="utf-8")

    hardening._patch_studio_drum_profile()
    profile = drum_arrange.load_drum_profile(target)
    pipeline_profile = drum_pipeline.load_drum_profile(target)

    assert profile["version"] == "bpsr-drums-calibrated-2"
    assert profile["calibrated"] is True
    assert profile["mapping"]["KICK"] == 65
    assert profile["mapping"]["SNARE"] == 72
    assert profile["mapping"]["CLOSED_HAT"] == 62
    assert pipeline_profile["mapping"] == profile["mapping"]


def test_custom_user_drum_profile_is_not_overwritten(tmp_path):
    target = tmp_path / "bpsr_drums.json"
    custom = _legacy_provisional_profile()
    custom["mapping"] = dict(custom["mapping"])
    custom["mapping"]["KICK"] = 65
    target.write_text(json.dumps(custom), encoding="utf-8")

    hardening._patch_studio_drum_profile()
    profile = drum_arrange.load_drum_profile(target)

    assert profile["calibrated"] is False
    assert profile["version"] == "bpsr-drums-provisional-1"
    assert profile["mapping"]["KICK"] == 65
    assert profile["mapping"]["SNARE"] == 63
