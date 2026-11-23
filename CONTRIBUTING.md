# Contributing to PilotPatch

The repository is [Dinesh-Das/PilotPatch](https://github.com/Dinesh-Das/PilotPatch).
Access requires permission while the repository is private. Follow [AGENTS.md](AGENTS.md)
and [setup.md](setup.md) before changing the project.

## Local workflow

Work on `main` unless the operator explicitly selects another branch. Keep each
commit focused and review its staged diff. Do not commit private pairing files,
browser profiles, credentials, virtual environments or generated packages.

Microsoft Copilot Web is the sole runtime reasoning provider. Fake providers belong
only in tests. Changes must preserve source-sharing consent, permission checks,
repository path confinement and unknown-outcome handling.

## Checks

From the repository root in PowerShell, after completing development setup:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
node --test tests/edge_connection.test.cjs
node --test editors/vscode/test/*.test.js
.\build.cmd
```

The full Python suite requires installed Edge, Node.js and the isolated Chromium
test browser described in setup.md. Account-bound tests remain explicitly gated;
report them separately from offline/local-fixture results.
The build produces packages in `artifacts/`. Pass `--no-office` to skip gathering
Windows runtime wheels or `--wheelhouse PATH` to use an approved local index.

Describe the problem, resulting behavior, checks performed and any remaining
validation limits when submitting changes. Use the issue tracker for reproducible
bugs, with versions and sanitized logs. Keep tokens, source secrets and account
credentials out of issues and screenshots.
