"""One-time exact-match source and regression version migration for v3.5.3."""
from pathlib import Path

changes = {
    'modern_launcher.py': [
        ('# v3.5.2 fixes Audio-to-Band drum transcription and dense Drum playback while\n# keeping Lite free of Studio-only AI/audio runtimes. Release metadata and\n# regression contracts are synchronized to 3.5.2.\napp.APP_VERSION = "3.5.2"',
         '# v3.5.3 hardens Cloud Band host authorization and desktop input safety\n# without adding Studio-only AI/audio runtimes to Lite.\napp.APP_VERSION = "3.5.3"'),
    ],
    'build_exe.bat': [('set VERSION=3.5.2', 'set VERSION=3.5.3')],
    'version_info.txt': [
        ('filevers=(3, 5, 2, 0)', 'filevers=(3, 5, 3, 0)'),
        ('prodvers=(3, 5, 2, 0)', 'prodvers=(3, 5, 3, 0)'),
        ("FileVersion', u'3.5.2'", "FileVersion', u'3.5.3'"),
        ("ProductVersion', u'3.5.2'", "ProductVersion', u'3.5.3'"),
    ],
    'tests/test_release_version_consistency.py': [
        ('3.5.2', '3.5.3'), ('(3, 5, 2, 0)', '(3, 5, 3, 0)'),
    ],
    'tests/test_v303_regressions.py': [('set VERSION=3.5.2', 'set VERSION=3.5.3')],
    'tests/test_ui_contract.py': [('app.APP_VERSION = "3.5.2"', 'app.APP_VERSION = "3.5.3"')],
    'tests/test_ui_2026_contract.py': [('app.APP_VERSION = "3.5.2"', 'app.APP_VERSION = "3.5.3"')],
    'studio_band/__init__.py': [('VERSION = "0.5.0-beta.9-hotfix9"', 'VERSION = "0.5.0-beta.9-hotfix10"')],
    'tests/test_studio_precision_judges.py': [('VERSION.endswith("hotfix9")', 'VERSION.endswith("hotfix10")')],
}
for filename, replacements in changes.items():
    path = Path(filename)
    text = path.read_text(encoding='utf-8')
    for old, new in replacements:
        if text.count(old) != 1:
            raise RuntimeError(f'Expected exactly one version anchor in {filename}: {old!r}, got {text.count(old)}')
        text = text.replace(old, new, 1)
    path.write_text(text, encoding='utf-8')
    print(f'Updated {filename}')

changelog = Path('CHANGELOG.md')
text = changelog.read_text(encoding='utf-8')
header = '# Changelog\n\n'
assert text.startswith(header) and '## v3.5.3' not in text
text = text.replace(header, header + '''## v3.5.3 (release candidate; not published)

- Fixed Cloud Band host identity spoofing, bound participant identity to a connection, and required an unbroadcast private host credential for host commands and temporary MIDI uploads.
- Preserved existing MIDI on replacement failures and serialized expiry cleanup so a stale file cannot delete new room metadata.
- Fixed coalesced WebSocket handshake frames, bounded fragmented messages, and made room-creation UI errors safe for deferred callbacks.
- Restricted Windows keyboard injection to recognized game executables (or explicitly configured regional names), retaining existing focus-loss cleanup.
- Prevented GitHub release asset replacement, added authorization/storage regressions, a live deployment smoke, and a gated production deployment workflow.
- Studio beta.9 internal hotfix10 includes the shared Band safety fixes; its audio analysis cache contract is unchanged.
- Requires a coordinated client/Worker upgrade and recreation of existing rooms. Production Cloudflare deployment and real-game verification are separate required release gates.

''', 1)
changelog.write_text(text, encoding='utf-8')
print('Updated CHANGELOG.md')

notes = Path('STUDIO_RELEASE_NOTES.md')
text = notes.read_text(encoding='utf-8')
assert text.startswith('# Studio beta.9 hotfix9 - bundled with Lite v3.5.2')
text = '''# Studio beta.9 hotfix10 - planned bundle with Lite v3.5.3

This release candidate includes the common Cloud Band host authentication, MIDI storage and WebSocket reliability fixes, plus verified-target keyboard injection. The visible Studio product stays beta.9, the internal package label advances to `0.5.0-beta.9-hotfix10`, and the audio analysis cache remains `band-accurate-10` because transcription has not changed. The v3.5.3 release is **not yet published**; deployment and real-game verification are required first. Existing rooms must be recreated after the coordinated Cloudflare upgrade.

## Previous release history

''' + text
notes.write_text(text, encoding='utf-8')
print('Updated STUDIO_RELEASE_NOTES.md')
