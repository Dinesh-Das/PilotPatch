# PilotPatch

A local coding agent whose **only runtime reasoning engine is Microsoft Copilot Web**.
Copilot requests local exploration, proposes guarded edits, runs approved tests and
iterates on failures. PilotPatch supplies deterministic Python orchestration.

**Status:** implemented with offline and local Edge tests. A real authorized Microsoft
session is required to validate account-bound workflows. See [validation](docs/validation.md).
No fake connector or alternative model is selectable at runtime.
The latest [audit report](docs/audit-2026-11-09.md) records office-laptop fixes and validation limits.
Use the [office laptop checklist](docs/office-laptop.md) when moving to a managed Windows device.

Source: [Dinesh-Das/PilotPatch](https://github.com/Dinesh-Das/PilotPatch).
See [contribution instructions](CONTRIBUTING.md) for the local workflow and checks.

## Windows setup

See [setup.md](setup.md) for the complete PowerShell setup, existing Edge pairing,
VS Code/fork installation, task commands, recovery and troubleshooting guide.

Audited target: Windows 11 x64, **64-bit CPython 3.11–3.13**, Git and current Microsoft
Edge (120+). Python 3.14+ is excluded by the dependency lock. Windows 10 and ARM64 are
unverified. No administrator rights, Docker, WSL, API keys or background service required.

```powershell
cd D:\MyProjects\PilotPatch
.\setup-windows.ps1
# If needed: .\setup-windows.ps1 -Python 'C:\Path to Python\python.exe'
.\copilot.cmd connect
# Follow the one-time existing-Edge extension setup printed by connect.
.\copilot.cmd login
.\copilot.cmd status
.\copilot.cmd probe
```

Setup creates `.venv`, installs dependencies and the local package. It does not install
or replace Edge, modify script execution policy or change system settings. Use your
approved package index/proxy. If scripts are restricted, install manually:

```powershell
py -3.12 -I -m venv .venv
.\.venv\Scripts\python.exe -I -m pip install --only-binary=:all: -r requirements.txt
.\.venv\Scripts\python.exe -I -m pip install --no-deps -e .
```

To use both `pilotpatch` and `copilot-agent` anywhere in the current PowerShell session:

```powershell
$env:Path = "D:\MyProjects\PilotPatch\.venv\Scripts;$env:Path"
cd 'C:\Office\Backend'
copilot-agent "Explore this project and explain its architecture."
copilot-agent --project 'C:\Office\Frontend' "Add a reusable table component and tests."
```

Alternatively call `D:\MyProjects\PilotPatch\copilot.cmd` by absolute path. Your current
working directory remains the target repository.

## Prompt from VS Code or Cursor

An optional desktop extension adds a dedicated **PilotPatch** activity-bar panel.
The panel launches the same Python harness for your selected local workspace; its
prompts still go exclusively to Microsoft Copilot Web. Source-sharing consent,
diffs, command approvals and actual output remain in the integrated task terminal.

1. Install `artifacts/pilotpatch-0.2.2.vsix` through **Extensions → … → Install from VSIX…**.
2. Run **PilotPatch: Open Prompt Panel** from the command palette.
3. Click **Select backend Python** and select this installation's
   `.venv\Scripts\python.exe` (for this checkout: `D:\MyProjects\PilotPatch\.venv\Scripts\python.exe`).
4. Click **Connect existing Edge** and follow its one-time installation/pairing steps.
   Select your already-open Copilot tab in the extension in your current Edge profile.
5. Use **Sign in** and **Test connection**, then enter a task and choose **Run task**.
   Ctrl/Cmd+Enter also submits the prompt.

**Permissions** selects approve/read-only/auto-edit; **Preview only** passes dry-run.
**Change** selects a project in multi-root workspaces. **Stop task** stops only the
owned editor task; inspect backend session state before resuming partial work.
The editor's built-in AI chat remains separate. No model API, fallback provider or
remote AI service is introduced. The backend uses a temporary authenticated loopback
connection to the Edge extension. Remote/WSL hosts and untrusted workspaces are blocked.

Verified with VS Code 1.141.2 and Cursor 3.20.17 (VS Code API 1.128.0) using real
extension hosts and an actual backend diagnostic process. Other compatible forks can
install the same VSIX; compatibility must be checked in the particular fork/version.
See [editor extension instructions](editors/vscode/README.md) for setup, packaging
and security details. Node.js is required only for editor-extension development/tests.

## Account and data destination

The default connection uses **your existing Edge profile and selected Copilot tab**.
Run `connect` once, then in that Edge profile open `edge://extensions`, enable
Developer mode, choose **Load unpacked** and select the folder printed by `connect`.
Open the PilotPatch extension, choose the printed `edge-pairing.json` file, select
your Copilot tab and click **Connect this tab**. This follows Edge's documented
[local extension installation](https://learn.microsoft.com/en-us/microsoft-edge/extensions/getting-started/extension-sideloading).

`login` checks that selected tab and waits for manual sign-in/MFA there only if needed.
It never launches a browser/profile or substitutes another tab. Closing a task leaves
Edge, your tabs and Microsoft sign-in intact. Keep the selected tab open; finish or
clear any unsent draft manually before starting a task. Pairing persists across runs.
Select the tab again after restarting Edge; session-only selection prevents tab ID reuse.
The extension reconnects within about 30 seconds; opening its popup and clicking
Connect wakes it immediately when the local backend is available.

PilotPatch never asks for passwords, imports profiles, exports cookies or bypasses
authentication. `status` requires a visible signed-in account control and a single
composer; a chat box or browser profile portrait alone is insufficient. Open Copilot's
account menu if needed; a visible **Sign out** control also proves sign-in.

`probe` submits a harmless random nonce and verifies the full reply without uploading
source. It tests that session, not a complete coding workflow or office data authorization.

Use `https://copilot.com/chat` in your current Edge profile. No debugging port or
profile copying is needed. See [connection details](editors/edge/README.md).

Status reports `authenticated`, `chat_ready` and `connection_verified` separately.
Sign-in detection does not verify a model reply. `service_error` means the page is
showing a request failure, even when the account is signed in. `status` exits 2 when
chat is not ready; `probe` is the actual prompt/reply connectivity check. A failed
request is never automatically refreshed or resubmitted.

After updating an already running Login task, stop that old task once with Ctrl+C,
then complete `connect` setup and choose **Sign in** again. The old Python process
cannot load a new connector while running. Install the 0.2.2 VSIX for the panel;
the CLI `connect` command also works with older panel versions.

The former dedicated profile is available only by explicit opt-in:
`copilot-agent --browser-connection managed-edge login`, or set
`browser_connection: managed-edge` in operator-owned config. There is no automatic
fallback to this mode. Existing dedicated profiles are left intact during the upgrade.

Microsoft's [personal Copilot terms](https://www.microsoft.com/en-us/microsoft-copilot/for-individuals/termsofuse)
prohibit automated access and explicitly exclude work/Entra accounts. Verify the
applicable enterprise agreements and organization policy for your actual account.
This browser adapter is unofficial. Microsoft 365 Copilot and GitHub Copilot are
distinct services. No enterprise API connector is shipped because tenant licensing,
registration and consent were unavailable; see [research](docs/research.md).

## Coding workflow

```powershell
copilot-agent run "Create a health-check endpoint and tests."
copilot-agent --mode read-only "Explain this repository."
copilot-agent --dry-run "Propose validation improvements."
copilot-agent --share-code --mode auto-edit "Fix the failing tests."
```

Before sharing context, PilotPatch asks you to authorize selected source/instructions
and tool results to Microsoft Copilot using the selected Edge connection's
account. `--share-code` explicitly supplies that consent for the invocation; it
does not approve commands. Initial context is bounded and relevant files are selected
deterministically. Copilot requests further reads/searches incrementally. Project
files, `AGENTS.md` and command output cannot grant permissions or override the user.

Every edit shows a diff, verifies expected hashes or exact content, rechecks after
approval, saves original bytes and writes atomically. Target-repository Git commits,
resets and cleanup are never automatic. The final report separates Copilot's claims
from actual applied paths and executed command exit codes. No checks means no
commands executed, regardless of Copilot's narrative.

| Mode | Reads/search/Git | Ordinary edits | Rename/delete | Commands/tests |
|---|---|---|---|---|
| `approve` (default) | Allowed | Ask with diff | Always ask | Ask or exact preauthorization |
| `read-only` | Allowed | Denied | Denied | Denied |
| `auto-edit` | Allowed | Guarded automatic edits | Always ask | Ask or exact preauthorization |
| `--dry-run` | Allowed | Preview only | Preview only | Not executed |

Dry-run still contacts Copilot after consent. It does not maintain a virtual edited
filesystem: later reads see originals and proposed tests do not run. Ctrl+C cancels
the loop and terminates active command trees. Unknown interrupted outcomes require review.

## Configuration and commands

```powershell
copilot-agent config --init
copilot-agent config
copilot-agent --config 'C:\Users\me\pilotpatch-office.yaml' "Fix validation."
```

Config defaults to `%LOCALAPPDATA%\PilotPatch\config.yaml`; use
[config.example.yaml](config.example.yaml). Repository configuration is never loaded
automatically. Preauthorize only exact argument vectors in operator-owned YAML:

```yaml
permission_mode: approve
test_commands:
  unit: ['C:\Office\Backend\.venv\Scripts\python.exe', '-m', 'pytest', '-q']
allowed_commands: []
command_timeout: 120
max_steps: 40
max_context_bytes: 48000
response_timeout: 180
retention_days: 30
```

Copilot can request `run_tests` with `{"name":"unit"}`. The configured test command
is preauthorized. Other commands prompt unless the entire argv matches an allowed
entry. Tests execute arbitrary repository code with your OS user permissions: this
approval boundary is not an OS sandbox. Python, Node/npm, Java/Maven/Gradle, .NET and
other tools work through approved argument vectors. Freeform model text and shell
strings are never executed. Batch arguments containing shell metacharacters are rejected.

| Command | Purpose |
|---|---|
| `connect` | Prepare one-time extension pairing for your current Edge profile |
| `login`, `logout` | Check/wait for sign-in; remove PilotPatch pairing (leave Edge signed in) |
| `status`, `probe` | Account/composer check; harmless real communication check |
| `run "task"` or `"task"` | Start in the current or `--project` directory |
| `resume SESSION_ID` | Rebuild context; select a fresh Copilot chat manually first |
| `diff [SESSION_ID]` | Session proposals or filtered Git text diff against HEAD |
| `history` | Local session IDs, status, project and timestamps |
| `config [--init]` | Display validated config or create a default |
| `doctor [--offline]` | Dependencies/Git/Edge/project permissions and browser connectivity |

Options work before/after commands. `--home` selects private state outside the project.
Exit codes: 0 success, 1 error/denial, 2 failed status/doctor check, 130 cancellation.
In existing-edge mode, logout removes local pairing only. Disconnect in the extension
too. Microsoft account logout/revocation remains manual. Explicit managed-edge logout
retains the former behavior of deleting only PilotPatch's owned dedicated profile.

## Resume and recovery

```powershell
copilot-agent history
copilot-agent diff SESSION_ID
copilot-agent resume SESSION_ID
# Only after manually reconciling an interrupted edit/command:
copilot-agent resume SESSION_ID --resolve-pending skip
```

Tool intents are saved before execution. Repeated identical IDs replay receipts;
ID/payload conflicts fail. Browser timeouts never automatically resubmit accepted
prompts. Resume uses actual saved receipts and re-reads current files; it does not
trust a stale conversation URL. `diff SESSION_ID` includes proposed changes, including
dry-run proposals; inspect receipt `applied` flags and current files to determine outcomes.

Originals and before/after manifests live under
`%LOCALAPPDATA%\PilotPatch\sessions\SESSION_ID\backups`. Compare hashes and later user
edits before restoring manually. New files have a manifest and no original. Protect
state/backups as confidential source. See [security and recovery](docs/security.md).

## Troubleshooting and selector maintenance

- **Missing Edge:** install through an approved software channel; setup never replaces it.
- **Startup failure:** the CLI reports the failed stage and a short `Reason`, such as
  `launching Microsoft Edge` or `opening the Copilot page` with its `net::ERR_...` code.
  Browser logs and authentication URL details are omitted. Follow that specific reason
  when checking installation, certificate trust, proxy or connectivity.
- **An existing sign-in task is running:** finish in that Edge window first. Wait for
  the login task to end before using **Test connection** or another browser command.
  Do not delete the profile or close an active sign-in window to run diagnostics.
- **Expired sign-in:** rerun `login`, handle MFA/challenges manually, then `status` and `probe`.
- **Signed in but unrecognized:** inspect the actual visible DOM and override
  `selectors.signed_in` and `selectors.composer` in your operator YAML.
- **Timeout/ambiguous turn:** verify `selectors.user`, `selectors.assistant`, `selectors.stop`
  and `selectors.completion`. The user selector must match the submitted message.
  The assistant container must include its own message-level completion controls.
  The default requires **Copy message**; generic Copy/code-copy controls are insufficient.
  Surrounding prose is retained so example JSON is rejected by the strict protocol. Do not weaken
  completion into text stability alone: that can execute partially streamed responses.
- **UI drift:** default selectors are candidates; they have not been verified against
  authenticated production Copilot markup. Use `probe` after updating them.
- **TLS/proxy:** configure `proxy_server: 'http://proxy.example:8080'` if required and use
  approved certificate trust. No certificate verification is disabled. Pip uses its
  own approved index/proxy configuration.
- **Profile in use:** exit the other PilotPatch process/Edge session. Profile/task leases
  are exclusive; no remote-debugging port is exposed.
- **Noninteractive denial:** explicitly authorize sharing and exact commands; auto-edit
  covers ordinary guarded edits. Delete/rename still need interactive confirmation.
- **Incomplete generic Git diff:** it filters sensitive/binary/large files and compares
  existing tracked text to HEAD. Use session diff and your Git client for creations/deletions.

Diagnostics omit response/source content and credentials. Never attach Edge profiles,
cookies or unredacted DOM to an issue. No undocumented endpoints, stealth or fallback
providers are implemented.

## Development

```powershell
.\setup-windows.ps1 -Dev
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m build
.\.venv\Scripts\python.exe -m pip_audit -r requirements.txt
```

Local browser fixtures use real headless Edge with requests routed to local HTML;
they never contact Copilot. These checks skip explicitly on hosts without Edge.
The offline fake provider exists only in tests and cannot prove live integration.
After authorization/sign-in, opt in to the account-bound suite:

```powershell
.\.venv\Scripts\python.exe -m pytest -m live --live --live-login -s
```

It checks manual login, session reuse, real prompt/reply, multi-turn conversation,
read-file requests and an actual temporary-project test-failure/edit/repair loop.
No credentials are passed to pytest. See [validation](docs/validation.md) for observed results.

`agent/` handles context, JSON, loop and state; `providers/` and `browser/` manage
Copilot/Edge; `tools/` implements repository/process operations; `security/` enforces
paths/approvals/redaction/storage; `ui/` contains the terminal presentation.
[Protocol](docs/protocol.md) specifies the contract. `examples/sample_project` ships
with passing tests and a suggested live repair exercise.

MIT licensed. Independent software, not affiliated with Microsoft.
