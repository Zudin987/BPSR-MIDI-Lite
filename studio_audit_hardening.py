"""Post-hotfix6 Studio audit fixes that do not change musical decisions."""
from __future__ import annotations

import copy
import shutil
from pathlib import Path
from typing import Any

_INSTALLED = False


def _sanitize_manifest_value(value: Any) -> Any:
    """Copy a saved Studio value while removing machine-local path metadata."""
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for raw_key, item in value.items():
            key = str(raw_key)
            if key == "cache_job":
                # Internal cache location has no reopen/export purpose and can
                # contain a Windows account name.
                continue
            if key == "model_sha256" and isinstance(item, dict):
                checksums: dict[str, Any] = {}
                for raw_path, digest in item.items():
                    name = Path(str(raw_path)).name or "model"
                    if name in checksums and checksums[name] != digest:
                        name = f"{name}#{str(digest)[:8]}"
                    checksums[name] = _sanitize_manifest_value(digest)
                cleaned[key] = checksums
                continue
            cleaned[key] = _sanitize_manifest_value(item)
        return cleaned
    if isinstance(value, list):
        return [_sanitize_manifest_value(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize_manifest_value(item) for item in value]
    return value


def sanitize_manifest_record(record: dict[str, Any]) -> dict[str, Any]:
    sanitized = _sanitize_manifest_value(copy.deepcopy(record))
    if not isinstance(sanitized, dict):
        raise ValueError("Studio arrangement must be a JSON object")
    return sanitized


def _patch_studio_export_privacy() -> None:
    import studio_band.export as export_module
    import studio_band.pipeline as pipeline_module
    import studio_band_ui as ui_module
    from studio_band.storage import atomic_json, read_json

    original_export = export_module.export_arrangement
    if not getattr(original_export, "_bpsr_public_manifest", False):
        def export_arrangement(*args, **kwargs):
            path = Path(original_export(*args, **kwargs))
            record = read_json(path)
            sanitized = sanitize_manifest_record(record)
            if sanitized != record:
                atomic_json(path, sanitized)
            return path

        export_arrangement._bpsr_public_manifest = True
        export_module.export_arrangement = export_arrangement
        # pipeline.py imported this function by value before the patch layer.
        pipeline_module.export_arrangement = export_arrangement

    original_copy = export_module.copy_export
    if not getattr(original_copy, "_bpsr_public_manifest", False):
        def copy_export(path: Path, folder: Path) -> Path:
            destination = Path(original_copy(path, folder))
            copied_manifest = destination / Path(path).name
            try:
                record = read_json(copied_manifest)
                atomic_json(copied_manifest, sanitize_manifest_record(record))
            except Exception:
                # Do not leave a partially exported legacy project containing
                # machine-local metadata if sanitising the copy fails.
                shutil.rmtree(destination, ignore_errors=True)
                raise
            return destination

        copy_export._bpsr_public_manifest = True
        export_module.copy_export = copy_export
        # studio_band_ui.py imported this function by value before the patch.
        ui_module.copy_export = copy_export


def clear_studio_thread_state() -> None:
    """Drop reviewer context so a failed conversion cannot taint a later one."""
    try:
        from studio_band import fast_precision
        if hasattr(fast_precision._STATE, "context"):
            delattr(fast_precision._STATE, "context")
    except (ImportError, AttributeError):
        pass

    try:
        from studio_band import precision_judges
        for key in (
            "piano_candidates", "guitar_candidates", "mega53_ownership",
            "review_regions", "review_context",
        ):
            if hasattr(precision_judges._STATE, key):
                delattr(precision_judges._STATE, key)
    except (ImportError, AttributeError):
        pass


def _patch_studio_conversion_cleanup() -> None:
    from studio_band import pipeline

    original = pipeline.BandPipeline.convert
    if getattr(original, "_bpsr_audit_state_cleanup", False):
        return

    def convert(self, *args, **kwargs):
        clear_studio_thread_state()
        try:
            return original(self, *args, **kwargs)
        finally:
            clear_studio_thread_state()

    convert._bpsr_audit_state_cleanup = True
    pipeline.BandPipeline.convert = convert


def _walk_widgets(widget):
    yield widget
    try:
        children = widget.winfo_children()
    except Exception:
        children = ()
    for child in children:
        yield from _walk_widgets(child)


def _patch_studio_project_ui() -> None:
    import tkinter as tk
    from studio_band_ui import BandAudioTab

    original_save = BandAudioTab.save
    if not getattr(original_save, "_bpsr_project_wording", False):
        def save(self):
            result = original_save(self)
            try:
                text = str(self.status.get())
                if text.startswith("Exported: "):
                    self.status.set(
                        text + " · Band Mode uses Full Band.mid; keep Arrangement.json to edit later."
                    )
            except (AttributeError, tk.TclError):
                pass
            return result
        save._bpsr_project_wording = True
        BandAudioTab.save = save

    original_use = BandAudioTab.use
    if not getattr(original_use, "_bpsr_project_wording", False):
        def use(self):
            result = original_use(self)
            try:
                if self.manifest and self.record:
                    name = self.record["files"]["full"]
                    if Path(name).name == name:
                        self.app.status_var.set(
                            "Full Band loaded. In Band Mode every player uses this same MIDI, then selects Piano, Guitar, Bass or Drums."
                        )
            except (AttributeError, KeyError, tk.TclError):
                pass
            return result
        use._bpsr_project_wording = True
        BandAudioTab.use = use

    original_init = BandAudioTab.__init__
    if getattr(original_init, "_bpsr_project_wording", False):
        return

    def init(self, app):
        original_init(self, app)
        try:
            self.save_button.configure(text="Save Band Project…")
            self.use_button.configure(text="Load Full Band into Player")
            self.rearrange_button.configure(text="Rebuild parts (no AI)")
            for widget in _walk_widgets(self.workspace):
                try:
                    if widget.winfo_class() == "TButton" and str(widget.cget("text")) == "Open arrangement":
                        widget.configure(text="Open saved project…")
                except (AttributeError, tk.TclError):
                    continue
        except (AttributeError, tk.TclError):
            pass

    init._bpsr_project_wording = True
    BandAudioTab.__init__ = init


def install_studio_audit_hardening() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _patch_studio_export_privacy()
    _patch_studio_conversion_cleanup()
    _patch_studio_project_ui()
    _INSTALLED = True
