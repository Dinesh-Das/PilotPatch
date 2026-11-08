import json
import re
import shutil
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

from filelock import FileLock, Timeout

from pilotpatch.security.storage import atomic_json


class SessionStore:
    def __init__(self, home: Path):
        self.home = home
        self.sessions = home / "sessions"
        self.sessions.mkdir(parents=True, exist_ok=True)
        self.locks = home / "session-locks"
        self.locks.mkdir(parents=True, exist_ok=True)

    def directory(self, session_id: str) -> Path:
        if not re.fullmatch(r"[a-f0-9]{32}", session_id):
            raise ValueError("Session ID must be the 32-character ID from history")
        directory = self.sessions / session_id
        if directory.is_symlink() or not directory.resolve().is_relative_to(
            self.sessions.resolve()
        ):
            raise ValueError("Unsafe session directory")
        return directory

    def create(self, project: Path, task: str, dry_run: bool = False) -> dict:
        state = dict(
            version=1,
            id=uuid.uuid4().hex,
            project=str(project.resolve()),
            task=task,
            created_at=datetime.now(UTC).isoformat(),
            updated_at=datetime.now(UTC).isoformat(),
            status="created",
            steps=0,
            messages=[],
            receipts={},
            pending=None,
            changes=[],
            checks=[],
            final=None,
            dry_run=dry_run,
            conversation_url=None,
        )
        self.save(state)
        return state

    def task_lock(self, session_id: str) -> FileLock:
        self.directory(session_id)  # Validate ownership path before constructing a lease.
        # Keep the lease outside the directory so Windows can prune it while locked.
        return FileLock(self.locks / f"{session_id}.lock", timeout=0)

    def save(self, state: dict):
        state["updated_at"] = datetime.now(UTC).isoformat()
        atomic_json(self.directory(state["id"]) / "state.json", state)

    def load(self, session_id: str) -> dict:
        path = self.directory(session_id) / "state.json"
        if path.stat().st_size > 20000000:
            raise ValueError("Session state is too large")
        state = json.loads(path.read_text(encoding="utf-8"))
        if state.get("id") != session_id or state.get("version") != 1:
            raise ValueError("Unsupported or mismatched session state")
        return state

    def history(self) -> list[dict]:
        entries = []
        for path in sorted(
            self.sessions.glob("*/state.json"), key=lambda p: p.stat().st_mtime, reverse=True
        )[:100]:
            try:
                state = self.load(path.parent.name)
                entries.append({k: state[k] for k in ("id", "status", "project", "updated_at")})
            except (ValueError, OSError, KeyError):
                continue
        return entries

    def audit(self, state: dict, event: str, **metadata):
        # Metadata only: never store prompt text, cookies, auth tokens or tool content here.
        line = dict(time=datetime.now(UTC).isoformat(), event=event, **metadata)
        with (self.directory(state["id"]) / "audit.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(line) + "\n")

    def prune(self, retention_days: int):
        cutoff = time.time() - retention_days * 86400
        # History is a 100-entry UI view; retention must inspect older sessions too.
        for path in self.sessions.glob("*/state.json"):
            try:
                session_id = path.parent.name
                with self.task_lock(session_id):
                    state = self.load(session_id)
                    directory = self.directory(session_id)
                    if (
                        state["status"] != "completed"
                        or (directory / "state.json").stat().st_mtime >= cutoff
                    ):
                        continue
                    # Respect an active pre-upgrade task too. Merely finding its old
                    # lock file is insufficient: a crashed process can leave it behind.
                    if (directory / "task.lock").exists():
                        with FileLock(directory / "task.lock", timeout=0):
                            pass
                    shutil.rmtree(directory)
            except (OSError, ValueError, KeyError, Timeout):
                continue
