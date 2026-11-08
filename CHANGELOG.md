# Changelog

## 0.1.1 — 2026-11-08

- Browser startup failures report the failed stage and a sanitized underlying cause,
  including network error codes, instead of hiding all failures behind one generic message.
- Preserve the original failure if browser cleanup also fails; always attempt driver
  cleanup and profile-lease release, including cancelled startup.
- Added startup, cancellation, redaction and active-profile isolation regression tests.

## 0.1.0 — 2026-11-08

- Initial Microsoft Copilot-only Python coding harness and Windows CLI.
- Dedicated VS Code/Cursor prompt panel, terminal approvals, selected-workspace routing,
  permission/preview controls, actual task status and a locally installable VSIX.
- Persistent Edge login, visible authentication checks, harmless live probe and doctor.
- Bounded repository exploration, strict JSON tools, approvals, guarded atomic edits,
  backups, approved test/command execution and iterative error feedback.
- Durable task history, receipt deduplication, interrupted-action reconciliation and resume.
- Offline tests, real Edge DOM fixtures, opt-in account-bound tests and sample repository.
- Runtime dependency lock audited without known advisories. Live account acceptance remains
  unverified and is documented separately.
