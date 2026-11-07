# PilotPatch working rules

- Work directly on `main` and commit there unless the user explicitly selects another branch.
- Never create `codex/*` or automatic task/feature branches.
- Microsoft Copilot Web is the sole runtime reasoning/code generation provider.
- Never add an alternative model, mock runtime mode, undocumented endpoint or auth bypass.
- Fake providers are test-only. Report live account validation separately from offline tests.
- Preserve permission, path, source-sharing and unknown-outcome boundaries.
- Run `python -m pytest -q`, `python -m ruff check .` and package validation for relevant changes.
