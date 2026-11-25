# PilotPatch setup guide

## 1. Requirements and paths

Use Windows 11 x64, approved 64-bit CPython 3.11–3.13, Git and Microsoft Edge 120+.
Use local VS Code for the prompt panel. The office guide covers device and account
policy, portable paths and offline installation.
[Office laptop checks](docs/office-laptop.md)

Clone the repository or extract an approved office bundle on this laptop. Start
PowerShell in that folder. Set the target project to a local folder you can access.

```powershell
$PilotPatchRoot = (Get-Location).Path
$TargetProject = 'C:\Work\YourProject'
$PilotPatchPython = Join-Path $PilotPatchRoot '.venv\Scripts\python.exe'
$PilotPatchCli = Join-Path $PilotPatchRoot 'copilot.cmd'
$PilotPatchState = Join-Path $env:LOCALAPPDATA 'PilotPatch'
$PilotPatchVsix = Join-Path $PilotPatchRoot 'artifacts\pilotpatch-0.5.0.vsix'
```

## 2. Install the Python backend

```powershell
.\setup-windows.ps1 -InstallEditor -OpenEdgeSetup
```

This installs and checks the local Python environment, prepares the Edge files, and
registers the backend with PilotPatch in VS Code. With `-InstallEditor`, setup builds
the matching VSIX if needed and installs it. Use `-Python 'C:\Approved Python\python.exe'`
if the script cannot find the approved interpreter. Setup reuses a working environment.
With `-OpenEdgeSetup`, setup opens Edge Extensions and copies the unpacked folder path.
If the environment was copied from another laptop, move it aside and rerun setup.

For manual installation under workplace script restrictions:

```powershell
py -3.12 -I -m venv .venv
& $PilotPatchPython -I -m pip install --only-binary=:all: -r (Join-Path $PilotPatchRoot 'requirements.txt')
& $PilotPatchPython -I -m pip install --no-deps -e $PilotPatchRoot
& $PilotPatchPython -I -m pilotpatch --project $PilotPatchRoot register-editor
```

For an extracted office bundle, install from the included wheels instead of the two
online pip steps:

```powershell
$PilotPatchWheels = Join-Path $PilotPatchRoot 'wheelhouse'
& $PilotPatchPython -I -m pip install --no-index --find-links $PilotPatchWheels --only-binary=:all: -r (Join-Path $PilotPatchRoot 'requirements.txt')
& $PilotPatchPython -I -m pip install --no-index --no-deps (Join-Path $PilotPatchRoot 'dist\pilotpatch-0.5.0-py3-none-any.whl')
```

If you installed manually, use **Extensions → … → Install from VSIX…** in VS Code
and select the versioned file in `artifacts`. Build it with `build.cmd --no-office`
if needed.

## 3. Connect your current Edge profile

Click **PilotPatch → Open Edge setup** in VS Code. It opens Edge Extensions and
copies the folder path. You can also run:

```powershell
& $PilotPatchCli --project $TargetProject connect --open-edge
```

1. In the Edge profile you want to use, open `edge://extensions`. Enable **Developer
   mode** and click **Load unpacked**. In the folder picker, press **Ctrl+L**,
   **Ctrl+V**, and **Enter**, then click **Select Folder**. Use the printed
   `edge-extension` path if the clipboard is unavailable. If PilotPatch is already
   installed from this folder, click **Reload** on its card.
2. Open **PilotPatch** from Edge's Extensions menu and choose the pairing file if
   asked. Open Copilot in that Edge profile and sign in. Click **Use this tab** in
   the PilotPatch popup. Choose the intended tab when more than one is open.

The VS Code panel can copy either path. Keep the pairing file private. Pairing
persists, and you confirm the tab again after restarting Edge. Stop a running task
before changing tabs.

## 4. Verify sign-in and a real Copilot reply

In VS Code, click **Test connection**. From the CLI:

```powershell
& $PilotPatchCli --project $TargetProject probe
```

The test sends a short random marker with no project files and checks the reply.
Edge can take about 30 seconds to reconnect. Click **Reconnect** in the Edge popup
while the test waits to wake it immediately. If the test fails, follow the terminal
message. **Check Microsoft sign-in** in the panel or `login` in the CLI diagnoses
account controls. `status` checks chat readiness without submitting a prompt.

## 5. Chat in VS Code

