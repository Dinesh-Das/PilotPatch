# Use the user's existing Edge profile

Requested behavior: select an already-open Copilot tab in the user's regular Edge
profile; never create a browser/profile or copy credentials as a fallback.

## Contract and boundaries

- Default `browser_connection: existing-edge`; managed Edge remains explicit opt-in.
- A Manifest V3 extension operates only the user-selected HTTPS Copilot tab.
- Temporary authenticated loopback broker, no permanent service or remote endpoint.
- The private pairing file contains a PilotPatch token, never Microsoft credentials.
- RPC allowlist: status, submit, response. No arbitrary code, URL or shell operations.
- One browser lease and selected tab per CLI run. Delivered commands are never replayed.
- Login detects public account controls. Probe alone verifies a real model response.
- Losing a submitted turn is an unknown outcome; no automatic retry or tab replacement.
- Closing a CLI run leaves the user's Edge browser, tabs and sign-in intact.

## Work

- [x] Regression and security tests for default selection and local broker.
- [x] Implement broker, pairing, provider and scoped browser extension.
- [x] Wire CLI and document one-time installation/pairing and explicit managed mode.
- [x] Test real DOM fixtures, run full Python/Node checks and package validation.
- [x] Commit on main and report live account validation separately.

Implementation committed as `d018ce8`. Final validation: 118 Python tests passed,
5 explicitly skipped; 13 Node checks passed. Ruff, installed-wheel validation,
wheel/sdist builds and the dependency audit passed. VS Code 0.2.0 is installed and
the extension/pairing files are prepared. User installation/tab selection and live
Copilot probe remain a separate account-bound step, not an offline test claim.

Live use of the user's existing account requires them to install/pair the extension.
Do not inspect or attach to their everyday browser during development.
