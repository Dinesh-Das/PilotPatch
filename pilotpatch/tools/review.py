"""In-memory file drafts with a bounded, reviewable diff against the original bytes."""

import difflib
import fnmatch
import io
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from pilotpatch.security.redaction import redact
from pilotpatch.tools.repository import Repository


@dataclass(frozen=True)
class Change:
    name: str
    before: bytes | None
    after: bytes | None

    def diff(self) -> str:
        return text_diff(self.name, self.before, self.after)

    def review_entry(self, index: int, limit: int, group: int | None) -> dict:
        diff = self.diff()
        lines = diff.splitlines()
        edits = lines[2:] if diff.startswith("--- ") else []
        return dict(
            id=index,
            path=self.name,
            kind="added"
            if self.before is None
            else "deleted"
            if self.after is None
            else "modified",
            added=sum(line.startswith("+") for line in edits),
            removed=sum(line.startswith("-") for line in edits),
            diff=diff if len(diff) <= limit else diff[:limit].rsplit("\n", 1)[0],
            clipped=len(diff) > limit,
            group=group,
        )


def text_diff(name: str, before: bytes | None, after: bytes | None) -> str:
    lines = list(
        difflib.unified_diff(
            (before or b"").decode("utf-8-sig").splitlines(keepends=True),
            (after or b"").decode("utf-8-sig").splitlines(keepends=True),
            fromfile=f"a/{name}" if before is not None else "/dev/null",
            tofile=f"b/{name}" if after is not None else "/dev/null",
        )
    )
    if not lines and before != after:
        description = (
            "Create empty file"
            if before is None
            else ("Delete empty file" if after is None else "Change UTF-8 byte order mark")
        )
        return redact(f"{description}: {name}\n")
    return redact(
        "".join(
            line if line.endswith(("\n", "\r")) else line + "\n\\ No newline at end of file\n"
            for line in lines
        )
    )


def review_entries(changes: list[Change], groups: dict[int, int]) -> list[dict]:
    limit = min(12000, 200000 // len(changes))
    return [
        change.review_entry(index, limit, groups.get(index)) for index, change in enumerate(changes)
    ]


class ReviewRepository(Repository):
    def __init__(self, original: Repository):
        super().__init__(original.root, original.config)
        self.original = original
        self.changes: dict[Path, Change] = {}
        self.renames: dict[Path, set[Path]] = {}

    def link_rename(self, source: Path, target: Path):
        paths = self.renames.get(source, {source}) | self.renames.get(target, {target})
        for path in paths:
            self.renames[path] = paths

    def review_groups(self, changes: list[Change]) -> dict[int, int]:
        indices = {self.root / item.name: index for index, item in enumerate(changes)}
        groups = {}
        for path, index in indices.items():
            linked = [indices[item] for item in self.renames.get(path, ()) if item in indices]
            if len(linked) > 1:
                groups[index] = min(linked)
        return groups

    def stage(self, name: str, before: bytes | None, after: bytes | None):
        target = self.guard.resolve(name)
        if after is not None:
            self.validate_text(after)
            if any(
                change.after is not None
                and path != target
                and (path in target.parents or target in path.parents)
                for path, change in self.changes.items()
            ):
                raise ValueError("Proposed file conflicts with another proposed path")
        prior = self.changes.get(target)
        original = prior.before if prior is not None else before
        if original == after:
            self.changes.pop(target, None)
        else:
            self.changes[target] = Change(target.relative_to(self.root).as_posix(), original, after)

    def existing(self, name: str) -> bytes | None:
        change = self.changes.get(self.guard.resolve(name))
        return change.after if change else self.original.existing(name)

    def raw(self, name: str) -> bytes:
        change = self.changes.get(self.guard.resolve(name))
        if change:
            if change.after is None:
                raise ValueError("File is deleted in the proposed changes")
            return change.after
        return self.original.raw(name)

    def open_text_bytes(self, name: str):
        if self.guard.resolve(name) in self.changes:
            return io.BytesIO(self.raw(name))
        return super().open_text_bytes(name)

    def files(self, pattern: str = "*", limit: int = 2000) -> list[str]:
        result = [
            name
            for name in super().files(pattern, limit)
            if (change := self.changes.get(self.root / name)) is None or change.after is not None
        ]
        known = {self.root / name for name in result}
        for path, change in self.changes.items():
            if (
                change.after is not None
                and path not in known
                and (
                    fnmatch.fnmatchcase(change.name, pattern)
                    or PurePosixPath(change.name).match(pattern)
                )
            ):
                result.append(change.name)
        return result[:limit]

    def git_diff(self, name: str | None = None) -> dict:
        if not self.changes:
            return super().git_diff(name)
        paths = [self.guard.resolve(name)] if name else list(self.changes)
        output = "".join(self.changes[path].diff() for path in paths if path in self.changes)
        cap = self.config.max_output_bytes
        return dict(output=output[:cap], truncated=len(output) > cap, note="Proposed file edits")
