from profiles import FIXED_PROFILES, PROFILE_LABELS, allowed_modes_for_unlock, get_fixed_profile


def test_fixed_profiles_are_only_the_three_safe_tiers() -> None:
    assert set(FIXED_PROFILES) == {"tier1", "tier2", "tier3"}
    assert get_fixed_profile("tier1").unlock_tier == "tier1"
    assert get_fixed_profile("tier2").unlock_tier == "tier2"
    assert get_fixed_profile("tier3").unlock_tier == "tier3"
    assert "tier4" not in PROFILE_LABELS.values()


def test_all_fixed_profiles_are_safe_and_never_use_full_range_mode() -> None:
    for profile in FIXED_PROFILES.values():
        assert profile.mode == "stable"
    assert "full" not in allowed_modes_for_unlock("tier1")
    assert "full" not in allowed_modes_for_unlock("tier2")
    assert "full" not in allowed_modes_for_unlock("tier3")
    assert "full" in allowed_modes_for_unlock("tier4")


def test_profiles_have_sensible_chord_simplification() -> None:
    assert FIXED_PROFILES["tier1"].chord_limit == 2
    assert FIXED_PROFILES["tier2"].chord_limit == 3
    assert FIXED_PROFILES["tier3"].chord_limit == 0
