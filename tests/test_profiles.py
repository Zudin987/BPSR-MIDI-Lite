from profiles import FIXED_PROFILES, allowed_modes_for_unlock, default_profile_code, get_fixed_profile, profile_labels_for


def test_categories_and_raw_mode_are_the_only_user_profiles() -> None:
    assert set(FIXED_PROFILES["keyboard"]) == {"tier1", "tier2", "tier3", "tier4", "raw"}
    assert set(FIXED_PROFILES["guitar"]) == {"tier1", "tier2", "tier3", "raw"}
    assert set(FIXED_PROFILES["bass"]) == {"tier1", "tier2", "raw"}
    for instrument in ("keyboard", "guitar", "bass"):
        values = set(profile_labels_for(instrument).values())
        assert "raw" in values
        assert "custom" not in values


def test_category_labels_follow_game_progression() -> None:
    assert get_fixed_profile("keyboard", "tier4").label.startswith("Category 4")
    assert get_fixed_profile("guitar", "tier3").label.startswith("Category 3")
    assert get_fixed_profile("bass", "tier2").label.startswith("Category 2")


def test_raw_is_no_remap_no_chord_limit() -> None:
    for instrument in ("keyboard", "guitar", "bass"):
        raw = get_fixed_profile(instrument, "raw")
        assert raw.mode == "stable"
        assert raw.mapping == "skip"
        assert raw.chord_limit == 0


def test_no_selectable_profile_exposes_page_mode() -> None:
    for profiles in FIXED_PROFILES.values():
        for profile in profiles.values():
            assert profile.mode == "stable"
    for instrument in ("keyboard", "guitar", "bass"):
        for tier in ("tier1", "tier2", "tier3", "tier4"):
            assert allowed_modes_for_unlock(instrument, tier) == ("stable",)


def test_defaults_are_highest_normal_categories() -> None:
    assert default_profile_code("keyboard") == "tier4"
    assert default_profile_code("guitar") == "tier3"
    assert default_profile_code("bass") == "tier2"


def test_bass_normal_profiles_remain_monophonic_but_raw_does_not() -> None:
    assert get_fixed_profile("bass", "tier1").chord_limit == 1
    assert get_fixed_profile("bass", "tier2").chord_limit == 1
    assert get_fixed_profile("bass", "raw").chord_limit == 0


def test_all_profiles_keep_v21_articulation_defaults() -> None:
    for profiles in FIXED_PROFILES.values():
        for profile in profiles.values():
            assert profile.speed == 100
            assert profile.note_length == 100
            assert profile.minimum_note == 70
