# PilotPatch implementation plan

The supplied brief is the specification. Build a Python 3.11+ CLI; Microsoft Copilot Web
in a dedicated persistent Edge profile is the exclusive runtime reasoning provider.
No API keys, alternative models, daemon, Docker, WSL, or web UI.

## Ordered slices

1. Strict protocol, validated configuration, path and secret boundaries (unit tests).
2. Repository tools, exact edits, single-file unified patches, backups and approvals
   (real temporary repositories; conflicts, traversal, dry-run and recovery tests).
3. Bounded command runner and durable agent loop (fake provider only in tests;
   multi-turn, deduplication, cancellation and interruption tests).
4. Persistent Edge connector and terminal commands (local DOM fixtures and CLI checks).
5. Windows launch/setup, sample repository, live opt-in tests, documentation and ZIP.

Dependencies follow this order. Each slice is tested and committed on main.
Checkpoints: core security tests; integrated offline suite; packaging and local Edge fixtures.

## Boundaries and decisions

- Untrusted repository/model/tool output never grants permissions.
- Global or explicitly selected operator configuration only; project files cannot authorize tools.
- Read-only, approve (default), and auto-edit modes. Commands require separate approval
  or exact argv preauthorization; rename/delete always need interactive approval.
- Consent before any repository context is shared with the configured Microsoft destination.
- Hash guards, atomic single-file writes and local backups protect existing work.
- A durable pending-action record prevents replay after an ambiguous interruption.
- Browser timeouts never resubmit a possibly accepted prompt automatically.
- Microsoft 365 API is optional in the brief, and deliberately not implemented: no tenant,
  registration, license or administrator consent is available here.

## Risks

Browser markup is not a supported API. Use configurable semantic selectors and stop on ambiguity.
Personal Copilot terms prohibit automated access; work/Entra accounts follow their applicable
enterprise agreements. Do not infer office authorization from account availability.
Real account workflows remain explicitly unverified until opt-in live checks pass.
