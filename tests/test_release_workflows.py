from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LITE_WORKFLOW = ROOT / ".github" / "workflows" / "build-windows.yml"
STUDIO_WORKFLOW = ROOT / ".github" / "workflows" / "build-studio.yml"


def _workflow_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_release_workflows_keep_manual_dispatch_and_support_audited_release_commits():
    for path in (LITE_WORKFLOW, STUDIO_WORKFLOW):
        text = _workflow_text(path)
        assert "workflow_dispatch:" in text
        assert "startsWith(github.event.head_commit.message, '[release v')" in text
        assert "RELEASE_COMMIT_MESSAGE: ${{ github.event.head_commit.message }}" in text
        assert "Release commits must start with [release vX.Y.Z]" in text
        assert "Release version must use vX.Y.Z" in text


def test_studio_release_waits_for_lite_release_before_uploading():
    text = _workflow_text(STUDIO_WORKFLOW)
    wait_index = text.index("Waiting for Lite release")
    upload_index = text.index("gh release upload $tag")
    assert wait_index < upload_index
    assert "AddMinutes(10)" in text


def test_release_workflows_do_not_add_marker_or_publisher_files():
    workflow_text = _workflow_text(LITE_WORKFLOW) + _workflow_text(STUDIO_WORKFLOW)
    assert "marker" not in workflow_text.lower()
    assert "publisher" not in workflow_text.lower()


def test_studio_ci_builds_beta9_zip_and_real_audio_uses_clean_runtime():
    build = _workflow_text(STUDIO_WORKFLOW)
    smoke = _workflow_text(ROOT / ".github" / "workflows" / "studio-band-smoke.yml")
    assert "BPSR-MIDI-Studio-beta.9-Windows.zip" in build
    assert "Compress-Archive" in build
    assert 'BPSR_STUDIO_CLEAN_RUNTIME: "1"' in smoke
    assert "BPSR_STUDIO_BAND_HOME: ${{ runner.temp }}" in smoke
    assert "clean first-use runtime and actual model inference" in smoke


def test_release_assets_cannot_be_replaced_or_attached_to_another_commit():
    lite = _workflow_text(LITE_WORKFLOW)
    studio = _workflow_text(STUDIO_WORKFLOW)
    assert "--clobber" not in lite + studio
    assert "gh release delete-asset" not in studio
    assert "Release $tag already exists" in lite
    assert "--target $env:GITHUB_SHA" in lite
    assert "--json targetCommitish" in studio
    assert "$releaseTarget.Trim() -ne $env:GITHUB_SHA" in studio


def test_downloader_smoke_runs_when_shared_runtime_code_changes():
    smoke = _workflow_text(ROOT / ".github" / "workflows" / "studio-spotdl-smoke.yml")
    for path in (
        "studio_band/progress.py",
        "studio_band/protocol.py",
        "studio_band/runtime.py",
        "studio_band/storage.py",
    ):
        assert smoke.count(f'"{path}"') == 2
