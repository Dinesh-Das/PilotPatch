# PilotPatch

PilotPatch is a local coding assistant for Windows. It uses Microsoft Copilot Web to
explain a project, propose edits and run checks you approve. Source sharing, edit approval
and command approval happen in the terminal.

## Start in VS Code

From the PilotPatch folder in PowerShell:

```powershell
.\setup-windows.ps1 -InstallEditor
```

1. In your Edge profile, go to `edge://extensions`, turn on **Developer mode**, and
   click **Load unpacked**. Paste the `edge-extension` folder printed by setup.
2. Open **PilotPatch** from Edge's Extensions menu. Choose the pairing file printed
   by setup if asked. Open Copilot, sign in, and click **Use this tab** in PilotPatch.
3. Open your project in VS Code, click **PilotPatch**, then **Test connection**.
   When Copilot replies, enter a task and click **Run task**.

The setup command installs Python dependencies, prepares the Edge files, registers the
backend with the editor, and builds the VSIX if it is missing. You need Windows 11 x64,
approved 64-bit CPython 3.11–3.13, Git, Edge 120+ and local VS Code. See setup for
Cursor, CLI-only installation and restricted PowerShell.
[Full setup guide](setup.md)

## Build everything

```powershell
.\build.cmd
```

Look in `artifacts` for the Python wheel and source archive, VSIX, Edge ZIP and Windows
offline bundle. The build uses Python and your approved Python package index. For a
local index, use `--wheelhouse PATH`. Use `--no-office` to skip the offline bundle.
For **Load unpacked** in Edge, use the `edge-extension` folder printed by Windows setup.
[Contributor checks](CONTRIBUTING.md)

## Account and data destination

Use an authorized Microsoft Copilot Web account in your current Edge profile.
The Edge popup highlights the only open Copilot tab and asks you to confirm it.
When several Copilot tabs are open, choose the intended one. Confirm the tab again
after restarting Edge. Keep it open with an empty message box while a task runs.

**Test connection** sends a short random marker and verifies the whole reply without
sharing project files. The **ON** badge only shows that the local bridge is active.
Managed devices may prohibit loading the Edge extension or contacting Copilot.
[Office laptop setup and acceptance](docs/office-laptop.md)

Microsoft's personal Copilot terms restrict automated access and exclude work or Entra
accounts. Check the terms and policy for the account you intend to use. Microsoft 365
Copilot and GitHub Copilot are distinct services.
[Microsoft Copilot terms](https://www.microsoft.com/en-us/microsoft-copilot/for-individuals/termsofuse)

See the latest audit for what was verified locally and which checks require your actual
office device and account. [November 24 audit](docs/audit-2026-11-24.md)
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
