"""Strict single-file unified diffs; no fuzzy matching, commands, binary or mode changes."""

import re

_HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(?:.*)\r?\n?$")


def apply_unified(patch: str, original: str) -> tuple[str, str]:
    # JSON/browser transport commonly uses LF for a patch even when the source uses
    # CRLF. Preserve homogeneous Windows newlines without fuzzy content matching.
    if "\r\n" in original and "\n" not in original.replace("\r\n", ""):
        patch = patch.replace("\r\n", "\n").replace("\n", "\r\n")
    lines = patch.splitlines(keepends=True)
    if len(lines) < 3 or not lines[0].startswith("--- a/") or not lines[1].startswith("+++ b/"):
        raise ValueError("Use a single-file unified diff starting --- a/path and +++ b/path")
    old_name = lines[0][6:].rstrip("\r\n")
    new_name = lines[1][6:].rstrip("\r\n")
    if old_name != new_name or not old_name:
        raise ValueError(
            "Patch renames/deletions unsupported; use explicit rename_file/delete_file"
        )
    source = original.splitlines(keepends=True)
    result = []
    cursor = 0
    index = 2
    while index < len(lines):
        match = _HUNK.match(lines[index])
        if not match:
            raise ValueError("Invalid patch hunk header")
        old_start, old_count, new_start, new_count = [
            int(v) if v is not None else 1 for v in match.groups()
        ]
        target = old_start - 1 if old_count else old_start
        if target < cursor or target > len(source):
            raise ValueError("Overlapping or out-of-range patch hunks")
        result.extend(source[cursor:target])
        cursor = target
        if (new_start - 1 if new_count else new_start) != len(result):
            raise ValueError("New hunk position does not match output")
        index += 1
        removed = added = 0
        while index < len(lines) and not lines[index].startswith("@@ "):
            line = lines[index]
            if not line or line[0] not in " +-":
                raise ValueError("Unsupported patch line")
            kind, content = line[0], line[1:]
            if index + 1 < len(lines) and lines[index + 1].startswith(
                "\\ No newline at end of file"
            ):
                content = content.rstrip("\r\n")
                index += 1
            if kind in " -":
                if cursor >= len(source) or source[cursor] != content:
                    raise ValueError("Patch context mismatch; re-read the current file")
                cursor += 1
                removed += 1
            if kind in " +":
                result.append(content)
                added += 1
            index += 1
        if removed != old_count or added != new_count:
            raise ValueError("Hunk line counts do not match")
    result.extend(source[cursor:])
    return old_name, "".join(result)
