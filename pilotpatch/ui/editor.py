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


class Exchange(StrictModel):
    user: str = Field(max_length=16000)
    assistant: str = Field(max_length=20000)
    changed_files: list[str] = Field(max_length=500)


class ChatRequest(StrictModel):
    prompt: str = Field(min_length=1, max_length=16000)
    conversation: list[Exchange] = Field(max_length=8)


class EditorConsole:
    def __init__(self, *, dry_run: bool):
        self.dry_run = dry_run
        self.diff = None
        self.decisions = Queue()
        self.cancelled_in_confirmation = False

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
                    while line := stream.readline(1024):
                        message = json.loads(line)
                        if (
                            not isinstance(message, dict)
                            or not isinstance(message.get("id"), str)
                            or type(message.get("approved")) is not bool
                        ):
                            break
                        self.decisions.put((message["id"], message["approved"]))
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

    def confirm(self, message: str, *, source: bool = False) -> bool:
        diff, self.diff = self.diff, None
        if diff and len(diff) > 200000:
            self.emit(
                "progress", message="The proposed diff is too large to review. Try smaller edits."
            )
            return False
        identifier = uuid4().hex
        self.emit("approval", id=identifier, message=message, diff=diff, source=source)
        while True:
            decision = self.decisions.get()
            if decision is None:
                self.cancelled_in_confirmation = True
                raise asyncio.CancelledError
            if decision[0] == identifier:
                return decision[1]
