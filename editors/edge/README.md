# PilotPatch existing Edge connection

This Manifest V3 extension connects the local Python harness to one existing Copilot
tab selected by the user. It does not create windows, tabs or profiles. It operates
visible public page controls, never cookies, Microsoft auth storage or hidden endpoints.

## One-time setup

1. Run `D:\MyProjects\PilotPatch\copilot.cmd connect`, or **Connect existing Edge**
   in the 0.2.1 VS Code panel.
2. In **your current Edge profile**, open `edge://extensions`, enable Developer mode
   and choose **Load unpacked**. Select the printed `edge-extension` folder.
3. Open the PilotPatch extension from Edge's Extensions menu. Select the printed
   `edge-pairing.json` file. It stays on this computer; no upload happens.
4. Choose your already-open Copilot tab and click **Connect this tab**.
5. Run **Sign in**, then **Test connection** in VS Code (CLI: `login`, `probe`).

Use the normal public chat at `https://copilot.com/chat`. Complete Microsoft sign-in
and MFA manually if necessary. Keep the selected tab open and clear/send any unsent
draft yourself before a PilotPatch task. After setup the extension reconnects when a
CLI task starts, usually within 30 seconds. The popup's Connect button wakes it sooner.
The ON badge means local transport connected; only a successful probe proves a model reply.
Pairing persists, but select the tab again after restarting Edge. Stop a running task
before selecting another tab; changing the selection invalidates the active connection.

After upgrading, rerun `connect`, then click **Reload** for this extension on
`edge://extensions`. The stable installation directory and pairing are reused.
If an old Login task is still active, stop it yourself before starting the new connector.

## Scope and protocol

- Permissions: storage, alarms, scripting; exact HTTPS Copilot hosts and IPv4 loopback.
  No cookies, history, all-sites, browser-debugger or native-process permissions.
- Selection enumerates Copilot tabs only. Packaged content code runs in the selected
  tab's isolated world. Every command rechecks its origin and pins its document.
- The background worker alone holds the local token. Storage access is restricted to
  trusted extension contexts; no page-origin message relay or arbitrary JS RPC exists.
- A CLI-owned HTTP server binds only `127.0.0.1:57423`, checks Host, exact extension
  Origin and mutual HMAC proofs using a private 256-bit key, limits size/time/concurrency, and closes
  on task completion. No permanent service or external network listener is installed.
- Protocol v2 uses a fresh challenge at POST `/hello` and encrypted JSON POST `/next`,
  `/commit` and `/result`. Legacy workers are rejected before receiving a prompt.
  A server instance has a fresh session ID; all requests have unique
  random nonces and HMAC proofs, and responses are authenticated before parsing.
  The pairing secret is never transmitted. AES-256-GCM encrypts both directions using
  a domain-separated per-session derived key, fresh 96-bit IVs, and direction/session/
  path/request-nonce authenticated data. A replacement listener cannot read pending
  Copilot answers. Response size is capped while streaming, before buffering.
  Identity includes a random extension-install client ID, session-only selection ID
  and selected tab ID; one identity owns a CLI run.
  Submission prepares the composer, rechecks pairing/selection, obtains a one-shot
  grant for the still-pending CLI request, then synchronously commits in the pinned
  document. Revocation while injecting/preparing prevents the click. Updating pairing
  clears the old selection. Orphaned v1 content listeners use a different channel.
  Only status, submit and response operations exist. IDs are unique; delivered commands
  are not redelivered, and lost results are not retried. Never include token in logs.
- Each submission has a fresh nonce. Only its following assistant message, with owned
  completion controls and stable content, can become an agent action. Reload/navigation,
  closed tabs, duplicate delivery and partial responses fail closed. Inspect Edge before
  resuming unknown outcomes; choose a fresh chat manually for resume.
  Generic Copy/code-copy buttons do not establish completion; the default requires
  Copy message. Prose outside JSON is preserved so examples/warnings fail strict parsing.
- **Disconnect this profile** removes extension-side pairing/selection. CLI `logout`
  removes the backend token. Neither operation logs out of Microsoft or changes tabs.

The loopback port can be changed by editing the private pairing file and reselecting
it in the popup. The token is local application authorization, not a Microsoft credential.
The OS user and installed extension code remain trusted. Do not sync or share pairing.

Development uses official [extension network requests](https://developer.chrome.com/docs/extensions/develop/concepts/network-requests),
[isolated script injection](https://developer.chrome.com/docs/extensions/reference/api/scripting)
and [Edge sideloading](https://learn.microsoft.com/en-us/microsoft-edge/extensions/getting-started/extension-sideloading).
Run `node --test tests/edge_connection.test.cjs` from the repository root, plus
`python -m pytest -q tests/test_edge_bridge.py tests/test_existing_edge.py`.
The real extension tests use a separate test-only Chromium profile with local HTML,
never the user's profile or a live Microsoft account. Development requires
`python -m playwright install chromium`; runtime existing-edge mode does not.
