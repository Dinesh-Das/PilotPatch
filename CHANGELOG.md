# Changelog

## 0.2.1 — 2026-11-08

- Revoke old selection when pairing changes and recheck authority after script injection.
- Split submission into preparation and a one-shot, CLI-authorized synchronous commit.
  Revoking the tab, disconnecting or stopping the CLI during preparation prevents Send.
- Require protocol 2 and a versioned content channel. Old workers cannot receive prompts
  and orphaned content listeners cannot act on upgraded commands.
- Preserve substantive prose around JSON and require message-level completion controls;
  generic Copy/code-copy buttons cannot complete a streaming response.
- Fix completed-task terminal rendering and render approval descriptions as literal text.
- Prune expired completed sessions beyond the 100-entry history view and handle abandoned
  legacy lock markers while preserving active task leases.

## 0.2.0 — 2026-11-08

- Default to the user's selected Copilot tab in their current Edge profile through
  a scoped Manifest V3 extension. No browser launch, profile copy or debugging port.
- Add one-time `connect` setup and a Connect existing Edge button in the VS Code panel.
  Pairing persists, the local transport is temporary, and closing a task leaves Edge open.
- Mutually authenticate local requests without sending the private key; encrypt RPC
  bodies with AES-GCM, reject replays, cap response streams and check extension origin. Confine
  each run to one selected tab, reject duplicate commands and preserve unsent drafts.
- Retain the dedicated Playwright profile only as explicit `managed-edge` opt-in.
  Default logout removes pairing without changing the Microsoft account session.
- Test the actual extension/background/broker against local browser fixtures. Live
  account validation remains separate and requires installing/pairing the extension.

## 0.1.2 — 2026-11-08

- Open Copilot's public chat page directly instead of its marketing landing page.
- Recognize account labels without case sensitivity, labelled editable chat inputs,
  and a visible Sign out account menu. A visible Sign in control still prevents
  anonymous/guest chat from being treated as authenticated.
- Follow sign-in completion into a unique chat tab within the owned browser context.
  Active task conversations are never switched to another tab automatically.
- Report sign-in, chat readiness and Copilot service errors separately. Login prints
  progress when the observed state changes; service errors no longer wait for an answer
  that never appeared. No accepted prompt is automatically resubmitted.

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
