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
- Tolerance trend showing the dose needed to match your tolerance-free baseline, with a projected return-to-baseline date
- Adjustable estimate assumptions for absorption, elimination, body composition, and tolerance
- Windowed native build (Nuitka) with no command line window

## How the estimates work

The effect timeline is a one-compartment pharmacokinetic model:

- each drink enters the gut, spread over however long you spent drinking it
- it moves gut to bloodstream by **first-order absorption** (set by *Absorption time*, after an *Absorption lag* for gastric emptying)
- the bloodstream pool drains by **zero-order elimination** — a constant drinks/hour, because alcohol dehydrogenase is saturated at ordinary drinking levels

That is why the curve rises in steps as drinks land and then falls in a straight line.

BAC uses the **Watson** total-body-water regressions by default (height, weight, age, sex), which is how modern forensic BAC estimation is done. Ethanol dissolves in body water rather than fat, so composition — not just mass — sets the concentration a dose produces. The older fixed-factor **Widmark** model is still selectable in Settings; it tends to overestimate BAC for lean or tall people.

Tolerance is driven by **CNS exposure**, not drink counts: the BAC curve integrated above 0.02% for each session, in `%BAC-hours`. Because both the height and the duration of the curve grow together, one heavy night counts for far more than the same drinks spread thinly across a week. That exposure decays with the *Tolerance half-life*, and maps onto a **bounded** dose multiplier — chronic tolerance plateaus rather than growing without limit, so the model tops out at the configured ceiling (2x by default).

All of it is tunable in Settings, because these constants genuinely vary between people.

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
- build an installer, if Inno Setup is available
- create/update the desktop shortcut

The packaged app is created at:

```text
dist\AlcoholTracker\AlcoholTracker.exe
dist\installer\AlcoholTracker-<version>-setup.exe
```

Building the installer needs [Inno Setup 6](https://jrsoftware.org/isdl.php); the build skips that step with a warning if it isn't installed.

> **Python version for release builds.** Nuitka only fully supports Python up to
> 3.13; newer versions are flagged as experimental and will say so during the
> build. Development on a newer Python is fine, but prefer building the binaries
> you actually ship on the newest Python that Nuitka lists as fully supported.

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
.\build.ps1 -NoInstaller
.\build.ps1 -SignThumbprint "<code signing certificate thumbprint>"
```

From Command Prompt:

```bat
build.bat
build.bat -SkipTests
build.bat -NoShortcut
```

### Antivirus false positives

Compiled Python apps are routinely flagged by generic heuristics as `Trojan` or
`Dropper`. This build is deliberately shaped to avoid that — no `--onefile`
self-extraction, no executable packing, full version metadata and icon, no
administrator rights, and a plain per-user Inno Setup installer.

The remaining piece is Authenticode code signing, which needs a certificate tied
to a verified identity. Pass `-SignThumbprint` once you have one, and both the
executable and the installer are signed and timestamped automatically.

See [packaging/windows/ANTIVIRUS.md](packaging/windows/ANTIVIRUS.md) for the full
reasoning, certificate options, and how to report a false positive to vendors.

## Build (Linux)

```bash
./build.sh
./build.sh --skip-tests
./build.sh --no-shortcut
```

That script creates `.venv`, installs dependencies, runs tests, builds the executable with Nuitka, and (unless `--no-shortcut` is passed) writes an application launcher to `~/.local/share/applications/alcohol-tracker.desktop`.

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
