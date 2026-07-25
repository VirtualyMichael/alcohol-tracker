param(
    [switch]$SkipTests,
    [switch]$NoShortcut
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$VenvPyInstaller = Join-Path $ProjectRoot ".venv\Scripts\pyinstaller.exe"
$ExePath = Join-Path $ProjectRoot "dist\AlcoholTracker\AlcoholTracker.exe"

Write-Host "Alcohol Tracker build" -ForegroundColor Cyan
Write-Host "Project: $ProjectRoot"

if (-not (Test-Path $VenvPython)) {
    Write-Host "Creating local virtual environment..."
    python -m venv .venv
}

Write-Host "Installing/updating dependencies..."
& $VenvPython -m pip install -r requirements.txt

Write-Host "Checking Python syntax..."
& $VenvPython -m py_compile `
    alcohol_tracker\__main__.py `
    alcohol_tracker\app.py `
    alcohol_tracker\core\calculations.py `
    alcohol_tracker\core\database.py `
    alcohol_tracker\core\settings.py `
    alcohol_tracker\ui\dialogs.py `
    alcohol_tracker\ui\theme.py `
    alcohol_tracker\ui\main_window.py `
    tests\test_core.py

if (-not $SkipTests) {
    Write-Host "Running tests..."
    & $VenvPython -m unittest tests.test_core
}

Write-Host "Building windowed executable..."
& $VenvPyInstaller --noconfirm --windowed --name AlcoholTracker --paths . alcohol_tracker\__main__.py

if (-not (Test-Path $ExePath)) {
    throw "Build finished but executable was not found at $ExePath"
}

if (-not $NoShortcut) {
    Write-Host "Creating/updating desktop shortcut..."
    $Desktop = [Environment]::GetFolderPath("Desktop")
    $ShortcutPath = Join-Path $Desktop "Alcohol Tracker.lnk"
    $Shell = New-Object -ComObject WScript.Shell
    $Shortcut = $Shell.CreateShortcut($ShortcutPath)
    $Shortcut.TargetPath = $ExePath
    $Shortcut.WorkingDirectory = Split-Path $ExePath
    $Shortcut.Description = "Alcohol Tracker"
    $Shortcut.Save()
    Write-Host "Shortcut: $ShortcutPath"
}

Write-Host "Build complete: $ExePath" -ForegroundColor Green
