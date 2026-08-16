<#
.SYNOPSIS
    Build Alcohol Tracker into a native Windows executable and installer.

.DESCRIPTION
    Compiles with Nuitka in --standalone mode, then (optionally) packages the
    result with Inno Setup.

    The build is deliberately shaped to avoid antivirus false positives. See
    packaging/windows/ANTIVIRUS.md for the full reasoning; the short version is
    that self-extracting stubs and compressed executables are what generic
    "dropper" heuristics look for, so this build produces a plain directory of
    real compiled binaries and never uses --onefile or UPX.

.PARAMETER SignThumbprint
    SHA1 thumbprint of an Authenticode code-signing certificate in the current
    user's certificate store. When supplied, the executable and the installer are
    both signed and timestamped. This is the single most effective thing you can
    do about false positives.

.EXAMPLE
    .\build.ps1
    .\build.ps1 -SignThumbprint A1B2C3... -SkipTests
#>
param(
    [switch]$SkipTests,
    [switch]$NoShortcut,
    [switch]$NoInstaller,
    [string]$SignThumbprint,
    [string]$TimestampUrl = "http://timestamp.digicert.com",
    [string]$Version = "1.3.0.0",
    [string]$Publisher = "Alcohol Tracker Project"
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

$VenvPython     = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$NuitkaBuildDir = Join-Path $ProjectRoot "build_nuitka"
$DistDir        = Join-Path $ProjectRoot "dist\AlcoholTracker"
$ExePath        = Join-Path $DistDir "AlcoholTracker.exe"
$IconPath       = Join-Path $ProjectRoot "packaging\windows\AlcoholTracker.ico"
$InstallerScript= Join-Path $ProjectRoot "packaging\windows\installer.iss"
$InstallerOut   = Join-Path $ProjectRoot "dist\installer"

Write-Host "Alcohol Tracker build $Version" -ForegroundColor Cyan
Write-Host "Project: $ProjectRoot"

function Find-SignTool {
    $onPath = Get-Command signtool.exe -ErrorAction SilentlyContinue
    if ($onPath) { return $onPath.Source }
    $candidates = Get-ChildItem "${env:ProgramFiles(x86)}\Windows Kits\10\bin" -Filter signtool.exe -Recurse -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -match "\\x64\\" } |
        Sort-Object FullName -Descending
    if ($candidates) { return $candidates[0].FullName }
    return $null
}

function Find-InnoSetup {
    $onPath = Get-Command iscc.exe -ErrorAction SilentlyContinue
    if ($onPath) { return $onPath.Source }

    # Inno Setup installs per-machine or (via winget) per-user, so check both.
    foreach ($root in @($env:ProgramFiles, ${env:ProgramFiles(x86)}, "$env:LOCALAPPDATA\Programs")) {
        if (-not $root) { continue }
        foreach ($edition in @("Inno Setup 6", "Inno Setup 7")) {
            $candidate = Join-Path $root "$edition\ISCC.exe"
            if (Test-Path $candidate) { return $candidate }
        }
    }

    $uninstallKeys = @(
        "HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*",
        "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*",
        "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*"
    )
    foreach ($key in $uninstallKeys) {
        $entry = Get-ItemProperty $key -ErrorAction SilentlyContinue |
            Where-Object { $_.DisplayName -like "*Inno Setup*" -and $_.InstallLocation } |
            Select-Object -First 1
        if ($entry) {
            $candidate = Join-Path $entry.InstallLocation "ISCC.exe"
            if (Test-Path $candidate) { return $candidate }
        }
    }
    return $null
}

function Invoke-Sign {
    param([string]$Path)
    if (-not $SignThumbprint) { return }

    $signtool = Find-SignTool
    if (-not $signtool) { throw "-SignThumbprint was given but signtool.exe could not be found (install the Windows SDK)." }

    Write-Host "Signing $(Split-Path $Path -Leaf)..." -ForegroundColor Cyan
    # Timestamping matters: without it the signature stops validating the day the
    # certificate expires, and an expired signature is worse than none.
    & $signtool sign /fd SHA256 /td SHA256 /tr $TimestampUrl /sha1 $SignThumbprint /q $Path
    if ($LASTEXITCODE -ne 0) { throw "signtool failed for $Path (exit $LASTEXITCODE)" }
}

if (-not (Test-Path $VenvPython)) {
    Write-Host "Creating local virtual environment..."
    python -m venv .venv
}

Write-Host "Installing/updating dependencies..."
& $VenvPython -m pip install --disable-pip-version-check -r requirements.txt

Write-Host "Checking Python syntax..."
& $VenvPython -m compileall -q alcohol_tracker tests | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Syntax check failed" }

if (-not $SkipTests) {
    Write-Host "Running tests..."
    & $VenvPython -m unittest discover -s tests
    if ($LASTEXITCODE -ne 0) { throw "Tests failed" }
}

if (-not (Test-Path $IconPath)) {
    Write-Host "Generating application icon..."
    & $VenvPython (Join-Path $ProjectRoot "packaging\windows\make_icon.py")
}

