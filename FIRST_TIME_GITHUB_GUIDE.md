# First-time GitHub, EXE build, and release guide

This method requires only a GitHub account and a web browser. You do **not** need to install Python, Git, Visual Studio, or PyInstaller on your PC.

## What ordinary users need

After you build and publish the program, users only download and run:

```text
BPSR-MIDI-Lite.exe
```

or extract:

```text
BPSR-MIDI-Lite-Windows-x64.zip
```

They do not install Python.

---

# Part 1 — Prepare the project folder

1. Download the `BPSR-MIDI-Lite-source-v0.4.1.zip` supplied to you.
2. Right-click it and choose **Extract All**.
3. Open the extracted `BPSR-MIDI-Lite-v0.4.1` folder.
4. Confirm that you can see files such as:

```text
app.py
midi_engine.py
player.py
README.md
requirements.txt
BPSR-MIDI-Lite.spec
.github
```

The `.github` folder is important because it contains the automatic Windows builder.

Do not upload the outer ZIP as one file. Upload the extracted project contents.

---

# Part 2 — Create a GitHub account

1. Open `https://github.com/`.
2. Select **Sign up**.
3. Complete the email verification.
4. Sign in.

---

# Part 3 — Create the repository

1. In GitHub, click the **+** button near the top-right.
2. Choose **New repository**.
3. Repository name:

```text
BPSR-MIDI-Lite
```

4. Description, for example:

```text
A lightweight MIDI keyboard player for Blue Protocol: Star Resonance
```

5. Choose **Public** if you want everyone to see the source and download releases.
6. Leave **Add a README**, `.gitignore`, and licence initialization unchecked because the project already includes them.
7. Click **Create repository**.

---

# Part 4 — Upload the project using only the browser

1. On the empty repository page, click **uploading an existing file**.
   - On a non-empty repository, use **Add file → Upload files**.
2. Open the extracted project folder in File Explorer.
3. Press `Ctrl+A` to select all project files and folders.
4. Drag them into the GitHub upload area.
5. Wait until every file finishes uploading.
6. Confirm that `.github/workflows/build-windows.yml` is included.
7. In **Commit changes**, enter:

```text
Upload BPSR MIDI Lite v0.4.1
```

8. Choose **Commit directly to the main branch**.
9. Click **Commit changes**.

Important: files must appear at the repository root. You should see `app.py` immediately on the main repository page, not inside an extra nested folder.

---

# Part 5 — Enable and run the Windows EXE builder

1. Open the repository's **Actions** tab.
2. If GitHub asks whether to enable workflows, enable them.
3. In the left sidebar, select **Build Windows EXE**.
4. Click **Run workflow**.
5. Keep the branch as `main`.
6. For the first test, leave **release_version** blank.
7. Click the green **Run workflow** button.
8. Wait for the run to appear, then open it.
9. Wait until the job has a green check mark.

The workflow performs these tasks automatically:

- creates a temporary Windows machine;
- installs Python and build dependencies on that temporary machine;
- runs all automated tests;
- packages the app as a standalone EXE;
- creates a portable ZIP and SHA-256 checksum file.

Nothing is installed on your own PC.

---

# Part 6 — Download the first EXE

1. Open the completed workflow run.
2. Scroll to **Artifacts**.
3. Click `BPSR-MIDI-Lite-Windows`.
4. GitHub downloads an artifact ZIP.
5. Extract it.
6. Inside you should find:

```text
BPSR-MIDI-Lite.exe
BPSR-MIDI-Lite-Windows-x64.zip
SHA256SUMS.txt
```

Run the EXE on your Windows PC and test Stable mode first.

Workflow artifacts are temporary build outputs. Use a GitHub Release for the permanent public download.

---

# Part 7 — Publish a permanent GitHub Release automatically

After testing the EXE:

1. Return to **Actions → Build Windows EXE**.
2. Click **Run workflow**.
3. Enter this in **release_version**:

```text
v0.4.1
```

4. Click **Run workflow**.
5. Wait for the green check mark.
6. Return to the repository main page.
7. On the right side, open **Releases**.
8. You should see `BPSR MIDI Lite v0.4.1` with these files:

```text
BPSR-MIDI-Lite.exe
BPSR-MIDI-Lite-Windows-x64.zip
SHA256SUMS.txt
```

Share the Release page with users instead of sharing the temporary Actions artifact.

For a later update, use a new version such as:

```text
v0.4.1
v0.5.0
v1.0.0
```

Do not reuse an existing version tag.

---

# Part 8 — If automatic Release publishing fails

A failure containing `Resource not accessible by integration` usually means the workflow token cannot write a Release.

1. Open repository **Settings**.
2. In the left sidebar, open **Actions → General**.
3. Find **Workflow permissions**.
4. Select **Read and write permissions**.
5. Save.
6. Run the workflow again with the version field.

The normal build-only workflow can still produce a downloadable artifact without publishing a Release.

---

# Part 9 — Update the repository later

Browser-only method:

1. Open the repository.
2. Use **Add file → Upload files**.
3. Upload the updated files, replacing the old versions.
4. Commit the changes.
5. Run the workflow again.
6. Use a new Release version.

For frequent development, GitHub Desktop is easier, but it is optional.

---

# Optional local build on your own PC

You only need this if you do not want to use GitHub Actions.

## Install

1. Install 64-bit Python 3.12 from `https://www.python.org/downloads/windows/`.
2. During installation, enable the Python launcher (`py`).
3. Extract the project.
4. Double-click `build_exe.bat`.

The script creates a private virtual environment, downloads the required packages, runs tests, and builds the EXE.

Outputs:

```text
dist\BPSR-MIDI-Lite.exe
release\BPSR-MIDI-Lite.exe
release\BPSR-MIDI-Lite-v0.4.1-Windows-x64.zip
release\SHA256SUMS.txt
```

Only the builder needs Python. People receiving the EXE do not.

---

# SmartScreen and signing

The EXE is standalone but not digitally signed. New unsigned applications commonly have no SmartScreen reputation, so Windows may show an unknown-publisher warning.

For early private testing, users should only trust the EXE from your official GitHub Release and verify the provided SHA-256 checksum. For wider public distribution, the proper long-term improvement is Authenticode code signing; that normally requires purchasing or obtaining a trusted signing certificate.

Never tell users to disable antivirus globally.

## Updating an existing v0.4 repository to v0.4.1

1. Extract the new source ZIP.
2. In your GitHub repository, choose **Add file → Upload files**.
3. Drag everything from inside the extracted `BPSR-MIDI-Lite-v0.4.1` folder onto the upload page.
4. Confirm that `app.py`, `version_info.txt`, `build_exe.bat`, `tests/test_library.py`, and `.github/workflows/build-windows.yml` are included.
5. Commit with `Update to v0.4.1 MIDI library`.
6. Run **Actions → Build Windows EXE → Run workflow** again.
7. For a permanent release, enter `v0.4.1` in the release-version box.

Do not upload your personal `.mid` files. The included `.gitignore` excludes everything inside `MIDI` except the instruction text file.

