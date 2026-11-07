# PilotPatch editor panel

## Specification and design contract

Add an installable desktop VS Code extension using stable extension APIs so compatible
forks can install the same VSIX. A dedicated PilotPatch activity-bar view accepts a
task and selects the local workspace. It invokes the existing Python harness with
argument vectors through VS Code ProcessExecution tasks. Microsoft Copilot Web remains
the sole runtime reasoning provider; existing data-sharing/edit/command approvals stay
interactive in the integrated terminal. No API server or editor AI provider is added.

The view uses VS Code theme tokens, native fonts, compact spacing, a clearly labelled
multiline task field, one primary Run task action and honest execution states. Support
empty workspace, missing backend, busy, stopped, error and completed-process states.
Process exit 0 is labelled finished, never proof of live model/test success. Keyboard
submission is Ctrl/Cmd+Enter; source/diff approval remains in the terminal. No external
fonts/assets/network access are permitted in the webview. Render untrusted text with
textContent, use restrictive CSP, validate all messages and require trusted local folders.

## Ordered work

- [x] Define/test strict panel requests and shell-free CLI argument construction.
- [x] Add native task controller, workspace selection and machine-scoped Python setting.
- [x] Build theme-aware prompt view with actual lifecycle status and stop action.
- [x] Verify webview in Edge, real VS Code and Cursor hosts, and package VSIX.
- [x] Install VSIX in VS Code; document visible backend selection and fork installation.
- [x] Commit reviewed changes on main and update the source archive.

## Verification

Node built-in tests exercise validation, argument preservation, trust/duplicate-launch
rejection and task lifecycle. Real Edge verifies rendering/keyboard/messages. An isolated
VS Code extension host verifies registration, selected workspace and safe diagnostic
task execution; it sends no repository source to Microsoft. Existing Python tests remain
the backend regression checks. Account-bound Copilot acceptance remains outstanding.
