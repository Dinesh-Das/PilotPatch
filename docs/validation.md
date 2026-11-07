# Validation report — 8 November 2026

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

The audit version change was reviewed against the
[official filelock changelog](https://py-filelock.readthedocs.io/en/latest/changelog.html).
Windows OS utilities are resolved to System32 and Git must resolve outside the target
repository so an untrusted current directory cannot substitute a local executable.

## Explicit skips and outstanding live acceptance

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
