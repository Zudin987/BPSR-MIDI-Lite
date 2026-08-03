# BPSR MIDI Lite v0.5.2 — First-time GitHub and EXE guide

Created by **MrEz**.

## What you install

For the easiest GitHub build method, install nothing. You only need:

- a GitHub account
- a web browser
- the extracted source project

GitHub builds the Windows EXE. People downloading your final EXE do not need Python.

## Upload the project

1. Extract `BPSR-MIDI-Lite-source-v0.5.2.zip`.
2. Create a new public GitHub repository named `BPSR-MIDI-Lite`.
3. Do not create an extra README or `.gitignore` during repository creation.
4. Open the extracted `BPSR-MIDI-Lite-v0.5.2` folder.
5. Upload the contents so `app.py`, `profiles.py`, `midi_engine.py`, and `player.py` appear directly on the repository's main page.
6. Commit with:

```text
Upload BPSR MIDI Lite v0.5.2
```

### Hidden `.github` and `.gitignore`

Windows may hide dot-prefixed items from the browser upload picker.

For the workflow, open this source file in Notepad:

```text
WORKFLOW_build-windows.yml.txt
```

Then on GitHub choose **Add file → Create new file**, name it:

```text
.github/workflows/build-windows.yml
```

Paste the workflow text and commit it.

For `.gitignore`, choose **Add file → Create new file**, enter `.gitignore`, and paste the contents of the source `.gitignore` file.

## Build the EXE

1. Open the repository's **Actions** tab.
2. Select **Build Windows EXE**.
3. Click **Run workflow**.
4. Leave `release_version` empty for a test build.
5. Wait for the green success check.
6. Open the completed run and download the `BPSR-MIDI-Lite-Windows` artifact.
7. Extract it and test `BPSR-MIDI-Lite.exe`.

## Publish a permanent release

Run the workflow again and enter:

```text
v0.5.2
```

The workflow creates a GitHub Release containing:

- `BPSR-MIDI-Lite.exe`
- `BPSR-MIDI-Lite-Windows-x64.zip`
- `SHA256SUMS.txt`

Use a new version for later updates, such as `v0.5.2` or `v0.6.0`.

## Update an existing repository

Upload and replace the visible files from the v0.5.2 update ZIP, including:

```text
app.py
profiles.py
version_info.txt
build_exe.bat
README.md
END_USER_GUIDE.md
CHANGELOG.md
tests/test_profiles.py
```

Your existing `.github/workflows/build-windows.yml` can remain unchanged if it already uses the v6 GitHub actions. Rebuild the EXE after committing the files.

## SmartScreen

The EXE is portable but unsigned, so Windows may initially show an unknown-publisher warning. Distribute it only through your official GitHub Release and include `SHA256SUMS.txt`.


## v0.5.2 Online Sequencer files

Make sure these files are uploaded at the repository root before rebuilding:

```text
online_sequencer.py
online_sequencer_dialog.py
tests/test_online_sequencer.py
```

No browser extension or API key is required. The feature uses normal HTTPS requests at runtime.
