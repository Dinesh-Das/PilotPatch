# Validation report — 8 November 2026

## Office-laptop repeat audit (0.2.2)

**146 Python tests passed, 5 skipped**; 13 JavaScript checks passed. Ruff, dependency
audits, Python/VSIX builds, installed-wheel asset checks and fresh wheel/source
installations passed. The source setup was executed in real Windows PowerShell 5.1;
both fresh installations used paths with spaces and a local wheelhouse. Binary
availability passed for the corrected x64 CPython 3.11–3.13 locks; the full runtime
suite ran on 3.12. See [the office audit](audit-2026-11-09.md) for reproduced findings,
evidence and limits, and [the office checklist](office-laptop.md) for actual-laptop
acceptance. No Microsoft account or live prompt was used in this validation.

## Repeat audit fixes (0.2.1)

Full suite: **134 passed, 5 skipped**; 13 Node checks passed. Ruff, package builds,
installed-wheel checks, dependency audits and setup command syntax checks passed.
See [the audit report](audit-2026-11-08.md) for six reproduced findings, fixes and
regression evidence. Live account/selector compatibility and a real Copilot reply
remain unverified. Protocol 2 rejects old Edge workers before prompt delivery;
after updating, run `connect`, Reload the Edge extension and select the current tab.

## Existing Edge connection (0.2.0)

Final full suite: **118 passed, 5 skipped**. Ruff checks and formatting, wheel/sdist
build, installed-wheel asset comparison, `pip check`, and runtime dependency audit
passed. The audit reported no known vulnerabilities. The five skips remain four
explicitly gated live-account checks and the Windows symlink-privilege check.

The default now uses a user-installed extension and the explicitly selected Copilot
tab in the current Edge profile. Development never attached to the user's browser,
copied a profile, inspected Microsoft credentials or submitted a live model prompt.

The actual Manifest V3 background worker, packaged content script and local Python
broker were exercised together in headless Chromium with locally fulfilled HTML.
Cases include multiple turns, old-history isolation, account/guest/service errors,
preserving an unsent draft, delayed Send controls, navigation interruption, later
user messages, changing selection, and content-script denial of private pairing storage.
Transport tests reject wrong key/origin/Host, malformed framing, oversized requests,
replayed nonces, stale sessions/results, competing tabs and duplicate submissions.
A replacement listener on the same port could neither authenticate nor read the
pairing secret or encrypted pending answer. A streaming response cap is tested before
buffering. A separate model review found no blocking issues after those fixes.

The real popup rendered without JavaScript errors or horizontal overflow; its local
fixture screenshot is `artifacts/edge-connection-popup.png`. The editor's Connect action
is tested through real DOM events and shell-free command arguments. Thirteen Node
checks pass (nine editor, four Edge). The rebuilt wheel includes the Edge assets and
its installed `connect` setup is checked separately from the source checkout.

The backend and VS Code update were installed locally. `connect` prepared the stable
extension directory and private pairing file without launching Edge. The one-time
Load unpacked, pairing and tab selection are deliberately left to the user in their
current profile. **Live Microsoft sign-in/DOM compatibility and an actual Copilot
reply remain unverified** until setup is complete and `login`, `status`, `probe` pass.
An existing Copilot service-error banner can still prevent a successful live probe.

The sections below retain historical validation results for earlier releases.

## Observed environment

Windows, PowerShell, Python 3.12.14, Git 2.45.2 and installed Microsoft Edge
156.0.4314.58. Runtime dependencies are pinned in `requirements.txt`. Playwright
1.64.1 is required: an initial 1.51 browser startup failure was resolved by updating
to the current compatible release, without changing browser security policy.

## Passed checks

- Full application suite: **72 passed, 5 skipped** (`python -m pytest -q -rs`).
- Five browser fixtures use actual headless Edge and locally fulfilled HTML, covering
  prompt submission, complete streaming response retrieval, historical-turn isolation,
  multiple turns, timeout/no-resubmission, cancellation and positive authentication evidence.
- Seven direct patch cases cover CRLF preservation, missing final newline, empty-base
  creation, separate hunks and rejection of mismatched counts/positions/multiple files.
- Repository tools use real temporary files and Git repositories. Tests cover search,
  ignore rules, redaction, exact replacement, conflicts during review, backups,
  read-only/dry-run, explicit rename/delete denial and executable shadow protection.
- Agent tests use a clearly named test-only fake provider. A real Python subprocess
  fails, Copilot's fake proposal creates the missing module, and the subprocess then
  passes. Other cases cover duplicate receipts, reused IDs, loop limits, format limits,
  cancellation/pending recovery and truthful reporting of actual changes/checks.
- Real process failure, output limits, exact argv preauthorization, timeout and Ctrl+C-style
  asyncio cancellation checks passed. Session reload, retention and path boundaries passed.
- Ruff checks and formatting passed. `pip check` found no broken requirements.
- Runtime lock audit: **no known vulnerabilities** with `pip-audit --no-deps --disable-pip
  -r requirements.txt`. The initial filelock 3.32.7 advisories were resolved by upgrading
  to 4.2.9 and revalidating; no advisory was suppressed. Audit data is a point-in-time
  advisory check, not a guarantee of complete dependency security.
