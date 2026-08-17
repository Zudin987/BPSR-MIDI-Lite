@echo off
setlocal
cd /d "%~dp0"
set VERSION=2.5.0

echo ========================================
echo BPSR MIDI Lite v%VERSION% Windows builder
echo ========================================
echo.

where py >nul 2>nul
if errorlevel 1 (
  echo Python was not found.
  echo Install 64-bit Python 3.12 from python.org and enable the Python launcher.
  pause
  exit /b 1
)

if not exist .venv-build\Scripts\python.exe (
  echo Creating private build environment...
  py -3.12 -m venv .venv-build
  if errorlevel 1 goto :error
)

call .venv-build\Scripts\activate.bat

echo Installing build tools...
python -m pip install --upgrade pip
if errorlevel 1 goto :error
python -m pip install -r requirements-build.txt
if errorlevel 1 goto :error

echo Running tests...
python -m pytest -q
if errorlevel 1 goto :error

echo Building standalone EXE...
pyinstaller --noconfirm --clean BPSR-MIDI-Lite.spec
if errorlevel 1 goto :error

if exist release rmdir /s /q release
if exist portable rmdir /s /q portable
mkdir release
mkdir portable\BPSR-MIDI-Lite

copy /y dist\BPSR-MIDI-Lite.exe release\BPSR-MIDI-Lite.exe >nul
copy /y dist\BPSR-MIDI-Lite.exe portable\BPSR-MIDI-Lite\BPSR-MIDI-Lite.exe >nul
copy /y README.md portable\BPSR-MIDI-Lite\README.md >nul
copy /y LICENSE portable\BPSR-MIDI-Lite\LICENSE >nul
copy /y THIRD_PARTY_NOTICES.md portable\BPSR-MIDI-Lite\THIRD_PARTY_NOTICES.md >nul

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "Compress-Archive -Path 'portable\BPSR-MIDI-Lite' -DestinationPath 'release\BPSR-MIDI-Lite-v%VERSION%-Windows-x64.zip' -Force; $h1=(Get-FileHash 'release\BPSR-MIDI-Lite.exe' -Algorithm SHA256).Hash.ToLower(); $h2=(Get-FileHash 'release\BPSR-MIDI-Lite-v%VERSION%-Windows-x64.zip' -Algorithm SHA256).Hash.ToLower(); Set-Content 'release\SHA256SUMS.txt' ($h1 + '  BPSR-MIDI-Lite.exe'); Add-Content 'release\SHA256SUMS.txt' ($h2 + '  BPSR-MIDI-Lite-v%VERSION%-Windows-x64.zip')"
if errorlevel 1 goto :error

echo.
echo Build complete.
echo Direct EXE: dist\BPSR-MIDI-Lite.exe
echo Shareable files: release\
echo.
echo Other users do NOT need Python. They only run BPSR-MIDI-Lite.exe.
pause
exit /b 0

:error
echo.
echo Build failed. Read the error above.
pause
exit /b 1
