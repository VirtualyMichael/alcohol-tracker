# Alcohol Ingestion Tracker

Local Windows desktop app for logging alcohol ingestions, reviewing prior drinking days, and viewing estimated effect and tolerance timelines.

## Current Features

- Dark-mode PySide6 desktop GUI
- Add, edit, and delete ingestions
- Custom drink presets so common drinks can refill the ingestion form
- Supports shots and fluid ounces with custom ABV
- Automatically defaults new ingestions to the current time
- Local SQLite storage under `%LOCALAPPDATA%\AlcoholTracker`
- Previous drinking days list
- Estimated stacked effect timeline with a current-time `Now` marker
- Approximate tolerance trend with a current-time `Now` marker
- Adjustable estimate assumptions for absorption, elimination, and tolerance decay
- Windowed PyInstaller build with no command line window

## Easy Build

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

## Build Options

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

## Run During Development

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m alcohol_tracker
```

## Test

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_core
```

## Accuracy Note

All effect, BAC-style, and tolerance outputs are estimates for journaling only. They are not medical or legal advice and should not be used to decide whether it is safe to drive or perform risky activities.
