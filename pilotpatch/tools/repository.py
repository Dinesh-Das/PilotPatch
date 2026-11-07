import difflib
import fnmatch
import hashlib
import os
import shutil
import subprocess
import time
from pathlib import Path

from pathspec import GitIgnoreSpec

from pilotpatch.config import Config
from pilotpatch.security.paths import EXCLUDED, PathGuard, SafetyError, sensitive
from pilotpatch.security.redaction import redact


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class Repository:
    def __init__(self, root: Path, config: Config):
        self.guard = PathGuard(root)
        self.root = self.guard.root
        self.config = config

    def _ignore_specs(self, directory: Path):
        specs = []
        for parent in [self.root, *reversed(directory.relative_to(self.root).parents), directory]:
            # Gather ancestors below root without interpreting a path outside it.
            if not parent.is_absolute():
                parent = self.root / parent
            ignore = parent / ".gitignore"
            if ignore.is_file() and not ignore.is_symlink() and ignore.stat().st_size < 64000:
                try:
                    specs.append(
                        (
                            parent,
                            GitIgnoreSpec.from_lines(
                                ignore.read_text(encoding="utf-8").splitlines()
                            ),
                        )
                    )
                except (OSError, UnicodeError):
                    continue
        return specs

    def files(self, pattern: str = "*", limit: int = 2000) -> list[str]:
        result = []
        visited = 0
        deadline = time.monotonic() + 10
        for directory, dirs, files in os.walk(self.root, followlinks=False):
            base = Path(directory)
            specs = self._ignore_specs(base)

            def allowed(name: str, is_dir: bool, base=base, specs=specs) -> bool:
                path = base / name
                relative = path.relative_to(self.root).as_posix()
                if name.lower() in EXCLUDED or sensitive(relative) or path.is_symlink():
                    return False
                try:
                    self.guard.resolve(relative, directory=is_dir)
                except SafetyError:
                    return False
                return not any(
                    spec.match_file(path.relative_to(parent).as_posix() + ("/" if is_dir else ""))
                    for parent, spec in specs
                )

            dirs[:] = sorted(d for d in dirs if allowed(d, True))
            for name in sorted(files):
                visited += 1
                if visited > 50000 or time.monotonic() > deadline:
                    return result
                relative = (base / name).relative_to(self.root).as_posix()
                if allowed(name, False) and (
                    fnmatch.fnmatchcase(relative, pattern) or Path(relative).match(pattern)
                ):
                    result.append(relative)
                    if len(result) >= limit:
                        return result
        return result

    def raw(self, name: str) -> bytes:
        path = self.guard.resolve(name)
        if not path.is_file():
            raise ValueError("File does not exist or is not a regular file")
        with path.open("rb") as stream:
            data = stream.read(self.config.max_file_bytes + 1)
        if len(data) > self.config.max_file_bytes:
            raise ValueError("File too large; use read_file_range")
        if b"\x00" in data:
            raise ValueError("Binary files are excluded")
        data.decode("utf-8-sig")
        return data

    def read(self, name: str) -> dict:
        data = self.raw(name)
        content = data.decode("utf-8-sig")
        safe = redact(content)
        return dict(
            path=name, content=safe, sha256=sha256(data), truncated=False, redacted=safe != content
        )

    def read_range(self, name: str, start: int, end: int) -> dict:
        if start < 1 or end < start or end - start > 500:
            raise ValueError("Request 1-based inclusive ranges of at most 501 lines")
        path = self.guard.resolve(name)
        lines = []
        total_bytes = 0
        # Bounded scanning even if a file contains extremely long lines.
        with path.open("rb") as stream:
            for number in range(1, min(end + 1, 100001)):
                line = stream.readline(self.config.max_file_bytes + 1)
                total_bytes += len(line)
                if (
                    len(line) > self.config.max_file_bytes
                    or total_bytes > 8000000
                    or b"\x00" in line
                ):
                    raise ValueError("Range exceeds scan/line limits")
                if not line:
                    break
                if number >= start:
                    lines.append(line.decode("utf-8-sig"))
                if sum(len(s) for s in lines) > self.config.max_file_bytes:
                    raise ValueError("Range too large; request fewer lines")
        return dict(
            path=name,
            start=start,
            end=end,
            content=redact("".join(lines)),
            truncated=True,
            note="Range only; read_file supplies whole-file SHA256",
        )

    def listing(self, name: str = ".") -> dict:
        directory = self.guard.resolve(name, directory=True)
        prefix = "" if name == "." else directory.relative_to(self.root).as_posix() + "/"
        entries = set()
        for file in self.files():
            if file.startswith(prefix):
                suffix = file[len(prefix) :]
                first, separator, _ = suffix.partition("/")
                entries.add(first + ("/" if separator else ""))
        return dict(path=name, entries=sorted(entries)[:500], truncated=len(entries) > 500)

    def search(self, query: str, pattern: str = "*") -> dict:
        if not query or len(query) > 500:
            raise ValueError("Search query must contain 1 to 500 characters")
        matches = []
        for file in self.files(pattern):
            try:
                content = self.read(file)["content"]
            except (OSError, ValueError, UnicodeError):
                continue
            for line, text in enumerate(content.splitlines(), 1):
                if query.casefold() in text.casefold():
                    matches.append(dict(path=file, line=line, text=text[:1000]))
                    if len(matches) >= 100:
                        return dict(matches=matches, truncated=True)
        return dict(matches=matches, truncated=False)

    def _git(self, arguments: list[str]) -> str:
        executable = shutil.which("git")
        if not executable or Path(executable).resolve().is_relative_to(self.root):
            raise ValueError("Git must be installed outside the untrusted target repository")
        result = subprocess.run(
            [executable, "--no-optional-locks", "-c", "core.fsmonitor=false", *arguments],
            cwd=self.root,
            capture_output=True,
            timeout=15,
        )
        if result.returncode:
            raise ValueError("Git operation failed; ensure the project is a Git repository")
        return result.stdout[: self.config.max_file_bytes + 1].decode("utf-8", errors="replace")

    def git_status(self) -> dict:
        output = self._git(["status", "--porcelain=v1", "-unormal"])
        # Status includes names only; content is never obtained through an unfiltered git diff.
        return dict(
            output=redact(output)[: self.config.max_output_bytes],
            truncated=len(output.encode()) >= self.config.max_output_bytes,
        )

    def git_diff(self, name: str | None = None) -> dict:
        names = [name] if name else self.files(limit=1000)
        diffs = []
        size = 0
        for relative in names:
            self.guard.resolve(relative)
            try:
                current = self.read(relative)["content"]
                original = self._git(["show", f"HEAD:./{relative}"])
                if len(original.encode("utf-8")) > self.config.max_file_bytes:
                    continue
            except (ValueError, OSError, UnicodeError):
                continue
            diff = "".join(
                difflib.unified_diff(
                    original.splitlines(keepends=True),
                    current.splitlines(keepends=True),
                    fromfile=f"a/{relative}",
                    tofile=f"b/{relative}",
                )
            )
            size += len(diff.encode())
            diffs.append(redact(diff))
            if size >= self.config.max_output_bytes:
                break
        return dict(
            output="".join(diffs)[: self.config.max_output_bytes],
            truncated=size >= self.config.max_output_bytes,
            note="Filtered text diff against HEAD; untracked/deleted files use local session diff",
        )
