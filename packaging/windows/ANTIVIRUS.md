# Antivirus false positives

Alcohol Tracker is a local, offline desktop app. It makes no network connections,
installs no services or drivers, and needs no administrator rights. When a scanner
flags it as `Trojan`, `Dropper`, `Wacatac`, `Agent`, `susgen` or similar, that is a
**generic machine-learning / heuristic verdict**, not a specific signature match.

This document explains what causes those verdicts, what this build already does
about them, and the one remaining step only the publisher can take.

## Why an innocent app gets flagged

Generic detections fire on a *combination* of weak signals, not on any single one:

| Signal | Why it looks bad | Status here |
| --- | --- | --- |
| Self-extracting stub that unpacks to `%TEMP%` and executes | Literally what a dropper does | **Avoided** — `--standalone`, never `--onefile` |
| Compressed / packed executable (UPX and friends) | Used to hide payloads from static analysis | **Avoided** — no packer at any stage |
| No Authenticode signature | No accountable publisher | **Outstanding** — see below |
| No icon, no version resources | Real products have them; throwaway malware doesn't | **Fixed** — full metadata + icon |
| Requests administrator rights | Huge escalation signal from an unknown publisher | **Avoided** — `asInvoker`, per-user install |
| Never seen before / almost no downloads | Reputation systems distrust rare files by default | Inherent to any new release |

A Python app compiled to a native binary trips several of these at once by
default, which is why "it's just a Python GUI" and "it's detected as a dropper"
routinely happen together.

## What this build already does

- **Nuitka `--standalone`, never `--onefile`.** The output is an ordinary folder
  of compiled binaries and DLLs. Nothing unpacks itself at runtime. This is the
  single biggest structural difference from a default PyInstaller build, which
  extracts to a temp directory on every launch.
- **No UPX or any other executable compression.** The installer uses ordinary
  LZMA, but the installed `.exe` on disk is never packed.
- **`--deployment`** strips Nuitka's debugging and compatibility scaffolding.
- **Complete version resources** — company, product, version, description,
  copyright, trademarks — plus a real multi-resolution icon.
- **`asInvoker` manifest and a per-user installer.** No UAC prompt, ever. The app
  writes only to its own folder under `%LOCALAPPDATA%`.
- **Inno Setup** for packaging rather than a bespoke self-extractor. Its stub is
  one of the most widely whitelisted binaries in existence.
- **Clean distribution** — no stray sources, caches, `.pdb` or test files.
- **PyInstaller removed** from `requirements.txt` entirely.

## The remaining step: code signing

Everything above removes *avoidable* causes. It cannot fully solve the problem,
because the dominant remaining signal is that the binary has no verified
publisher. **An Authenticode signature is the fix**, and it requires buying a
certificate tied to a verified identity — so it is the one part of this that
cannot be done in the build script.

Once you have a certificate in your Windows certificate store, the build signs
both the executable and the installer automatically:

```powershell
.\build.ps1 -SignThumbprint "<your certificate SHA1 thumbprint>"
```

Options, cheapest first (verify current pricing — these change):

- **Azure Trusted Signing** — roughly $10/month, operated by Microsoft. Best value
  by a wide margin. Individuals can qualify, but the identity generally needs
  around three years of verifiable history.
- **OV certificate** (Sectigo, DigiCert, SSL.com, …) — roughly $200–400/year.
  Reputation with SmartScreen builds up gradually as downloads accumulate.
- **EV certificate** — roughly $400–700/year. Grants SmartScreen reputation
  immediately rather than earning it over time.

Since June 2023 the CA/Browser Forum requires code-signing private keys to live on
certified hardware (a USB token or cloud HSM) for OV as well as EV. Budget for
that; it is why the build takes a certificate-store thumbprint rather than a
`.pfx` file and password.

**Self-signed certificates do not help.** They only validate on machines that
already trust your root, and asking users to install a root certificate is worse
advice than shipping unsigned.

Always timestamp signatures (the build does, via `/tr`). Without a timestamp the
signature stops validating the moment the certificate expires.

## Verifying and reporting

Upload each release to [VirusTotal](https://www.virustotal.com) and expect to read
the results carefully rather than aiming for a clean sweep:

- **0/70 is not a realistic target for an unsigned new binary.** A handful of
  no-name engines flagging generic `.susgen`/`.ml` verdicts is normal and is
  largely ignored by users and platforms.
- **What actually matters** is whether the *major* engines are clean: Microsoft
  Defender, and the mainstream commercial suites your users actually run.
- Note that VirusTotal detections tend to *decrease* over the days following a
  release as the file's prevalence grows.

Report any false positive you do hit — vendors fix them, usually within days:

- **Microsoft Defender:** <https://www.microsoft.com/en-us/wdsi/filesubmission>
  (choose "Software developer", submit the file, describe what it is)
- Most other vendors have an equivalent "submit a false positive" form.

Signing first makes these reports far more likely to be actioned quickly, because
the vendor can whitelist your *certificate* rather than one file hash — which then
covers every future release automatically.