When connection testing succeeds, ask a question or request a change. Click **Send**
or press **Ctrl+Enter**, then click **Share and send** if authorized. Read replies and
review proposed edits and commands in the sidebar. The default **Review and apply**
mode works through repository reads and drafts automatically. Expand files in the
review to see highlighted edits or select **Open diff** for the full comparison.
The **Apply** button writes the selected files. **Preview only** shows the proposed diffs.
**Troubleshooting** contains **Check this laptop** and setup recovery.

For Cursor and compatible local desktop forks, run the setup command without
`-InstallEditor` and load the same VSIX through **Install from VSIX…**. The
registered backend is shared by editors under the current Windows user.
`pilotpatch.pythonPath` in User Settings can override the registered backend.
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

Stop your PilotPatch tasks. Get the updated source or extract the new office bundle,
then rerun `.\setup-windows.ps1 -InstallEditor`. Reload VS Code if prompted. In the
PilotPatch panel click **Open Edge setup** or **Show Edge setup paths**. In
`edge://extensions`, reload the PilotPatch card. Return to the Edge popup, click
**Use this tab** and rerun **Test connection** in VS Code.

## 10. Development, tests and packages

From the checkout root:

```powershell
.\setup-windows.ps1 -Dev
& $PilotPatchPython -m playwright install chromium
& $PilotPatchPython -m pytest -q
& $PilotPatchPython -m ruff check .
& $PilotPatchPython -m ruff format --check .
node --test tests/edge_connection.test.cjs
node --test editors/vscode/test/*.test.js
.\build.cmd
```

Node.js 20+ and the Playwright Chromium download are only needed for development
checks. The build uses Python and creates all packages under `artifacts`. Use
`--no-office` for a quick build or `--wheelhouse PATH` for approved local wheels.
The offline bundle contains the matching wheel, VSIX and runtime wheels for Windows
x64 Python 3.11–3.13.

After pairing and checking the real Copilot reply, explicitly authorized
live-account validation runs as a separate suite:

```powershell
& $PilotPatchPython -m pytest -m live --live --live-login -s
```

[Validation scope](docs/validation.md)
## 11. Troubleshooting

Start with the offline diagnostic; use the full diagnostic to attach to your selected
tab without submitting a model prompt:

```powershell
& $PilotPatchCli --project $TargetProject doctor --offline
& $PilotPatchCli --project $TargetProject --browser-connection existing-edge doctor
```

| Symptom | Action |
| --- | --- |
| Python opens the Microsoft Store or is missing | Use the approved Python executable with the -Python setup option. |
| Python 3.14+ or 32-bit Python is installed | Select approved 64-bit CPython 3.11–3.13 with `-Python`; this lock does not require compiling native dependencies. |
| Copied `.venv` does not start | Recreate it on this laptop; transfer source/packages, not virtual environments or private state. |
| `code` or `cursor` is not recognized | Use Install from VSIX in your editor. |
| Manifest file is missing or unreadable | In **Load unpacked**, choose the `edge-extension` folder printed by Windows setup or copied from the VS Code panel. Edge looks for `manifest.json` directly inside the selected folder. |
| Existing Edge is not paired | Run `connect`, load the unpacked extension in the current profile, then choose the pairing file and tab. |
| No existing Edge tab connected | Keep Edge open. Check that the extension is enabled in that profile, choose the tab, click Reconnect while the CLI waits. |
| Another PilotPatch browser task is active | Finish it or stop that specific task with Ctrl+C; then retry. |
| Send is disabled during a connection test | Wait for the result or click **Stop connection test**. Your draft stays in the panel. |
| Copilot is signed in but account controls are unrecognized | Open Copilot's own account menu so its Sign out/account controls are visible, then retry `login` or `status`. |
| `service_error` or the red request-failed banner | Inspect/refresh the Copilot tab manually, confirm normal chat works, then rerun `status` and `probe`. Re-pairing alone does not prove the service recovered. |
| Unsent draft in the selected tab | Send or clear that draft yourself. PilotPatch preserves it instead of overwriting it. |
| An earlier PilotPatch test is still in the message box | Open **New chat** on the selected Copilot tab before you try the new connection test. |
| A turn was interrupted by navigation, reload or another user message | Inspect the tab and local history. Start a fresh chat and resume after reviewing unknown outcomes. |
| Edge restarted | Click Use this tab again in the extension; pairing remains saved. |
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
