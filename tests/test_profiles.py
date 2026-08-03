from profiles import (
    FIXED_PROFILES,
    allowed_modes_for_unlock,
    default_profile_code,
    get_fixed_profile,
    profile_labels_for,
)


def test_instrument_profile_counts_and_ranges() -> None:
    assert set(FIXED_PROFILES) == {"keyboard", "guitar", "bass"}
    assert set(FIXED_PROFILES["keyboard"]) == {"tier1", "tier2", "tier3"}
    assert set(FIXED_PROFILES["guitar"]) == {"tier1", "tier2", "tier3"}
    assert set(FIXED_PROFILES["bass"]) == {"tier1", "tier2"}

    assert get_fixed_profile("keyboard", "tier3").unlock_tier == "tier3"
    assert get_fixed_profile("guitar", "tier3").label.endswith("E2–D6")
    assert get_fixed_profile("bass", "tier2").label.endswith("E1–B3")


def test_custom_is_available_for_every_instrument() -> None:
    for instrument in ("keyboard", "guitar", "bass"):
        assert "custom" in profile_labels_for(instrument).values()


def test_only_keyboard_and_guitar_experimental_full_range_allow_full_mode() -> None:
    for instrument in ("keyboard", "guitar"):
        assert "full" not in allowed_modes_for_unlock(instrument, "tier1")
        assert "full" not in allowed_modes_for_unlock(instrument, "tier3")
        assert "full" in allowed_modes_for_unlock(instrument, "tier4")

    assert "full" not in allowed_modes_for_unlock("bass", "tier1")
    assert "full" not in allowed_modes_for_unlock("bass", "tier2")


def test_defaults_are_highest_safe_fixed_profiles() -> None:
    assert default_profile_code("keyboard") == "tier3"
    assert default_profile_code("guitar") == "tier3"
    assert default_profile_code("bass") == "tier2"


def test_bass_profiles_keep_only_lowest_chord_note() -> None:
    assert get_fixed_profile("bass", "tier1").chord_limit == 1
    assert get_fixed_profile("bass", "tier2").chord_limit == 1
