; Inno Setup script for Alcohol Tracker.
;
; Built by build.ps1, which passes AppVersion / AppPublisher / SourceDir / IconFile.
; Compile manually with:
;   iscc /DSourceDir=..\..\dist\AlcoholTracker /DIconFile=AlcoholTracker.ico installer.iss
;
; Deliberately a plain, boring installer: per-user, no admin rights, no drivers,
; no services, no autostart entries, no bundled extras. Every one of those is a
; behaviour antivirus heuristics weigh against an unknown publisher, and none of
; them are things this app needs.

#ifndef AppVersion
  #define AppVersion "1.3.0.0"
#endif
#ifndef AppPublisher
  #define AppPublisher "Alcohol Tracker Project"
#endif
#ifndef SourceDir
  #define SourceDir "..\..\dist\AlcoholTracker"
#endif
#ifndef IconFile
  #define IconFile "AlcoholTracker.ico"
#endif

#define AppName "Alcohol Tracker"
#define AppExeName "AlcoholTracker.exe"

[Setup]
; Keep this GUID stable forever - it is how Windows recognises upgrades of an
; existing install rather than treating each version as a separate product.
AppId={{7C4E1F62-9A3D-4B58-8E17-2F6D0A9C5B41}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
VersionInfoVersion={#AppVersion}
VersionInfoCompany={#AppPublisher}
VersionInfoDescription={#AppName} Setup
VersionInfoProductName={#AppName}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
UninstallDisplayName={#AppName}
UninstallDisplayIcon={app}\{#AppExeName}
OutputBaseFilename=AlcoholTracker-{#AppVersion}-setup
SetupIconFile={#IconFile}

; Per-user install: no UAC prompt at all. An unknown-publisher binary asking for
; administrator rights is one of the strongest signals a scanner can see.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

; LZMA is the standard Inno compressor. This is ordinary installer compression,
; not executable packing - the installed .exe on disk is never compressed.
Compression=lzma2/max
SolidCompression=yes

WizardStyle=modern
DisableProgramGroupPage=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Only remove what the app generated inside its own install directory. The drink
; journal lives in %LOCALAPPDATA%\AlcoholTracker and is intentionally left alone,
; so reinstalling or upgrading never loses the user's history.
Type: filesandordirs; Name: "{app}\__pycache__"
