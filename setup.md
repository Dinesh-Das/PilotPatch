# PilotPatch setup guide

This guide covers PilotPatch **0.2.2** on Windows using **your current Edge profile
and an existing Copilot tab**. Microsoft Copilot Web is the only runtime AI provider.
The default connection leaves your Edge window and sign-in open when a task ends.

Run the commands in **PowerShell**. Complete the extension installation, pairing and
Microsoft sign-in steps manually. Commands that submit prompts are identified below.

If the backend and VS Code extension are already installed, set the path variables
in [section 1](#1-requirements-and-paths), then continue at
[Connect your current Edge profile](#3-connect-your-current-edge-profile).

## 1. Requirements and paths

Audited target: Windows 11 x64, 64-bit CPython 3.11–3.13, Git, current Microsoft Edge
(120+), and a Microsoft Copilot account you are authorized to use. Python 3.14+ is
excluded by this dependency lock; Windows 10 and ARM64 remain unverified. See the
[office laptop checklist](docs/office-laptop.md) for portable paths and policy checks.
VS Code or a compatible desktop fork is
needed for the prompt panel. Node.js 20+ is needed only to build/test the extensions.

For a new checkout, clone the GitHub repository first. Skip this command when the
folder already contains your checkout. Private repository access requires your
authorized GitHub account:

```powershell
git clone 'https://github.com/Dinesh-Das/PilotPatch.git' 'D:\MyProjects\PilotPatch'
```

The examples use your existing checkout and target project. Change these two paths
if you move either folder. Set these variables again in each new PowerShell window:

```powershell
$PilotPatchRoot = 'D:\MyProjects\PilotPatch'
$TargetProject = 'D:\MyProjects\Birthday Bash'
$PilotPatchPython = Join-Path $PilotPatchRoot '.venv\Scripts\python.exe'
$PilotPatchCli = Join-Path $PilotPatchRoot 'copilot.cmd'
$PilotPatchState = Join-Path $env:LOCALAPPDATA 'PilotPatch'
$PilotPatchVsix = Join-Path $PilotPatchRoot 'artifacts\pilotpatch-0.2.2.vsix'

Set-Location -LiteralPath $PilotPatchRoot
```

Check the prerequisites and folders:

```powershell
py -3.12 --version
git --version
Test-Path -LiteralPath $PilotPatchRoot
Test-Path -LiteralPath $TargetProject
```

Both folder checks should return `True`. If the Python launcher `py` is unavailable,
use the full path to your Python executable in the manual installation below.
Open your usual Edge window yourself; keep using the profile where Copilot works.

## 2. Install the Python backend

Choose **one** installation method. Virtual environment activation is unnecessary;
the commands call its Python executable directly.

### Method A: setup script

```powershell
Set-Location -LiteralPath $PilotPatchRoot
.\setup-windows.ps1
```

To select a specific installed Python, replace the example path:

```powershell
.\setup-windows.ps1 -Python 'C:\Path\To\Python\python.exe'
```

The script creates `.venv`, installs binary wheels from `requirements.txt`, and installs
PilotPatch from this checkout. It reuses a working local environment and otherwise
selects an installed supported Python version. If an existing `.venv` is broken or
copied from another laptop, setup stops before installing packages; recreate that
environment locally. If PowerShell policy blocks the script, use Method B.

### Method B: manual installation

```powershell
Set-Location -LiteralPath $PilotPatchRoot
py -3.12 -I -m venv .venv
& $PilotPatchPython -I -m pip install --only-binary=:all: -r (Join-Path $PilotPatchRoot 'requirements.txt')
& $PilotPatchPython -I -m pip install --no-deps -e $PilotPatchRoot
```

Without the Python launcher, replace only the environment creation command:

```powershell
& 'C:\Path\To\Python\python.exe' -I -m venv (Join-Path $PilotPatchRoot '.venv')
```

Confirm the installation without contacting Copilot:

```powershell
& $PilotPatchPython -m pip check
& $PilotPatchCli --version
& $PilotPatchCli --help
& $PilotPatchCli --project $TargetProject doctor --offline
```

The version should be `PilotPatch 0.2.2`. The diagnostic output should include
`"browser_connection": "existing-edge"`. If it shows `managed-edge`, change
`browser_connection` in your operator configuration as described in section 7.

## 3. Connect your current Edge profile

Stop an old PilotPatch Login/task process with **Ctrl+C** in its own terminal before
starting another connection. Keep your regular Edge window open.

Prepare the extension and private pairing file:

```powershell
& $PilotPatchCli --project $TargetProject connect
```

This prepares files locally. It does not launch Edge or create a browser profile.
Print the two paths you will select in Edge:

```powershell
Join-Path $PilotPatchState 'edge-extension'
Join-Path $PilotPatchState 'edge-pairing.json'
```

For this Windows account, the paths are:

```text
Extension folder: C:\Users\dines\AppData\Local\PilotPatch\edge-extension
Pairing file:     C:\Users\dines\AppData\Local\PilotPatch\edge-pairing.json
```

Complete these steps **in your current Edge profile**:

1. Open `edge://extensions` in that Edge window.
2. Enable **Developer mode** and choose **Load unpacked**.
3. Select the `edge-extension` folder printed above.
4. Open the **PilotPatch — Existing Edge Connection** extension from Edge's Extensions menu.
5. Under **Pair this profile**, select the printed `edge-pairing.json` file.
6. Open or keep your normal Copilot chat at `https://copilot.com/chat`. Complete any
   Microsoft sign-in and MFA yourself.
7. In the PilotPatch extension, choose that Copilot tab and click **Connect this tab**.

Keep the pairing file private. It is a local connection secret, not a Microsoft
password or cookie. The extension reads it locally; there is no upload step.

Pairing persists across CLI runs. **Select the tab again after restarting Edge.**
Keep the selected tab open and send or clear any unsent draft manually before a task.
Stop a running task before changing the selected tab.

## 4. Verify sign-in and a real Copilot reply

Run these commands **one at a time**, waiting for each to finish:

```powershell
& $PilotPatchCli --project $TargetProject --browser-connection existing-edge login
& $PilotPatchCli --project $TargetProject --browser-connection existing-edge status
& $PilotPatchCli --project $TargetProject --browser-connection existing-edge probe
```

What they establish:

| Command | Expected result |
| --- | --- |
| `login` | Detects public signed-in account controls; waits for manual authentication if needed. |
| `status` | Reports `authenticated: true` and `chat_ready: true` when the selected tab is ready. |
| `probe` | Sends a harmless random marker to Copilot and verifies its complete reply. |

`status` reports `connection_verified: false` because checking controls does not
submit a model prompt. **A successful `probe` is the live communication check.** It
does not upload repository source. The extension's **ON** badge means local transport
is connected; it does not establish that Copilot can answer.

The extension normally reconnects within about 30 seconds of starting a CLI command.
While the command is waiting, open its popup and click **Connect this tab** to wake it.

## 5. Install the VS Code or fork prompt panel

The VSIX must exist first:

```powershell
Test-Path -LiteralPath $PilotPatchVsix
```

If this returns `False`, build the VSIX using section 10. Generated packages are not
tracked in Git, so a fresh Git checkout may not contain one.

For VS Code, if `code` is available on PATH:

```powershell
code --install-extension $PilotPatchVsix --force
code --reuse-window $TargetProject
```

For this machine's VS Code installation, the absolute-path equivalent is:

```powershell
$VSCodeCli = Join-Path $env:LOCALAPPDATA 'Programs\Microsoft VS Code\bin\code.cmd'
& $VSCodeCli --install-extension $PilotPatchVsix --force
& $VSCodeCli --reuse-window $TargetProject
```

For Cursor, if its CLI is available, use this **instead of** the VS Code commands:

```powershell
cursor --install-extension $PilotPatchVsix --force
cursor $TargetProject
```

Other compatible desktop forks can use **Extensions → … → Install from VSIX…**.
Remote/WSL windows and untrusted workspaces are not supported by this local backend.

In your chosen editor:

1. If you updated an already installed extension, run **Developer: Reload Window**.
2. Run **PilotPatch: Open Prompt Panel** from the command palette.
3. Choose **Select backend Python** and select:
   `D:\MyProjects\PilotPatch\.venv\Scripts\python.exe`.
4. Confirm the panel shows the target project you want to change.
5. Use **Connect existing Edge** if you have not completed section 3.
6. Use **Sign in**, then **Test connection**. Let each terminal task finish.
7. Enter a task and click **Run task**, or press **Ctrl+Enter**.

The equivalent **User Settings JSON** entry is:

```json
{
  "pilotpatch.pythonPath": "D:\\MyProjects\\PilotPatch\\.venv\\Scripts\\python.exe"
}
```

Set this in User Settings; workspace settings cannot select the executable. Source
sharing, diffs and command approvals appear in the integrated terminal. The panel's
**Finished** state means the process exited successfully; inspect the actual report
to see which files changed and which checks ran.

## 6. Run tasks from PowerShell

These commands submit selected source/context to Microsoft Copilot after your
source-sharing confirmation. Each example is a separate invocation.

Read and explain the project:

```powershell
& $PilotPatchCli --project $TargetProject --mode read-only run 'Explain this project and identify its main entry points.'
```

Request edits with approval prompts:

```powershell
& $PilotPatchCli --project $TargetProject run 'Fix the login issue and run the relevant tests.'
```

Preview proposed changes:

```powershell
& $PilotPatchCli --project $TargetProject --dry-run run 'Propose improvements to form validation.'
```

Dry-run still contacts Copilot after consent. Project writes and commands are disabled;
later reads see the original files.

Allow ordinary file edits automatically while retaining command approvals:

```powershell
& $PilotPatchCli --project $TargetProject --mode auto-edit run 'Add input validation and tests.'
```

Only when you explicitly authorize sending the selected source/context to Copilot,
`--share-code` supplies that consent without another sharing prompt:

```powershell
& $PilotPatchCli --project $TargetProject --share-code run 'Investigate the failing unit tests.'
```

Limit the agent loop:

```powershell
& $PilotPatchCli --project $TargetProject --max-steps 10 run 'Inspect the current test failures.'
```

The equivalent direct Python invocation is:

```powershell
& $PilotPatchPython -I -m pilotpatch --project $TargetProject run 'Explain the project structure.'
```

To use the installed entry points from any directory in this PowerShell session:

```powershell
$env:Path = (Join-Path $PilotPatchRoot '.venv\Scripts') + ';' + $env:Path
pilotpatch --project $TargetProject status
copilot-agent --project $TargetProject --mode read-only 'Explain this project.'
```

`pilotpatch`, `copilot-agent`, and this checkout's `copilot.cmd` reach the same backend.

## 7. Operator configuration

Configuration defaults to `%LOCALAPPDATA%\PilotPatch\config.yaml`. Initialize it only
when it does not already exist:

```powershell
$PilotPatchConfig = Join-Path $PilotPatchState 'config.yaml'
if (-not (Test-Path -LiteralPath $PilotPatchConfig)) {
    & $PilotPatchCli config --init
}
notepad.exe $PilotPatchConfig
```

Keep these settings for the existing-profile connection:

```yaml
provider: copilot_browser
browser_connection: existing-edge
edge_connect_timeout: 45
permission_mode: approve
response_timeout: 180
```

These are selected settings to edit in the generated config. The full available
configuration is also shown in [config.example.yaml](config.example.yaml).

Display the validated configuration:

```powershell
& $PilotPatchCli config
```

To use a separate operator-owned configuration file, replace this example path:

```powershell
& $PilotPatchCli --config 'C:\Users\dines\pilotpatch-office.yaml' --project $TargetProject run 'Inspect this project.'
```

Repository YAML is never loaded automatically. `test_commands` and `allowed_commands`
preauthorize exact argument vectors; configure them only after reviewing the commands
and repository. `--share-code` does not approve edits or commands.

For separate private state, outside every target project:

```powershell
& $PilotPatchCli --home 'D:\PilotPatchState' --project $TargetProject connect
```

When using a custom `--home`, pair its printed file and pass the same `--home` on
every subsequent command. The VS Code panel uses the default home.

## 8. History, recovery and disconnecting

List saved sessions and inspect the current Git diff:

```powershell
& $PilotPatchCli --project $TargetProject history
& $PilotPatchCli --project $TargetProject diff
```

Copy a real session ID from `history`, then inspect its proposed changes:

```powershell
$PilotPatchSessionId = 'PASTE_SESSION_ID_FROM_HISTORY'
& $PilotPatchCli --project $TargetProject diff $PilotPatchSessionId
```

Before resuming, inspect the terminal, current files and saved receipts. Open a fresh
Copilot chat manually and select that tab in the extension, then run:

```powershell
& $PilotPatchCli --project $TargetProject resume $PilotPatchSessionId
```

If PilotPatch reports an interrupted **local action** with unknown outcome, reconcile
whether it ran first. Only after that review, mark the pending action as skipped:

```powershell
& $PilotPatchCli --project $TargetProject resume $PilotPatchSessionId --resolve-pending skip
```

Do not use this option as a general connection repair. Prompts and unknown local
actions are not automatically replayed. Backups and receipts live under:

```powershell
Join-Path $PilotPatchState 'sessions'
```

To stop the current task, use **Stop task** in the panel or **Ctrl+C** in that task's
terminal. Inspect partial changes before resuming.

To remove backend pairing while preserving your Edge tabs and Microsoft sign-in:

```powershell
& $PilotPatchCli --browser-connection existing-edge logout
```

Also choose **Disconnect this profile** in the Edge extension. To reconnect later,
run `connect`, select its pairing file again, and choose the tab. Microsoft account
sign-out remains a manual action in Copilot/Edge.

## 9. Update an existing installation

Stop PilotPatch tasks first. After obtaining the updated source in this checkout:

```powershell
Set-Location -LiteralPath $PilotPatchRoot
& $PilotPatchPython -I -m pip install --only-binary=:all: -r (Join-Path $PilotPatchRoot 'requirements.txt')
& $PilotPatchPython -I -m pip install --no-deps -e $PilotPatchRoot
& $PilotPatchCli --version
& $PilotPatchCli connect
```

In your current Edge, open `edge://extensions` and click **Reload** for the PilotPatch
extension. Existing pairing is reused unless you previously logged out. Select your
tab again if needed. Install the matching rebuilt VSIX and reload the editor:

```powershell
code --install-extension $PilotPatchVsix --force
```

Finally rerun `login`, `status` and `probe` from section 4. An already running Python
task cannot load new connector code until it is restarted.

Version 0.2.1 and later require Edge extension protocol 2. A previous extension is rejected
before it receives a prompt; run `connect`, **Reload** the Edge extension and select
the tab again. Existing Copilot tabs stay open. A reply requires a distinct message-level
completion control such as **Copy message**; generic Copy/code-copy buttons do not count.

## 10. Development, tests and packages

Run this section only when developing PilotPatch or building missing packages.
These commands run repository test/build code and install development dependencies.
Install Node.js 20+ before running the full Python suite too: some Python tests render
the editor panel through Node. Use either the direct development install below or
`./setup-windows.ps1 -Dev` from the checkout.

```powershell
Set-Location -LiteralPath $PilotPatchRoot
& $PilotPatchPython -m pip install -e ($PilotPatchRoot + '[dev]')
& $PilotPatchPython -m playwright install chromium
& $PilotPatchPython -m pytest -q
& $PilotPatchPython -m ruff check .
& $PilotPatchPython -m ruff format --check .
& $PilotPatchPython -m pip check
```

The Chromium download is for isolated extension test fixtures. Normal existing-Edge
runtime does not need a Playwright browser download. Offline tests use local HTML
fixtures or test-only providers; they do not validate your live Microsoft account.

Run the JavaScript checks, with Node.js 20+ installed:

```powershell
node --version
npm --version
node --test tests/edge_connection.test.cjs
npm --prefix editors/vscode test
```

Build the Python wheel and source distribution, and audit locked dependencies:

```powershell
& $PilotPatchPython -m build
& $PilotPatchPython -m pip_audit -r requirements.txt
Get-ChildItem -LiteralPath (Join-Path $PilotPatchRoot 'dist')
```

Build the VSIX:

```powershell
New-Item -ItemType Directory -Path (Join-Path $PilotPatchRoot 'artifacts') -Force | Out-Null
Push-Location (Join-Path $PilotPatchRoot 'editors\vscode')
try {
    npm exec --ignore-scripts --package=@vscode/vsce -- vsce package --no-dependencies --out $PilotPatchVsix
}
finally {
    Pop-Location
}
```

For explicitly authorized live-account acceptance testing, finish pairing and the
probe first, then run the following separately. These tests submit real model prompts
and include reads/edits/test execution in a temporary sample project:

```powershell
& $PilotPatchPython -m pytest -m live --live --live-login -s
```

Live test results must be reported separately from offline tests. See
[docs/validation.md](docs/validation.md) for the recorded validation scope.

## 11. Troubleshooting

Start with the offline diagnostic; use the full diagnostic to attach to your selected
tab without submitting a model prompt:

```powershell
& $PilotPatchCli --project $TargetProject doctor --offline
& $PilotPatchCli --project $TargetProject --browser-connection existing-edge doctor
```

| Symptom | Action |
| --- | --- |
| Python opens the Microsoft Store or is missing | Use the installed Python's full path with setup Method A or B. |
| Python 3.14+ or 32-bit Python is installed | Select approved 64-bit CPython 3.11–3.13 with `-Python`; this lock does not require compiling native dependencies. |
| Copied `.venv` does not start | Recreate it on this laptop; transfer source/packages, not virtual environments or private state. |
| `code` or `cursor` is not recognized | Use the absolute VS Code CLI above or Install from VSIX in your editor. |
| Existing Edge is not paired | Run `connect`, load the unpacked extension in the current profile, then choose the pairing file and tab. |
| No existing Edge tab connected | Keep Edge open. Check that the extension is enabled in that profile, choose the tab, click Connect while the CLI waits. |
| Another PilotPatch browser task is active | Finish it or stop that specific task with Ctrl+C; then retry. |
| Copilot is signed in but account controls are unrecognized | Open Copilot's own account menu so its Sign out/account controls are visible, then retry `login` or `status`. |
| `service_error` or the red request-failed banner | Inspect/refresh the Copilot tab manually, confirm normal chat works, then rerun `status` and `probe`. Re-pairing alone does not prove the service recovered. |
| Unsent draft in the selected tab | Send or clear that draft yourself. PilotPatch preserves it instead of overwriting it. |
| A turn was interrupted by navigation, reload or another user message | Inspect the tab and local history. Start a fresh chat and resume after reviewing unknown outcomes. |
| Edge restarted | Choose your Copilot tab again in the extension; pairing remains saved. |
| Extension files were updated but behavior is unchanged | Run `connect`, reload the Edge extension, restart the old CLI task, then reselect the tab. |
| Port 57423 is in use | Stop the known PilotPatch task using it. If necessary, change the port in the private pairing file and select that file again in the extension. |

The default workflow requires no remote-debugging flags, profile copying, credentials
export or replacement AI provider. An organization's extension/automation restrictions
must be handled through its normal administrator process.

## 12. Command and option reference

Prefix each command below with `& $PilotPatchCli --project $TargetProject`, or use
`pilotpatch` / `copilot-agent` after adding the virtual environment to PATH.

| Command | Purpose |
| --- | --- |
| `connect` | Prepare extension files and one-time local pairing. |
| `login` | Check the selected tab and wait for manual sign-in if needed. |
| `status` | Read account/chat controls; exit 2 if chat is not ready. |
| `probe` | Submit a harmless nonce and verify a real complete Copilot reply. |
| `run 'task'` or `'task'` | Start an agent task in the selected project. |
| `history` | List saved local sessions. |
| `diff` | Show filtered current Git changes. |
| `diff SESSION_ID` | Show saved proposals for a session. |
| `resume SESSION_ID` | Rebuild task context from saved state and receipts. |
| `config` | Show validated operator configuration. |
| `config --init` | Create configuration only if the file does not already exist. |
| `doctor` | Check dependencies/project and attach to the configured browser connection. |
| `doctor --offline` | Check local prerequisites without a browser connection. |
| `logout` | In existing-edge mode, remove backend pairing and leave Microsoft sign-in intact. |

| Option | Meaning |
| --- | --- |
| `--project PATH` | Target local project; defaults to the current working directory. |
| `--home PATH` | Private state directory, outside the target project. |
| `--config PATH` | Explicit operator-owned YAML file. |
| `--browser-connection existing-edge` | Use the selected tab in your current Edge profile. |
| `--browser-connection managed-edge` | Explicit legacy mode that opens a separate PilotPatch-owned profile. This guide uses existing-edge. |
| `--mode approve` | Ask before edits and commands; default mode. |
| `--mode read-only` | Permit exploration; deny edits and commands. |
| `--mode auto-edit` | Permit guarded ordinary file edits; commands and destructive operations retain their approval rules. |
| `--dry-run` | Preview writes; do not apply edits or run commands. Still contacts Copilot after sharing consent. |
| `--share-code` | Explicitly authorize source/context sharing for this invocation. |
| `--max-steps NUMBER` | Bound the agent loop. |
| `--resolve-pending skip` | On resume, acknowledge an interrupted local action after manually reconciling it. |
| `--offline` | For doctor: skip the browser connection. |
| `--init` | For config: create the default config file if absent. |
| `--help` | Show built-in CLI usage. |
| `--version` | Show the installed PilotPatch version. |

Exit codes: **0** success; **1** error/denial; **2** status or diagnostic failure;
**130** cancellation. Only a successful live probe verifies Copilot communication;
successful offline tests or sign-in detection establish different checks.
