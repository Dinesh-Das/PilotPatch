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
from pilotpatch.security.redaction import redact, redact_private_key_line


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class Repository:
    def __init__(self, root: Path, config: Config):
        self.guard = PathGuard(root)
        self.root = self.guard.root
        self.config = config

    def _ignore_specs(self, directory: Path, cache: dict[Path, GitIgnoreSpec | None]):
        specs = []
        ancestors = reversed(directory.relative_to(self.root).parents)
        for parent in [*(self.root / ancestor for ancestor in ancestors), directory]:
            if parent not in cache:
                ignore = parent / ".gitignore"
                cache[parent] = None
                try:
                    if (
                        not ignore.is_symlink()
                        and ignore.is_file()
                        and ignore.stat().st_size < 64000
                    ):
                        cache[parent] = GitIgnoreSpec.from_lines(
                            ignore.read_text(encoding="utf-8").splitlines()
                        )
                except (OSError, ValueError):
                    pass
            if cache[parent] is not None:
                specs.append((parent, cache[parent]))
        return specs

    def files(self, pattern: str = "*", limit: int = 2000) -> list[str]:
        return self.scan_files(pattern, limit)[0]

    def scan_files(self, pattern: str = "*", limit: int = 2000) -> tuple[list[str], bool]:
        result = []
        visited = 0
        deadline = time.monotonic() + 10
        limited = False
        ignore_cache: dict[Path, GitIgnoreSpec | None] = {}

        def unreadable(_):
            nonlocal limited
            limited = True

        for directory, dirs, files in os.walk(self.root, followlinks=False, onerror=unreadable):
            if time.monotonic() > deadline:
                return result, True
            base = Path(directory)
            specs = self._ignore_specs(base, ignore_cache)

            def allowed(name: str, is_dir: bool, base=base, specs=specs) -> bool:
                path = base / name
                relative = path.relative_to(self.root).as_posix()
                if name.lower() in EXCLUDED or sensitive(relative) or path.is_symlink():
                    return False
                try:
                    self.guard.resolve(relative, directory=is_dir)
                except SafetyError:
                    return False
                for parent, spec in reversed(specs):
                    decision = spec.check_file(
                        path.relative_to(parent).as_posix() + ("/" if is_dir else "")
                    ).include
                    if decision is not None:
                        return not decision
                return True

            dirs[:] = sorted(d for d in dirs if allowed(d, True))
            for name in sorted(files):
                visited += 1
                if visited > 50000 or time.monotonic() > deadline:
                    return result, True
                relative = (base / name).relative_to(self.root).as_posix()
                if (
                    fnmatch.fnmatchcase(relative, pattern) or Path(relative).match(pattern)
                ) and allowed(name, False):
                    if len(result) >= limit:
                        return result, True
                    result.append(relative)
        return result, limited

    def raw(self, name: str) -> bytes:
        path = self.guard.resolve(name)
        if not path.is_file():
            raise ValueError("File does not exist or is not a regular file")
        with path.open("rb") as stream:
            data = stream.read(self.config.max_file_bytes + 1)
        return self.validate_text(data)

    def validate_text(self, data: bytes) -> bytes:
        if len(data) > self.config.max_file_bytes:
            raise ValueError("File too large; use read_file_range")
        if b"\x00" in data:
            raise ValueError("Binary files are excluded")
        data.decode("utf-8-sig")
        return data

    def existing(self, name: str) -> bytes | None:
        return self.raw(name) if self.guard.resolve(name).exists() else None

    def open_text_bytes(self, name: str):
        return self.guard.resolve(name).open("rb")

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
        lines = []
        total_bytes = 0
        range_bytes = 0
        inside_key = False
        # Bounded scanning even if a file contains extremely long lines.
        with self.open_text_bytes(name) as stream:
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
                safe_line, inside_key = redact_private_key_line(line, inside_key)
                if number >= start:
                    range_bytes += len(line)
                    if range_bytes > self.config.max_file_bytes:
                        raise ValueError("Range too large; request fewer lines")
                    lines.append(safe_line.decode("utf-8-sig"))
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

    def _git_bytes(self, arguments: list[str], *, input_data: bytes | None = None) -> bytes:
        executable = shutil.which("git")
        if not executable or Path(executable).resolve().is_relative_to(self.root):
            raise ValueError("Git must be installed outside the untrusted target repository")
        result = subprocess.run(
            [
                executable,
                "--no-optional-locks",
                "--no-replace-objects",
                "-c",
                "core.fsmonitor=false",
                *arguments,
            ],
            cwd=self.root,
            capture_output=True,
            input=input_data,
            timeout=15,
        )
        if result.returncode:
            raise ValueError("Git operation failed; ensure the project is a Git repository")
        return result.stdout

    def _git(self, arguments: list[str]) -> str:
        return self._git_bytes(arguments)[: self.config.max_file_bytes + 1].decode(
            "utf-8", errors="replace"
        )

    def git_status(self) -> dict:
        output = self._git(["status", "--porcelain=v1", "-unormal"])
        # Status includes names only; content is never obtained through an unfiltered git diff.
        return dict(
            output=redact(output)[: self.config.max_output_bytes],
            truncated=len(output.encode()) >= self.config.max_output_bytes,
        )

    def git_diff(self, name: str | None = None) -> dict:
        if name:
            names = [self.guard.resolve(name).relative_to(self.root).as_posix()]
            truncated = False
        else:
            names, truncated = self.scan_files(limit=1000)
        output = bytearray()
        revisions = "".join(f"HEAD:./{relative}\n" for relative in names).encode()
        try:
            metadata = (
                self._git_bytes(
                    ["cat-file", "--batch-check", "--buffer"], input_data=revisions
                ).splitlines()
                if names
                else []
            )
        except (ValueError, OSError, subprocess.TimeoutExpired):
            metadata = []
        for relative, entry in zip(names, metadata, strict=False):
            fields = entry.split()
            if len(fields) != 3 or fields[1] != b"blob" or not fields[2].isdigit():
                continue
            oid, _, size = fields
            if len(oid) not in {40, 64} or any(c not in b"0123456789abcdef" for c in oid):
                continue
            if int(size) > self.config.max_file_bytes:
                continue
            try:
                data = self.raw(relative)
                algorithm = "sha1" if len(oid) == 40 else "sha256"
                digest = hashlib.new(algorithm, usedforsecurity=False)
                digest.update(f"blob {len(data)}\0".encode())
                digest.update(data)
                if digest.hexdigest().encode() == oid:
                    continue
                original = self.validate_text(self._git_bytes(["cat-file", "blob", oid.decode()]))
            except (ValueError, OSError, subprocess.TimeoutExpired):
                continue
            # Redact both complete files before diffing so removed private key
            # fragments cannot appear without their delimiters.
            diff = "".join(
                difflib.unified_diff(
                    redact(original.decode("utf-8-sig")).splitlines(keepends=True),
                    redact(data.decode("utf-8-sig")).splitlines(keepends=True),
                    fromfile=f"a/{relative}",
                    tofile=f"b/{relative}",
                )
            )
            safe = redact(diff).encode()
            remaining = self.config.max_output_bytes - len(output)
            output.extend(safe[:remaining])
            if len(safe) > remaining:
                truncated = True
                break
        return dict(
            output=output.decode("utf-8", errors="ignore"),
            truncated=truncated,
            note="Filtered text diff against HEAD; untracked/deleted files use local session diff",
        )
