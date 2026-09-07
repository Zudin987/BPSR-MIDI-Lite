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
