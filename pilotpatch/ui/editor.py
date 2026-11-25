"""Local JSON-lines transport for the VS Code extension. The backend owns approvals."""

import asyncio
import json
import os
import sys
from queue import Queue
from threading import Thread
from uuid import uuid4

from pydantic import Field

from pilotpatch.agent.protocol import StrictModel
from pilotpatch.security.redaction import redact_value
from pilotpatch.tools.review import Change, review_entries


class Exchange(StrictModel):
    user: str = Field(max_length=16000)
    assistant: str = Field(max_length=20000)
    changed_files: list[str] = Field(max_length=500)


class ChatRequest(StrictModel):
    prompt: str = Field(min_length=1, max_length=16000)
    conversation: list[Exchange] = Field(max_length=8)
    review_ui: bool = False


class EditorConsole:
    def __init__(self, *, dry_run: bool):
        self.dry_run = dry_run
        self.diff = None
        self.decisions = Queue()
        self.cancelled_in_confirmation = False
        self.supports_file_review = False

    def start(self) -> ChatRequest:
        # The daemon owns this duplicate after the first read. It can wait on
        # Windows pipe input without keeping Python alive when the turn finishes.
        stream = os.fdopen(os.dup(sys.stdin.fileno()), "rb")
        try:
            line = stream.readline(1024 * 1024 + 1)
            if not line.endswith(b"\n") or len(line) > 1024 * 1024:
                raise ValueError("Invalid editor chat request")
            request = ChatRequest.model_validate_json(line)
            if not request.prompt.strip() or "\0" in request.prompt:
                raise ValueError("Enter a message before sending")
            self.supports_file_review = request.review_ui
        except BaseException:
            stream.close()
            raise
        loop = asyncio.get_running_loop()
        task = asyncio.current_task()

        def cancel_running_turn():
            if not self.cancelled_in_confirmation:
                task.cancel()

        def read_decisions():
            try:
                with stream:
                    while line := stream.readline(8193):
                        if len(line) > 8192 or not line.endswith(b"\n"):
                            break
                        message = json.loads(line)
                        if not isinstance(message, dict) or not isinstance(message.get("id"), str):
                            break
                        self.decisions.put(message)
            except (ValueError, OSError):
                pass
            finally:
                self.decisions.put(None)
                try:
                    loop.call_soon_threadsafe(cancel_running_turn)
                except RuntimeError:
                    pass  # EOF after the turn has already shut down.

        Thread(target=read_decisions, daemon=True).start()
        return request

    def emit(self, kind: str, **payload):
        print(json.dumps(dict(type=kind, **redact_value(payload)), ensure_ascii=True), flush=True)

    def event(self, message: str):
        self.diff = None
        self.emit("progress", message=message)

    def preview(self, diff: str):
        self.diff = diff
        if self.dry_run:
            suffix = "\n[Preview truncated]" if len(diff) > 200000 else ""
            self.emit("preview", diff=diff[:200000] + suffix)

    def confirm(self, message: str, *, source: bool = False, review: bool = False) -> bool:
        diff, self.diff = self.diff, None
        if diff and len(diff) > 200000:
            self.emit(
                "progress", message="The proposed diff is too large to review. Try smaller edits."
            )
            return False
        identifier = uuid4().hex
        self.emit(
            "approval", id=identifier, message=message, diff=diff, source=source, review=review
        )
        for decision in self._messages(identifier):
            if set(decision) == {"id", "approved"} and type(decision["approved"]) is bool:
                return decision["approved"]

    def review_files(self, message: str, changes: list[Change], groups: dict[int, int]) -> set[int]:
        identifier = uuid4().hex
        files = review_entries(changes, groups)
        self.emit(
            "approval", id=identifier, message=message, source=False, review=True, files=files
        )
        indices = set(range(len(changes)))
        for decision in self._messages(identifier):
            if set(decision) == {"id", "approved"} and decision["approved"] is False:
                return set()
            if set(decision) == {"id", "open_file"}:
                index = decision["open_file"]
                if type(index) is int and index in indices:
                    change = changes[index]
                    self.emit(
                        "review_document",
                        id=identifier,
                        file=index,
                        before=(change.before or b"").decode("utf-8-sig"),
                        after=(change.after or b"").decode("utf-8-sig"),
                    )
                    continue
            if set(decision) == {"id", "selected"}:
                selection = decision["selected"]
                if (
                    isinstance(selection, list)
                    and 0 < len(selection) <= len(changes)
                    and all(type(index) is int and index in indices for index in selection)
                ):
                    selected = set(selection)
                    if all(
                        (index in selected) == (group in selected)
                        for index, group in groups.items()
                    ):
                        return selected
            self.emit(
                "review_error",
                id=identifier,
                message="Select valid files and keep linked renames together.",
            )

    def _messages(self, identifier: str):
        while True:
            decision = self.decisions.get()
            if decision is None:
                self.cancelled_in_confirmation = True
                raise asyncio.CancelledError
            if decision["id"] == identifier:
                yield decision
