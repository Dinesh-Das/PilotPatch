import os
import uuid
from pathlib import Path

from pilotpatch.security.permissions import Permissions
from pilotpatch.security.redaction import redact
from pilotpatch.security.storage import atomic_bytes, atomic_json
from pilotpatch.tools.patch import apply_unified
from pilotpatch.tools.repository import Repository, sha256
from pilotpatch.tools.review import Change, ReviewRepository, text_diff


class FileTools:
    def __init__(
        self,
        repo: Repository,
        state_dir: Path,
        permissions: Permissions,
        *,
        dry_run: bool = False,
        preview=lambda _: None,
    ):
        self.repo = repo
        self.state_dir = state_dir
        self.permissions = permissions
        self.dry_run = dry_run
        self.preview = preview

    def _backup(self, name: str, before: bytes | None, after: bytes | None):
        record = self.state_dir / "backups" / uuid.uuid4().hex
        record.mkdir(parents=True)
        if before is not None:
            atomic_bytes(record / "original.bak", before)
        atomic_json(
            record / "manifest.json",
            dict(
                path=name,
                before_sha256=sha256(before) if before is not None else None,
                after_sha256=sha256(after) if after is not None else None,
            ),
        )

    def _change(
        self, name: str, before: bytes | None, after: bytes | None, *, destructive: bool = False
    ) -> dict:
        self.repo.guard.resolve(name)
        if before is not None:
            text = before.decode("utf-8-sig")
            if redact(text) != text:
                raise ValueError("File contains redacted credential patterns; edit it manually")
        if after is not None and len(after) > self.repo.config.max_file_bytes:
            raise ValueError("Proposed file exceeds the file size limit")
        diff = text_diff(name, before, after)
        if isinstance(self.repo, ReviewRepository):
            self.repo.stage(name, before, after)
            return dict(
                path=name,
                applied=False,
                staged=True,
                sha256=sha256(after) if after is not None else None,
            )
        self.preview(diff)
        if self.dry_run:
            return dict(path=name, diff=diff, applied=False, dry_run=True)
        self.permissions.require(f"Apply change to {name}?", destructive=destructive)
        self.apply_change(Change(name, before, after))
        return dict(
            path=name,
            diff=diff,
            applied=True,
            sha256=sha256(after) if after is not None else None,
        )

    def apply_change(self, change: Change):
        # Re-resolve and re-read after approval to reject edits made while reviewing.
        name, before, after = change.name, change.before, change.after
        path = self.repo.guard.resolve(name)
        if self.repo.existing(name) != before:
            raise ValueError("File changed while awaiting approval; re-read before editing")
        self._backup(name, before, after)
        if after is None:
            path.unlink()
        else:
            previous_mode = path.stat().st_mode if path.exists() else None
            atomic_bytes(path, after, exclusive=before is None)
            if previous_mode is not None:
                os.chmod(path, previous_mode)
            if path.read_bytes() != after:
                raise OSError("Write verification failed; inspect session backups")

    def write(self, name: str, content: str, expected_sha256: str | None) -> dict:
        before = self.repo.existing(name)
        if before is not None and (expected_sha256 is None or sha256(before) != expected_sha256):
            raise ValueError("Existing file requires the current SHA256 from read_file")
        if before is None and expected_sha256 is not None:
            raise ValueError("Expected an existing file, but it is missing")
        return self._change(name, before, content.encode("utf-8"))

    def replace(self, name: str, old_text: str, new_text: str) -> dict:
        before = self.repo.raw(name)
        text = before.decode("utf-8-sig")
        if not old_text or text.count(old_text) != 1:
            raise ValueError("old_text must match exactly once; re-read the file")
        after = text.replace(old_text, new_text, 1).encode("utf-8")
        if before.startswith(b"\xef\xbb\xbf"):
            after = b"\xef\xbb\xbf" + after
        return self._change(name, before, after)

    def patch(self, patch: str) -> dict:
        first = patch.splitlines()[0] if patch else ""
        if not first.startswith("--- a/"):
            raise ValueError("Patch must start with --- a/path")
        name = first[6:]
        before = self.repo.existing(name)
        _, after = apply_unified(patch, (before or b"").decode("utf-8-sig"))
        data = after.encode("utf-8")
        if before and before.startswith(b"\xef\xbb\xbf"):
            data = b"\xef\xbb\xbf" + data
        return self._change(name, before, data)

    def delete(self, name: str, expected_sha256: str) -> dict:
        before = self.repo.raw(name)
        if sha256(before) != expected_sha256:
            raise ValueError("File hash mismatch")
        return self._change(name, before, None, destructive=True)

    def rename(self, name: str, destination: str, expected_sha256: str) -> dict:
        source = self.repo.guard.resolve(name)
        target = self.repo.guard.resolve(destination)
        before = self.repo.raw(name)
        if (
            self.repo.existing(destination) is not None
            or source == target
            or sha256(before) != expected_sha256
        ):
            raise ValueError("Rename destination exists or source hash mismatch")
        if isinstance(self.repo, ReviewRepository):
            # Stage the destination first: a failed target validation must leave the source intact.
            text = before.decode("utf-8-sig")
            if redact(text) != text:
                raise ValueError("File contains redacted credential patterns; rename it manually")
            self.repo.stage(destination, None, before)
            self.repo.stage(name, before, None)
            self.repo.link_rename(source, target)
            return dict(path=name, destination=destination, applied=False, staged=True)
        self.preview(f"Rename {name} -> {destination}")
        if self.dry_run:
            return dict(path=name, destination=destination, applied=False, dry_run=True)
        self.permissions.require(f"Rename {name} to {destination}?", destructive=True)
        source = self.repo.guard.resolve(name)
        target = self.repo.guard.resolve(destination)
        if target.exists() or self.repo.raw(name) != before:
            raise ValueError("Files changed during approval")
        self._backup(name, before, None)
        self._backup(destination, None, before)
        target.parent.mkdir(parents=True, exist_ok=True)
        # Windows rename fails if destination appeared; no silent replacement.
        if os.name == "nt":
            source.rename(target)
        else:
            os.link(source, target)
            source.unlink()
        return dict(path=name, destination=destination, applied=True)
