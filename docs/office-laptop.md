# Office laptop setup and acceptance

Use a fresh local installation on the office laptop. The audited target is Windows
11 x64 with approved **64-bit CPython 3.11–3.13**, Git and Microsoft Edge 120 or newer.
The full local suite was executed on Python 3.12; other Python versions' Windows
binary availability is checked separately. Python 3.14+ is excluded by this lock.
Windows 10 and native ARM64 remain unverified. Playwright's current
[Windows requirements](https://playwright.dev/python/docs/intro#system-requirements)
start at Windows 11 for its managed browser and development fixtures.

## Install locally

Choose a normal local folder you may write, outside OneDrive, redirected Documents,
network shares and junctions. PilotPatch rejects Windows reparse points to preserve
repository confinement; this can include cloud placeholders. Example paths require
no administrator installation and do not depend on a `D:` drive:

```powershell
$PilotPatchRoot = Join-Path $env:LOCALAPPDATA 'Programs\PilotPatch'
$TargetProject = 'C:\REPLACE_WITH_YOUR_APPROVED_LOCAL_PROJECT'
$PilotPatchPython = Join-Path $PilotPatchRoot '.venv\Scripts\python.exe'
$PilotPatchCli = Join-Path $PilotPatchRoot 'copilot.cmd'

# Skip cloning if you extracted the source ZIP into this folder.
git clone 'https://github.com/Dinesh-Das/PilotPatch.git' $PilotPatchRoot
Set-Location -LiteralPath $PilotPatchRoot
.\setup-windows.ps1
# Or select an approved supported interpreter explicitly:
# .\setup-windows.ps1 -Python 'C:\Approved Python\python.exe'
```

Copy source, wheels and the VSIX through your approved transfer route. **Do not copy
`.venv`, `%LOCALAPPDATA%\PilotPatch`, pairing files, browser profiles or sessions from
the other machine.** Virtual environments contain machine-specific interpreter
paths. Create the environment and pair the office Edge profile locally.

If PowerShell scripts are restricted, use the manual commands below with approved
Python 3.12 (or choose installed 3.11/3.13). Activation is unnecessary:

```powershell
py -3.12 -I -m venv (Join-Path $PilotPatchRoot '.venv')
& $PilotPatchPython -I -m pip install --only-binary=:all: -r (Join-Path $PilotPatchRoot 'requirements.txt')
& $PilotPatchPython -I -m pip install --no-deps -e $PilotPatchRoot
```

Use the approved package index, proxy and certificate trust. Runtime dependencies
install as wheels, without Rust/C++ compilers. Editable source installation also
needs `hatchling` and its editable-build helper `editables` from the approved index.
An approved prebuilt
`pilotpatch-0.2.2-py3-none-any.whl` can replace that editable install using
`pip install --no-deps WHEEL_PATH`; it already contains the Edge extension assets.
Node.js, a Playwright browser download and development dependencies are unnecessary
for normal existing-Edge operation. They are needed only for development checks or
building a missing VSIX. A fresh Git checkout does not include generated artifacts.

If you received the audited `PilotPatch-Office-0.2.2.zip`, it includes source, the
wheel, VSIX and a `wheelhouse` for x64 Python 3.11–3.13. After creating `.venv`,
install without contacting a package index:

```powershell
& $PilotPatchPython -I -m pip install --no-index --find-links (Join-Path $PilotPatchRoot 'wheelhouse') --only-binary=:all: -r (Join-Path $PilotPatchRoot 'requirements.txt')
& $PilotPatchPython -I -m pip install --no-index --no-deps (Join-Path $PilotPatchRoot 'dist\pilotpatch-0.2.2-py3-none-any.whl')
```

The bundle does not include Python, Git or Edge; use approved installations of those.
Copilot still requires the laptop's normal authorized network/account access.

## Check on the actual laptop

First run the local checks:

```powershell
& $PilotPatchPython -I -m pip check
& $PilotPatchCli --version
& $PilotPatchCli --project $TargetProject doctor --offline
& $PilotPatchCli --project $TargetProject connect
```

Expect version `0.2.2`, default `existing-edge`, `git: true`, `project_readable: true`,
`project_writable: true`, `edge_found: true` and exit 0. Doctor tests Git execution
and creates/writes/deletes one uniquely owned temporary file to check NTFS write
access. In read-only mode it skips that write probe (`project_writable: null`).
Offline doctor cannot check browser policy, pairing, account access or model replies.

Follow [the Edge pairing steps](../setup.md#3-connect-your-current-edge-profile).
Microsoft documents [Load unpacked](https://learn.microsoft.com/en-us/microsoft-edge/extensions-chromium/getting-started/extension-sideloading)
and organization [extension blocking policy](https://learn.microsoft.com/en-us/deployedge/microsoft-edge-policies/extensioninstallblocklist).
If Developer mode, installation or loopback access is blocked, use your normal IT
process; PilotPatch cannot override those restrictions. The fixed extension ID is
`jhmhehhjehmldcehodmlbopiajhcghki`, and its default local port is `127.0.0.1:57423`.
The existing-Edge connection uses Edge's configured proxy and certificate trust;
`proxy_server` config applies only to the explicit managed-Edge connection.

Run each check separately, waiting for it to finish:

```powershell
& $PilotPatchCli --project $TargetProject login
& $PilotPatchCli --project $TargetProject doctor
& $PilotPatchCli --project $TargetProject probe
```

`doctor` must exit 0 with `chat_ready: true`. Only a successful `probe` verifies a
complete real reply, without sharing project source. This adapter supports public
Copilot hosts listed in the [README](../README.md#account-and-data-destination);
Microsoft 365 Copilot availability alone does not establish adapter compatibility.
Use only the account and destination approved for your work.

After that, use an approved disposable sample project for a read/edit/test task
before confidential work. Inspect the actual diff and command exit codes. A real
multi-turn task remains a separate acceptance check from probe and offline tests.
Install the supplied `pilotpatch-0.2.2.vsix` manually in the chosen local editor,
select this laptop's backend Python path in User Settings, and use **Test connection**.
See [the full setup guide](../setup.md) for recovery and command approvals.