- `setup-windows.ps1` was executed with an explicit Python path against the local venv;
  it installed the lock and editable package successfully. PowerShell parser validation,
  `copilot.cmd`, `copilot-agent.cmd`, console entry points, help and version passed.
- `doctor --offline` confirmed dependencies, Git, Edge and project permissions.
- Actual `doctor` launched a dedicated persistent Edge profile and navigated to the
  public Copilot site: `edge_initialization: true`, `copilot_connectivity: true`.
  This confirms page connectivity only, not account authentication or a model response.
- Sample repository test: **1 passed**.
- Python wheel and source distribution built successfully; a source ZIP is supplied.

## Editor panel follow-up

The dedicated VS Code extension has nine passing Node unit tests and three passing
real Edge webview tests. The latter cover multiline keyboard submission, permission
and preview arguments, safe rendering of hostile-looking workspace names, running/
stopping/error states, and layouts at 320, 768, 1024 and 1440 pixels. No webview
JavaScript errors were observed. A panel screenshot is generated under `artifacts/`.

Isolated real editor hosts verified extension activation, panel command registration,
selected workspace, a native ProcessExecution task launching the actual Python
`doctor`, exit 0, and honest finished-process status in:

- Visual Studio Code 1.141.2.
- Cursor 3.20.17, exposing VS Code API version 1.128.0.

These editor checks used new test profiles and a known local sample folder, with no
repository source submitted to a model. The editor's own built-in extension/service
warnings were separate from PilotPatch. VSIX packaging succeeded and the extension
was installed in the user's VS Code default profile. Backend Python selection remains
a visible per-editor User Setting. NPM audit reports zero dependencies/vulnerabilities
for the extension's dependency-free lockfile. The Python harness is unchanged by
this editor feature; the full combined Python suite now has 75 tests plus the five
previously documented skips. Account-bound Copilot validation remains outstanding.

The audit version change was reviewed against the
[official filelock changelog](https://py-filelock.readthedocs.io/en/latest/changelog.html).
Windows OS utilities are resolved to System32 and Git must resolve outside the target
repository so an untrusted current directory cannot substitute a local executable.

## Explicit skips and outstanding live acceptance

### Login readiness fix (0.1.2)

The user's screenshots showed a chat page and request-error banner while Login still
printed its generic manual-sign-in wait. The prior checker matched only case-sensitive
account/profile labels and inspected only the original tab. An isolated unauthenticated
startup also showed that the old root URL could land on Copilot's marketing page.

Regression fixtures now exercise account label changes, labelled editable inputs,
explicit guest sign-in controls, an opened Sign out menu, owned-context popup/tab
completion, multiple-tab ambiguity, delayed app rendering and service errors before
any assistant answer exists. CLI tests verify sign-in progress and nonzero status
when chat is unavailable. The user's running sign-in process and browser profile
were not changed or closed during development. These fixtures do not establish that
their live account or Microsoft's request service is working.
The full 0.1.2 suite passed with **96 passed, 5 skipped**, plus nine passing editor
tests. Ruff checks/formatting, the wheel/sdist build and editable upgrade passed.
The prior Login task must be restarted once to load this checker; the editor extension
and existing persistent profile are reused.

### Startup diagnostic fix (0.1.1)

A reported VS Code login failure used a generic initialization error. During diagnosis,
the user's subsequent VS Code login process was active and held the dedicated profile.
It was left running as requested. The original failure was not reproduced: an isolated
visible Edge profile opened Copilot successfully; a separate headless startup with the
fix also reached `https://copilot.com/` and released its own lease.

Six new regression tests cover stage/cause reporting, authentication-URL and browser-log
redaction, preservation of the original error when cleanup fails, cancelled startup,
active-profile isolation and unchanged Edge security options. They first reproduced
four failures, then passed after the fix. These checks do not establish the cause of
the original transient failure or validate the user's account authentication.
The complete 0.1.1 suite passed with **81 passed, 5 skipped**; Ruff checks/formatting,
the nine editor tests, wheel/sdist build and editable installation also passed.

Four opt-in live tests were skipped because no authorized signed-in Microsoft
account was provided. One filesystem symlink test was skipped because this Windows
account lacks symlink-creation privilege. Lexical path traversal tests all ran;
the implementation also rejects symlinks/junctions when present.

**Unverified:** manual Microsoft login/MFA, authenticated session reuse, current
authenticated Copilot DOM selector compatibility, actual prompt/reply communication,
real multi-turn reasoning, Copilot-requested file reads/edits, a real Copilot test
failure/correction loop, and actual enterprise expired-session recovery.

The fake-provider and local browser fixtures do not prove these workflows. Do not
claim production or account-bound end-to-end readiness until the following succeed
in an authorized environment:

```powershell
.\copilot.cmd login
.\copilot.cmd status
.\copilot.cmd probe
.\.venv\Scripts\python.exe -m pytest -m live --live --live-login -s
```

Inspect the visible Microsoft account, applicable agreement, organization source
sharing policy and live selectors before using confidential code. No model fallback,
credential bypass, alternative provider or fake runtime mode was used for validation.
