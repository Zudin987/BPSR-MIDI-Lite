from __future__ import annotations

import json
from pathlib import Path

import playback_adaptive as adaptive
import playback_calibration_provenance as provenance


def _saved_profile() -> adaptive.CalibrationProfile:
    return adaptive.CalibrationProfile(
        instrument="keyboard",
        minimum_clean_hold_ms=155,
        hard_floor_ms=72,
        retrigger_gap_ms=41,
        chord_stagger_ms=6,
        modifier_settle_ms=96,
        max_polyphony=2,
        calibrated=True,
        updated_at=123.0,
    )


def test_effective_profile_uses_only_verified_timing_fields() -> None:
    profile = provenance._effective_profile(
        "keyboard",
        _saved_profile(),
        {
            "hold": True,
            "repeat": False,
            "chord": False,
            "modifier": True,
        },
    )
    defaults = adaptive._default_calibration("keyboard")
    assert profile.minimum_clean_hold_ms == 155
    assert profile.hard_floor_ms == 72
    assert profile.retrigger_gap_ms == defaults.retrigger_gap_ms
    assert profile.chord_stagger_ms == defaults.chord_stagger_ms
    assert profile.modifier_settle_ms == 96
    assert profile.max_polyphony == defaults.max_polyphony


def test_legacy_v33_provenance_is_entirely_untrusted(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "provenance.json"
    path.write_text(
        json.dumps(
            {
                "keyboard": {
                    "hold": True,
                    "repeat": True,
                    "chord": True,
                    "modifier": True,
                    "polyphony": True,
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(provenance, "provenance_path", lambda: path)

    flags = provenance.load_measurement_flags("keyboard")
    assert flags == {
        "hold": False,
        "repeat": False,
        "chord": False,
        "modifier": False,
    }
    assert "polyphony" not in provenance.MEASUREMENT_FIELDS
    assert provenance.measurement_state_label("keyboard") == "safe defaults active"


def test_schema_v2_provenance_flags_are_trusted(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "provenance.json"
    path.write_text(
        json.dumps(
            {
                "_schema_version": provenance.PROVENANCE_SCHEMA_VERSION,
                "keyboard": {
                    "hold": True,
                    "repeat": True,
                    "chord": True,
                    "modifier": True,
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(provenance, "provenance_path", lambda: path)
    assert all(provenance.load_measurement_flags("keyboard").values())
    assert provenance.measurement_state_label("keyboard") == "timing fully verified"


def test_first_new_measurement_migrates_and_invalidates_other_legacy_flags(
    tmp_path: Path,
    monkeypatch,
) -> None:
    path = tmp_path / "provenance.json"
    path.write_text(
        json.dumps(
            {
                "keyboard": {"hold": True, "repeat": True},
                "guitar": {"chord": True, "modifier": True},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(provenance, "provenance_path", lambda: path)

    provenance.set_measurement("keyboard", "hold", True)
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["_schema_version"] == provenance.PROVENANCE_SCHEMA_VERSION
    assert payload["keyboard"] == {
        "hold": True,
        "repeat": False,
        "chord": False,
        "modifier": False,
    }
    assert payload["guitar"] == {
        "hold": False,
        "repeat": False,
        "chord": False,
        "modifier": False,
    }


def test_provenance_flags_can_be_revoked_after_failed_exploration(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "provenance.json"
    monkeypatch.setattr(provenance, "provenance_path", lambda: path)
    provenance.set_measurement("keyboard", "hold", True)
    assert provenance.load_measurement_flags("keyboard")["hold"] is True
    provenance.set_measurement("keyboard", "hold", False)
    assert provenance.load_measurement_flags("keyboard")["hold"] is False


def test_polyphony_cannot_be_marked_as_verified() -> None:
    try:
        provenance.mark_measurement("keyboard", "polyphony")
    except ValueError as exc:
        assert "Unknown calibration measurement field" in str(exc)
    else:
        raise AssertionError("polyphony must not be accepted as verified without a real N-key test")


def test_guided_clean_requires_convergence_before_verification() -> None:
    class FakeApp:
        _calibration_guide_bounds = {("keyboard", "hold"): (40, 90)}

    app = FakeApp()
    assert provenance._guided_search_converged(app, "keyboard", "hold") is False
    app._calibration_guide_bounds[("keyboard", "hold")] = (64, 68)
    assert provenance._guided_search_converged(app, "keyboard", "hold") is True


def test_reset_removes_only_selected_instrument(tmp_path: Path, monkeypatch) -> None:
    calibration_path = tmp_path / "calibration.json"
    provenance_path = tmp_path / "provenance.json"
    calibration_path.write_text(
        json.dumps({"keyboard": {"minimum_clean_hold_ms": 150}, "guitar": {"minimum_clean_hold_ms": 120}}),
        encoding="utf-8",
    )
    provenance_path.write_text(
        json.dumps({"keyboard": {"hold": True}, "guitar": {"repeat": True}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(adaptive, "calibration_path", lambda: calibration_path)
    monkeypatch.setattr(provenance, "provenance_path", lambda: provenance_path)

    provenance.reset_instrument_calibration("keyboard")

    calibration_payload = json.loads(calibration_path.read_text(encoding="utf-8"))
    provenance_payload = json.loads(provenance_path.read_text(encoding="utf-8"))
    assert "keyboard" not in calibration_payload
    assert "keyboard" not in provenance_payload
    assert "guitar" in calibration_payload
    assert "guitar" in provenance_payload
    assert provenance_payload["_schema_version"] == provenance.PROVENANCE_SCHEMA_VERSION


def test_launchers_install_provenance_after_guidance() -> None:
    for filename in ("modern_launcher.py", "studio_launcher.py"):
        source = Path(filename).read_text(encoding="utf-8")
        assert "from playback_calibration_provenance import install_calibration_provenance" in source
        assert source.index("install_calibration_lab(app)") < source.index("install_guided_calibration(app)")
        assert source.index("install_guided_calibration(app)") < source.index("install_calibration_provenance(app)")
