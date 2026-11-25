# Changelog

## 0.5.2 — 2026-11-25

- Show the selected tab, active VS Code link and last verified Copilot reply in the Edge popup.
- Keep the successful reply visible after the connection test finishes.
- Wake the local connection check when the toolbar popup opens. Opening a Copilot tab
  requires a separate click.

## 0.5.1 — 2026-11-25

- Release the Edge connection promptly when a task stops with an open browser request.
- Honor nested Git ignore rules, avoid repeated ignore-file parsing, and skip unchanged
  Git blobs when generating repository diffs.
- Preserve private key redaction in line ranges and Git diffs, and keep resumed
  requests inside the configured context budget.
- Show recorded file changes when an apply is interrupted and flag any write whose
  outcome needs to be checked on disk.

## 0.5.0 — 2026-11-25

- Review draft edits by file with line numbers and highlighted additions and removals.
- Open the original and proposed text in VS Code’s native diff editor.
- Apply selected files, keep rename paths linked, and check for unsaved editor changes
  before writing the selected draft.

## 0.4.2 — 2026-11-25

- Run codebase audits as read-only, multi-turn reviews with automatic source,
  test and configuration batches.
- Wait for audit synthesis and show actual file coverage, including partial results
  when a limit or Copilot response prevents completion.

## 0.4.1 — 2026-11-25

- Recognize the signed-in Copilot profile when its sidebar is collapsed. A visible
  sign-in control still takes precedence.
- Describe the connection test’s readiness check before it submits the probe.

## 0.4.0 — 2026-11-25

- Select **Think Deeper** through the Copilot picker when offered. Use **Auto** when
  it is the best recognized option and report the mode used in VS Code.
- Gather relevant source automatically and continue with local tool requests when
  an edit response ends without proposing changes.
- Prepare a file draft in VS Code, keep subsequent reads in sync with it, and
  show the combined diff for **Apply changes** or **Discard draft**.
- Keep the chat composer visible while the conversation scrolls.

## 0.3.0 — 2026-11-24

- Chat about a project in the VS Code sidebar. Copilot replies inline and recent
  exchanges give follow-up questions context.
- Approve source sharing, review diffs and approve commands in the same sidebar.
  Show applied files and actual command results alongside Copilot’s reply.

## 0.2.6 — 2026-11-24

- Read the visible Copilot reply when the message also contains an empty
  placeholder. Keep the reply tied to the submitted turn.
- Explain why Run task is disabled during a connection test and provide a
  **Stop connection test** button. The terminal reports when Edge connects.

## 0.2.5 — 2026-11-24

- Support Copilot's current rich composer, message layout, and **Copy Response**
  completion control.
- Clear PilotPatch's exact unsent text when Send fails validation before the click.
  Drafts edited by the user and turns with uncertain outcomes require manual review.
- Accept the probe token followed by a single period. Upgrade the unpacked Edge
  extension and reload it before starting a new task.

## 0.2.4 — 2026-11-24

- Open Edge Extensions and copy the unpacked folder path in one action. Use
  **Open Edge setup** in VS Code, `copilot.cmd connect --open-edge`, or the Windows
  setup switch `-OpenEdgeSetup`.
- Clarify the folder picker steps and display the extension as **PilotPatch** in Edge.
- Recognize Copilot's signed-in personal account control in the navigation sidebar
  so the connection check can proceed with the account menu closed.

## 0.2.3 — 2026-11-24

- Build the wheel, source distribution, VSIX, Edge ZIP and offline Windows bundle
  with `build.cmd` from a clean checkout. Packaging requires Python only.
- Windows setup registers its Python backend with the editor and can build and install
  the VS Code extension using `-InstallEditor`. Extracted office bundles install from included wheels.
- VS Code shows the next setup step, copies the two paths Edge asks for, and says when
  Copilot has actually replied. Task options and recovery tools are grouped separately.
- Edge shows only the next pairing step, offers a single confirmation when only one
  Copilot tab is open, and avoids clearing a fresh selection when updating pairing.
- Pass dash-prefixed editor prompts as literal text and give clearer connection errors.

## 0.2.2 — 2026-11-09

- Isolate backend imports in Windows launchers and editor tasks; project modules and
  inherited Python paths cannot replace the backend before consent. Preserve alias
  arguments without a second batch `CALL` expansion.
- Fail `doctor` when Copilot chat, trusted executable Git or required project writes
  are unavailable. Verify writes using an owned temporary file; skip writes in read-only mode.
- Reject Windows reparse points on Python 3.11 as well as newer interpreters, closing
  an internal junction alias into excluded directories.
- Bound supported Python to 64-bit CPython 3.11–3.13, select a compatible installed
  version, use a Python 3.11-compatible pyee pin and require binary runtime wheels.
  Detect copied/broken virtual environments before package installation.
- Add an office-laptop setup and acceptance checklist with portable paths and explicit
  separation of local verification from live Microsoft account validation.

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
