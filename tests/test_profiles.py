from profiles import FIXED_PROFILES, allowed_modes_for_unlock, get_fixed_profile


def test_fixed_profiles_lock_expected_unlock_tiers() -> None:
    assert get_fixed_profile("tier1").unlock_tier == "tier1"
    assert get_fixed_profile("tier2").unlock_tier == "tier2"
    assert get_fixed_profile("tier3").unlock_tier == "tier3"
    assert get_fixed_profile("tier4").unlock_tier == "tier4"


def test_beginner_profiles_never_use_full_range_mode() -> None:
    assert FIXED_PROFILES["tier1"].mode == "stable"
    assert FIXED_PROFILES["tier2"].mode == "stable"
    assert "full" not in allowed_modes_for_unlock("tier1")
    assert "full" not in allowed_modes_for_unlock("tier2")


def test_late_profiles_use_full_unlocked_ranges() -> None:
    assert FIXED_PROFILES["tier3"].mode == "full"
    assert FIXED_PROFILES["tier4"].mode == "full"
    assert "full" in allowed_modes_for_unlock("tier3")
    assert "full" in allowed_modes_for_unlock("tier4")


def test_profiles_have_sensible_chord_simplification() -> None:
    assert FIXED_PROFILES["tier1"].chord_limit == 2
    assert FIXED_PROFILES["tier2"].chord_limit == 3
    assert FIXED_PROFILES["tier3"].chord_limit == 0
    assert FIXED_PROFILES["tier4"].chord_limit == 0
