# Studio beta.9 hotfix6

This release refreshes the **BPSR MIDI Studio beta.9** assets attached to Lite release `v3.4.0`.

## Fast precision mode

Real-song testing showed that full-song HQ separation plus the complete Extra quality stack could take roughly four times longer while only slightly cleaning the stems, and the same isolated Piano/Guitar wrong notes could still survive. Hotfix6 moves the default strategy from **more full-song compute** to **targeted wrong-note proof**.

- The normal Audio → Band path now uses the fast Demucs separation route. Auto conversion no longer silently promotes an installed HQ runtime into a full-song BS-RoFormer job.
- The normal Stem Quality selector is removed from the main workspace. The user sees **Separation: Auto (fast)** instead.
- Full-song BS-RoFormer is retained as **Deep separation** inside Advanced for unusually difficult recordings or diagnostics; it is no longer presented as the recommended normal quality mode.
- The old Extra quality control is relabeled **Deep diagnostic model review** and remains off by default.
- Existing HQ, MR-MT3, Mega53 and other heavyweight code is not deleted; it is preserved for explicit diagnostics rather than charged to every normal conversion.

## Wrong-note suppression without a 40-minute run

- Adds an always-on **fast precision sieve** after the existing fusion, rhythm guard and audio-grounded note validator.
- The sieve combines exact note-local audio support, original-mixture support, cross-stem ownership, local pitch classes, nearby phrase register, repetition and beat-grid context.
- Key/scale context is never allowed to delete a note by itself. A chromatic/borrowed note needs additional audio, phrase or rhythm disagreement before rejection.
- Real same-onset Piano/Guitar chords are never dismantled by the tonal-orphan rule.
- Strong independent model support remains protected unless the note simultaneously fails audio, phrase and rhythm checks.

### Targeted specialist budgets

Normal CUDA conversion spends specialist work only around suspicious notes:

- Guitar specialist: at most **18 candidates / 3 regions / 12 seconds** of audio. Candidate neighborhoods are cropped and concatenated before HCQT+Mel extraction, so the six-fold model no longer analyzes the full song.
- Aria-AMT: reused only when already installed, at most **2 regions / 8 seconds**.
- YourMT3+: reused only when already installed and only for high-risk candidates, at most **2 regions / 6 seconds**.
- Mega53 and the full deep cross-check stack remain diagnostic-only because their model-loading cost is not justified for normal songs.

The Guitar specialist is the only new precision runtime prepared by the normal CUDA setup. Aria/YourMT3+/Mega53 are not silently installed by the fast path.

## Runtime / cache

- Studio internal pipeline version: `0.5.0-beta.9-hotfix6`.
- Analysis cache contract: `band-accurate-8`; older hotfix5 musical maps are intentionally not reused.
- Windows executable metadata remains on the established beta.9 release label for compatibility with the existing launcher/release workflow.

## Validation

Focused tests cover removal of a weak audio-grounded tonal orphan, preservation of same-onset chords, preservation of a chromatic note with strong source audio, the normal fast separator policy, the hard targeted-review audio budget and the new Advanced UI wording. Standard Windows Studio/Lite CI remains the release gate.
