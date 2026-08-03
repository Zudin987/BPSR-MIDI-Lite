# First-time GitHub and EXE Build Guide

## What you need

For the easiest method, you only need:

- A GitHub account
- A browser
- The extracted BPSR MIDI Lite source folder

You do not need Python on your own PC when using GitHub Actions.

## Upload the project

1. Create a new public GitHub repository named `BPSR-MIDI-Lite`.
2. Do not create an extra README or licence.
3. Open the extracted source folder.
4. Upload everything inside it so `app.py` appears at the repository root.
5. Make sure `.github/workflows/build-windows.yml` exists. Hidden dot folders can be created or edited directly on GitHub if Windows does not show them.
6. Commit the files.

## Build a test EXE

1. Open the repository's **Actions** tab.
2. Select **Build Windows EXE**.
3. Click **Run workflow**.
4. Leave the release version blank.
5. Wait for a green success mark.
6. Download the artifact from the completed workflow page.
7. Extract and test `BPSR-MIDI-Lite.exe`.

The EXE bundles Python and required libraries. Other users only download and run the EXE; they do not install Python.

## Publish a release

Run the workflow again and enter a new version such as:

`v1.1.1`

The workflow publishes the EXE, portable ZIP and SHA-256 checksums to GitHub Releases.

## Updating later

Upload the newer source files, commit them, then run the workflow again with a new version such as `v0.6.1` or `v0.7.0`.


## Publish v1.1.1 for friends

After the updated source is committed and the normal test build works:

1. Open **Actions → Build Windows EXE**.
2. Click **Run workflow**.
3. Enter `v1.1.1` in `release_version`.
4. Run the workflow and wait for the green check.
5. Open the repository **Releases** page.
6. Share the v1.1.1 release page with friends.
7. Tell normal users to download `BPSR-MIDI-Lite.exe` directly, run it, and accept the Administrator prompt. They do not need Python.

The standalone `.exe` is the recommended public download.