Write-Host "Building windowed executable (Nuitka, native compile)..." -ForegroundColor Cyan
if (Test-Path $NuitkaBuildDir) { Remove-Item $NuitkaBuildDir -Recurse -Force }

# NOTE: --standalone (a real directory of DLLs), never --onefile. A onefile build
# unpacks itself into %TEMP% and executes from there at every launch, which is
# behaviourally identical to a dropper and is the main reason packed Python apps
# get flagged. Nothing here is compressed or obfuscated either.
& $VenvPython -m nuitka `
    --standalone `
    --python-flag=-m `
    --deployment `
    --lto=yes `
    --jobs=0 `
    --enable-plugin=pyside6 `
    --windows-console-mode=disable `
    --windows-icon-from-ico=$IconPath `
    --output-dir=$NuitkaBuildDir `
    --output-filename=AlcoholTracker.exe `
    --company-name=$Publisher `
    --product-name="Alcohol Tracker" `
    --file-version=$Version `
    --product-version=$Version `
    --file-description="Alcohol Tracker - personal drink journal" `
    --copyright="$Publisher" `
    --trademarks="Alcohol Tracker" `
    --assume-yes-for-downloads `
    alcohol_tracker
if ($LASTEXITCODE -ne 0) { throw "Nuitka build failed (exit $LASTEXITCODE)" }

# Compiling the package (with --python-flag=-m) rather than __main__.py directly
# is what Nuitka recommends, and names the output after the package.
$BuiltDist = Join-Path $NuitkaBuildDir "alcohol_tracker.dist"
if (-not (Test-Path $BuiltDist)) {
    throw "Build finished but Nuitka output was not found at $BuiltDist"
}

if (Test-Path $DistDir) { Remove-Item $DistDir -Recurse -Force }
New-Item -ItemType Directory -Path (Split-Path $DistDir) -Force | Out-Null
Move-Item $BuiltDist $DistDir
Remove-Item $NuitkaBuildDir -Recurse -Force

if (-not (Test-Path $ExePath)) {
    throw "Build finished but executable was not found at $ExePath"
}

# Ship only what runs. Leftover sources, caches and test files add nothing at
# runtime and give scanners more surface to be unhappy about.
Write-Host "Cleaning distribution..."
Get-ChildItem $DistDir -Recurse -Include "__pycache__" -Directory -ErrorAction SilentlyContinue |
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
Get-ChildItem $DistDir -Recurse -Include "*.pdb", "*.pyc", "*.pyi", "*.lib", "*.exp" -File -ErrorAction SilentlyContinue |
    Remove-Item -Force -ErrorAction SilentlyContinue

Invoke-Sign $ExePath

$SizeMb = [math]::Round(((Get-ChildItem $DistDir -Recurse -File | Measure-Object Length -Sum).Sum / 1MB), 1)
Write-Host "Executable ready: $ExePath ($SizeMb MB)" -ForegroundColor Green

if (-not $NoInstaller) {
    $Iscc = Find-InnoSetup

    if ($Iscc) {
        Write-Host "Building installer (Inno Setup)..." -ForegroundColor Cyan
        New-Item -ItemType Directory -Path $InstallerOut -Force | Out-Null
        & $Iscc `
            "/DAppVersion=$Version" `
            "/DAppPublisher=$Publisher" `
            "/DSourceDir=$DistDir" `
            "/DIconFile=$IconPath" `
            "/O$InstallerOut" `
            $InstallerScript
        if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed (exit $LASTEXITCODE)" }

        $Installer = Get-ChildItem $InstallerOut -Filter "*.exe" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
        if ($Installer) {
            Invoke-Sign $Installer.FullName
            Write-Host "Installer ready: $($Installer.FullName)" -ForegroundColor Green
        }
    } else {
        Write-Host "Inno Setup not found - skipping installer." -ForegroundColor Yellow
        Write-Host "  Install it from https://jrsoftware.org/isdl.php, then re-run this script."
    }
}

if (-not $NoShortcut) {
    Write-Host "Creating/updating desktop shortcut..."
    $Desktop = [Environment]::GetFolderPath("Desktop")
    $ShortcutPath = Join-Path $Desktop "Alcohol Tracker.lnk"
    $Shell = New-Object -ComObject WScript.Shell
    $Shortcut = $Shell.CreateShortcut($ShortcutPath)
    $Shortcut.TargetPath = $ExePath
    $Shortcut.WorkingDirectory = Split-Path $ExePath
    $Shortcut.IconLocation = $ExePath
    $Shortcut.Description = "Alcohol Tracker"
    $Shortcut.Save()
    Write-Host "Shortcut: $ShortcutPath"
}

if (-not $SignThumbprint) {
    Write-Host ""
    Write-Host "This build is UNSIGNED." -ForegroundColor Yellow
    Write-Host "Code signing is the single biggest factor in avoiding antivirus and"
    Write-Host "SmartScreen warnings. See packaging/windows/ANTIVIRUS.md for options."
}

Write-Host "Build complete." -ForegroundColor Green
