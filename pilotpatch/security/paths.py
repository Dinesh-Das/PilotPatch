"""Portable repository confinement, including Windows path aliases."""

import re
from pathlib import Path, PureWindowsPath

EXCLUDED = {".git", "node_modules", "dist", "build", ".venv", "venv", "target", "coverage",
            ".pytest_cache", "__pycache__", ".mypy_cache", ".ruff_cache", ".gradle", ".next",
            ".idea", ".pilotpatch", ".cache", "bin", "obj"}
PRIVATE_DIRS = {".ssh", ".aws", ".azure", ".config", ".vscode"}
SENSITIVE_NAMES = {"id_rsa", "id_ed25519", "credentials", "credentials.json", "secrets.json",
                   ".npmrc", ".pypirc", ".netrc", "nuget.config", "web.config"}
RESERVED = re.compile(r"^(con|prn|aux|nul|com[0-9]|lpt[0-9])(?:\.|$)", re.I)


class SafetyError(ValueError):
    pass


def sensitive(path: str) -> bool:
    parts = path.replace("\\", "/").lower().split("/")
    return any(p in PRIVATE_DIRS or p in SENSITIVE_NAMES or p.startswith(".env")
               or p.endswith((".pem", ".key", ".pfx", ".p12", ".keystore", ".kdbx"))
               or "secret" in p or p.startswith("appsettings.") for p in parts)


class PathGuard:
    def __init__(self, root: Path):
        self.root = root.resolve(strict=True)
        if not self.root.is_dir():
            raise SafetyError("Project must be a directory")

    def resolve(self, name: str, *, directory: bool = False) -> Path:
        if not name or "\x00" in name or PureWindowsPath(name).drive or name.startswith(("/", "\\")):
            raise SafetyError("Use a relative repository path")
        parts = name.replace("\\", "/").split("/")
        if name == "." and directory:
            return self.root
        for part in parts:
            if (part in {"", ".", ".."} or ":" in part or part.endswith((".", " "))
                    or RESERVED.match(part) or any(ord(c) < 32 for c in part)):
                raise SafetyError("Unsafe or ambiguous path component")
            if part.lower() in EXCLUDED:
                raise SafetyError("Excluded repository directory")
        if sensitive(name):
            raise SafetyError("Sensitive file excluded; inspect it manually outside the agent")
        lexical = self.root.joinpath(*parts)
        # Reject all reparse points/symlinks, even ones currently inside the root. This
        # also keeps backup/rename operations from changing a different lexical file.
        cursor = lexical
        while cursor != self.root:
            if cursor.is_symlink() or (hasattr(cursor, "is_junction") and cursor.is_junction()):
                raise SafetyError("Symlinks and junctions are excluded")
            cursor = cursor.parent
        resolved = lexical.resolve()
        if not resolved.is_relative_to(self.root) or resolved == self.root:
            raise SafetyError("Path escapes the repository")
        return resolved
