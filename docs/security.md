# Security and recovery

Trust boundaries: the operator authorizes a local repository and a Microsoft data
destination. Repository text, Copilot JSON, browser content and command output are
untrusted. Python validates tool names/arguments, paths, edit preconditions and
permissions independently of prompt instructions.

- Source sharing requires per-invocation confirmation or explicit `--share-code`.
- Configuration comes only from user state or an explicit `--config`; repository
  YAML cannot silently authorize commands.
- Paths are relative to one project. Absolute/drive/UNC/traversal/alternate-stream/
  reserved Windows paths, symlinks and junctions are rejected. Sensitive file names
  and dependency/build directories are excluded. Redaction is a best-effort additional
  layer, not a guarantee of detecting every confidential value.
- Read-only rejects mutations and processes; approve asks for each edit; auto-edit
  authorizes guarded ordinary edits. Delete/rename always require confirmation.
- Commands use argument vectors without a shell. Windows batch launchers are routed
  through a tightly restricted cmd invocation. Command execution, including tests,
  can run arbitrary repository code with the operator's user permissions. This is
  an approval boundary, not an OS sandbox. Approve only trusted repositories/commands.
- Exact argv preauthorization is scoped to operator configuration, never a command
  prefix. Install/network/system operations have no automatic permission.
- Editing compares raw file hashes or exact unique old text, shows a diff, rechecks
  after approval, saves an original and uses atomic replacement. Writes preserve
  existing permissions; exact replacement preserves a UTF-8 BOM. No Git reset/clean,
  automatic commit, or removal of unrelated user work occurs in target repositories.
- A patch is one file, exact hunks, no fuzzy matching. Multi-file changes are separate
  calls; interruption can leave earlier calls applied, explicitly visible in state/diff.
- Browser/profile/task locks prevent concurrent writers. A pending local action is
  saved before execution. Unknown outcomes never replay automatically on resume.
- The browser accepts a response only after the nonce-bound user turn, with completion
  evidence owned by that response, no generation/busy signal and stable content.
  Timeout, authentication failure, UI ambiguity and oversized output stop the loop.
  There is no retry of a potentially accepted browser submission.

State defaults to `%LOCALAPPDATA%\PilotPatch`. The directory receives user-only
inheritable Windows ACLs (mode 0700 on Unix). Edge's browser storage holds credentials;
PilotPatch never reads or exports passwords/cookies. The OS user and local administrator
remain trusted. Do not sync this directory or place it inside a target repository.
The state JSON contains task text, redacted recent context, tool receipts and proposed
diffs; `.bak` files hold original source, including any original sensitive material.
Protect backups as confidential source. Audit JSONL stores event metadata only.
No telemetry is implemented. Completed session retention defaults to 30 days and is
enforced on subsequent history/run/diff/resume commands. Active/interrupted tasks are
retained to allow recovery. Browser state persists until `logout`.

For recovery: `history`, then `diff SESSION_ID`, inspect `audit.jsonl` and current files.
Backups are under `sessions/SESSION_ID/backups/RECORD/original.bak`; the adjacent
manifest records before/after SHA256 and the relative path. Restore manually after
review; never copy an original over later user edits without comparing it. A newly
created file has a manifest and no original; its recovery is a manually reviewed removal.
If an action was interrupted, reconcile the file/command outcome first, then use
`resume SESSION_ID --resolve-pending skip`. The next prompt reports an unknown outcome.
Do not resume while an independently started command still runs.

Same-user malicious processes can race filesystem checks or tamper with state. This
implementation is not a defense against a hostile local OS user. There is no claim
of cross-file transactions, encrypted source backups, or guaranteed secret detection.
