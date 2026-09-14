from types import SimpleNamespace

from studio_band import drum_quality


def test_cymbal_classifier_distinguishes_hat_open_ride_and_crash():
    assert drum_quality._cymbal_role(
        sustain=.10, strength=.55, mid_share=.12, air_share=.70
    ) == "CLOSED_HAT"
    assert drum_quality._cymbal_role(
        sustain=.40, strength=.55, mid_share=.12, air_share=.68
    ) == "OPEN_HAT"
    assert drum_quality._cymbal_role(
        sustain=.78, strength=.70, mid_share=.34, air_share=.40
    ) == "RIDE"
    assert drum_quality._cymbal_role(
        sustain=.78, strength=.70, mid_share=.16, air_share=.72
    ) == "CRASH"


def test_provider_patch_replaces_legacy_three_role_fallback():
    old = lambda payload, report: {"events": []}
    legacy = SimpleNamespace(PROVIDERS={"drums_dsp": old})
    providers = SimpleNamespace(_legacy=legacy, PROVIDERS=legacy.PROVIDERS)

    drum_quality._patch_providers(providers)

    replacement = legacy.PROVIDERS["drums_dsp"]
    assert replacement is not old
    assert getattr(replacement, "_bpsr_six_kit_fallback", False) is True
    assert providers.PROVIDERS is legacy.PROVIDERS


def test_cuda_normal_conversion_promotes_drumsep_even_with_cross_check_off():
    calls = []

    class DummyPipeline:
        def _stage(self, client, job, provider, audio, payload, cancel, report,
                   warnings, settings, hardware):
            calls.append((provider, settings.cross_check))
            if provider == "drumsep":
                return {
                    "events": [{"source": "drums", "role": "KICK"}],
                    "provenance": {"provider": "drumsep"},
                }
            return {
                "events": [{"source": "drums", "role": "CLOSED_HAT"}],
                "provenance": {"provider": "drums_dsp"},
            }

    fake_module = SimpleNamespace(BandPipeline=DummyPipeline, Cancelled=RuntimeError)
    drum_quality._patch_pipeline(fake_module)
    settings = SimpleNamespace(cross_check=False, device="auto")
    result = DummyPipeline()._stage(
        None, None, "drums_dsp", "drums.wav", {}, None, lambda *_: None,
        [], settings, SimpleNamespace(cuda=True),
    )

    assert calls == [("drums_dsp", False), ("drumsep", False)]
    assert settings.cross_check is False
    assert result["provenance"]["provider"] == "drumsep"
    assert result["provenance"]["six_kit_primary"] is True
    assert result["six_kit_primary"] is True


def test_cpu_conversion_keeps_six_kit_spectral_fallback_without_model_install():
    calls = []

    class DummyPipeline:
        def _stage(self, client, job, provider, audio, payload, cancel, report,
                   warnings, settings, hardware):
            calls.append(provider)
            return {
                "events": [{"source": "drums", "role": "TOM"}],
                "provenance": {"provider": "drums_dsp"},
            }

    fake_module = SimpleNamespace(BandPipeline=DummyPipeline, Cancelled=RuntimeError)
    drum_quality._patch_pipeline(fake_module)
    settings = SimpleNamespace(cross_check=True, device="cpu")
    result = DummyPipeline()._stage(
        None, None, "drums_dsp", "drums.wav", {}, None, lambda *_: None,
        [], settings, SimpleNamespace(cuda=False),
    )

    assert calls == ["drums_dsp"]
    assert settings.cross_check is True
    assert result["provenance"]["provider"] == "drums_dsp"
