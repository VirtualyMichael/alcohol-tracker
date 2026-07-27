# Alcohol Ingestion Tracker

Local desktop app for logging alcohol ingestions, reviewing prior drinking days, and viewing estimated effect and tolerance timelines. Windows and Linux are both supported.

## Current Features

- Dark-mode PySide6 desktop GUI
- Add, edit, and delete ingestions
- Custom drink presets so common drinks can refill the ingestion form
- Quick Add bar with a dropdown covering every saved preset, plus one-click buttons for your top drinks
- Supports shots and fluid ounces with custom ABV
- Automatically defaults new ingestions to the current time
- Local SQLite storage under `%LOCALAPPDATA%\AlcoholTracker` on Windows, or `~/.local/share/AlcoholTracker` on Linux
- Previous drinking days list
- Estimated stacked effect timeline with a current-time `Now` marker
- Approximate tolerance trend with a current-time `Now` marker
- Adjustable estimate assumptions for absorption, elimination, and tolerance decay
- Windowed PyInstaller build with no command line window

## Easy Build (Windows)

Double-click:

```text
build.bat
```

That script will:

- create `.venv` if needed
- install/update dependencies
- run syntax checks
- run unit tests
- build the no-console Windows executable
- create/update the desktop shortcut

The packaged app is created at:

```text
dist\AlcoholTracker\AlcoholTracker.exe
```

The desktop shortcut is:

```text
%USERPROFILE%\Desktop\Alcohol Tracker.lnk
```

### Build Options (Windows)

From PowerShell:

```powershell
.\build.ps1
.\build.ps1 -SkipTests
.\build.ps1 -NoShortcut
```

From Command Prompt:

```bat
build.bat
build.bat -SkipTests
build.bat -NoShortcut
```

## Build (Linux)

```bash
./build.sh
./build.sh --skip-tests
./build.sh --no-shortcut
```

That script creates `.venv`, installs dependencies, runs tests, builds the executable with PyInstaller, and (unless `--no-shortcut` is passed) writes an application launcher to `~/.local/share/applications/alcohol-tracker.desktop`.

The packaged app is created at:

```text
dist/AlcoholTracker/AlcoholTracker
```

### Running a downloaded release (Linux)

Extract `AlcoholTracker-<version>-linux-x86_64.tar.gz`, then either run the binary directly:

```bash
./AlcoholTracker/AlcoholTracker
```

or install a desktop launcher for it:

```bash
./install.sh
```

## Run During Development

Windows (PowerShell):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m alcohol_tracker
```

Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m alcohol_tracker
```

## Test

Windows:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_core
```

Linux:

```bash
.venv/bin/python -m unittest tests.test_core
```

## Accuracy Note

All effect, BAC-style, and tolerance outputs are estimates for journaling only. They are not medical or legal advice and should not be used to decide whether it is safe to drive or perform risky activities.
