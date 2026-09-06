from __future__ import annotations

from studio_band.progress import PipelineProgress, ProgressEvent, progress_context, progress_line
from studio_band.protocol import RuntimeSetupError
from studio_band_ui import _job_error


def test_first_time_setup_maps_real_byte_progress_without_faking_pipeline_precision():
    updates = []
    flow = PipelineProgress(updates.append)
    flow.setup("Transkun", 0, 2, ProgressEvent(
        "Downloading isolated runtime",
        activity="download",
        stage_fraction=.05,
        bytes_done=684 * 1024**2,
        bytes_total=1400 * 1024**2,
    ))
    event = updates[-1]
    assert event.phase == "First-time setup" and event.activity == "download"
    assert event.overall == .45  # 18% setup weight * first half * 5% completed substep
    line = progress_line(event, 42)
    assert "684 MB" in line and "1.4 GB" in line and "(49%)" in line
    assert "0%" in line and "00:42" in line
    assert "cached for future songs" in progress_context(event)


def test_indeterminate_stage_holds_weighted_boundary_until_real_completion():
    updates = []
    flow = PipelineProgress(updates.append)
    flow.setup_ready()
    flow.stage("separate", activity="cpu")
    flow.detail("separate", ProgressEvent("Long separator inference", activity="cpu"))
    assert updates[-1].overall == 23
    assert updates[-1].indeterminate is True
    flow.complete("separate")
    assert updates[-1].overall == 40 and updates[-1].indeterminate is False


def test_cached_runtime_check_does_not_claim_first_time_setup():
    updates = []
    PipelineProgress(updates.append).setup_ready("Runtime and transcription components ready")
    event = updates[-1]
    assert event.phase == "Preparing conversion"
    assert event.activity == "cache"
    assert "First-time setup" not in progress_context(event)


def test_actual_model_download_is_identified_as_first_time_setup():
    updates = []
    flow = PipelineProgress(updates.append)
    flow.stage("piano", activity="cpu")
    flow.detail("piano", ProgressEvent("Downloading Transkun model", activity="download"))
    event = updates[-1]
    assert event.phase == "First-time setup"
    assert "cached for future songs" in progress_context(event)


def test_skipped_stage_advances_without_claiming_it_ran():
    updates = []
    flow = PipelineProgress(updates.append)
    flow.skip("cross_check", "Musical cross-check disabled")
    event = updates[-1]
    assert event.overall == 93
    assert event.activity == "skipped"
    assert "Cross-checking musical evidence" not in event


def test_weighted_progress_never_moves_backwards_on_retry_messages():
    updates = []
    flow = PipelineProgress(updates.append)
    flow.stage("piano")
    flow.detail("piano", ProgressEvent("Transcribing Piano", stage_fraction=.5, activity="gpu"))
    flow.detail("piano", ProgressEvent("Retrying this stage on CPU", stage_fraction=.1, activity="cpu"))
    values = [event.overall for event in updates]
    assert values == sorted(values)
    assert updates[-1].activity == "cpu"


def test_runtime_setup_error_keeps_concise_ui_copy_and_full_technical_log():
    error = _job_error(RuntimeSetupError(
        "piano",
        "Could not prepare Transkun runtime. Windows dependency installation failed.",
        "setuptools warning\nerror: Microsoft Visual C++ 14.0 or greater is required",
    ), "conversion")
    assert error["summary"] == (
        "Conversion/setup failed · Could not prepare Transkun runtime. "
        "Windows dependency installation failed."
    )
    assert "setuptools warning" not in error["summary"]
    assert "Microsoft Visual C++" in error["technical"]
