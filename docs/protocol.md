# Text tool protocol v1

Return exactly one JSON object per turn, optionally enclosed in a whole-response
JSON fence. A single rendered browser code block is extracted without its language/Copy bar.
Prefix/suffix prose outside plain/fenced messages, arrays, duplicate keys, non-finite numbers, unknown
fields/types/tools and oversized responses are rejected. Formatting retries are bounded.

```json
{"type":"tool_call","id":"read-1","tool":"read_file","arguments":{"path":"src/app.py"}}
```

IDs match `[A-Za-z0-9_-]{1,80}`. Each distinct intent needs a new ID. The same ID with
the same normalized tool/arguments replays its receipt; a changed payload stops the
task. Identical actions with distinct IDs are limited to three executions. Receipts
persist across resume. A pending interrupted action never automatically reexecutes.

```json
{"type":"tool_result","id":"read-1","tool":"read_file","success":true,"result":{"path":"src/app.py","content":"...","sha256":"...","truncated":false,"redacted":false}}
```

Failures use `success:false` and `error:{"code":"...","message":"..."}`. Denied tools,
unknown outcomes and `applied:false` do not prove a local change. Commands report
`executed`, `exit_code`, `timed_out`, `output`, `truncated`. Runner `success:true` does
not imply command success: a nonzero exit code still indicates a failing command/test.

| Tool | Strict arguments |
|---|---|
| `list_directory` | `path` (default `.`) |
| `read_file` | `path` |
| `read_file_range` | `path`, `start`, `end` (1-based inclusive, at most 501 lines) |
| `search_files` | `pattern` (glob, default `*`) |
| `search_content` | `query` (literal, case insensitive), optional `pattern` |
| `git_status` | empty object |
| `git_diff` | optional `path` |
| `write_file` | `path`, `content`, `expected_sha256` (required for existing files) |
| `replace_in_file` | `path`, exact unique nonempty `old_text`, `new_text` |
| `apply_patch` | `patch` (single-file unified diff) |
| `rename_file` | `path`, `destination`, `expected_sha256` |
| `delete_file` | `path`, `expected_sha256` |
| `run_tests` | `name` (operator-configured test name) |
| `run_command` | `argv` (array), `cwd` (default `.`) |

Paths are repository-relative and pass confinement/sensitive-path checks. Whole reads
are bounded UTF-8 text and return SHA256 of original bytes. Ranges use bounded scans
and do not supply whole-file hashes. Files containing redacted credential patterns
require manual editing. Exact replacement preserves BOM and unmodified newlines;
write_file writes UTF-8 content as supplied.

Patches start `--- a/path` and `+++ b/path` with identical paths and exact ordered
hunks/counts/positions. No binary/mode changes, renames, fuzzy context or multi-file
patches. Empty-base creation uses `@@ -0,0 +1,N @@`. Use explicit approved tools for
deletion/rename. Multi-file tasks use independently journaled calls.

```json
{"type":"final","summary":"Implemented validation.","files_changed":["src/app.py"],"tests":"unit command succeeded","remaining_issues":[]}
```

All final fields are required and bounded. Claimed files/tests remain Copilot's
narrative; the local report separately lists actual changes and executed checks.
The exact schemas are generated from `MESSAGE_ADAPTER.json_schema()` and
`tool_schemas()` in Python and included in the initial prompt. No model interprets JSON.
