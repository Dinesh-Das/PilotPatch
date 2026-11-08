"""Temporary loopback transport for the user-installed, scoped Edge extension.

No browser launch, credential inspection, arbitrary JavaScript or Microsoft endpoints.
The pairing token authenticates the extension, not the Microsoft account.
"""

import asyncio
import base64
import binascii
import hashlib
import hmac
import json
import re
import secrets
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from filelock import FileLock, Timeout

from pilotpatch.providers.base import ProviderError
from pilotpatch.security.storage import atomic_json, private_directory

EXTENSION_ID = "jhmhehhjehmldcehodmlbopiajhcghki"
DEFAULT_PORT = 57423
MAX_BODY = 12_000_000


def pairing(home: Path, *, create=False) -> dict:
    path = home / "edge-pairing.json"
    if not path.exists():
        if not create:
            raise ProviderError(
                "Existing Edge is not paired. Run 'pilotpatch connect' for one-time setup. "
                "PilotPatch will not open another browser or profile."
            )
        private_directory(home)
        atomic_json(
            path,
            dict(
                version=1, token=secrets.token_hex(32), port=DEFAULT_PORT, extension_id=EXTENSION_ID
            ),
        )
    if path.stat().st_size > 4096:
        raise ProviderError("Invalid Edge pairing file; recreate it using connect")
    data = json.loads(path.read_text(encoding="utf-8"))
    if (
        not isinstance(data, dict)
        or data.get("version") != 1
        or data.get("extension_id") != EXTENSION_ID
        or not isinstance(data.get("token"), str)
        or not re.fullmatch(r"[a-f0-9]{64}", data["token"])
        or type(data.get("port")) is not int
        or not 1024 <= data["port"] <= 65535
    ):
        raise ProviderError("Invalid Edge pairing file; recreate it using connect")
    return data


class Bridge:
    def __init__(self, home: Path, *, port: int | None = None):
        self.home = home
        self.port_override = port
        self.extension_id = EXTENSION_ID
        self.lock = FileLock(home / "browser.lock", timeout=0)
        self.server = None
        self.handlers = set()
        self.connected = asyncio.Event()
        self.identity = None
        self.connection_error = None
        self.pending = None
        self.token = ""
        self.port = 0
        self.session = secrets.token_hex(32)
        self.nonces = set()

    async def open(self):
        data = pairing(self.home, create=True)
        self.token = data["token"]
        try:
            self.lock.acquire()
        except Timeout as exc:
            raise ProviderError(
                "Another PilotPatch browser task is active; leave it open or stop it"
            ) from exc
        try:
            self.connected.clear()
            self.identity = None
            self.connection_error = None
            self.session = secrets.token_hex(32)
            self.nonces.clear()
            self.server = await asyncio.start_server(
                self._handle,
                "127.0.0.1",
                data["port"] if self.port_override is None else self.port_override,
                limit=16384,
            )
            self.port = self.server.sockets[0].getsockname()[1]
        except BaseException:
            self.lock.release()
            raise

    async def close(self):
        if self.server:
            self.server.close()
            await self.server.wait_closed()
            self.server = None
        for task in list(self.handlers):
            task.cancel()
        if self.handlers:
            await asyncio.gather(*list(self.handlers), return_exceptions=True)
        self.lock.release()

    async def call(self, action: str, payload: dict, *, wait_seconds=15):
        if action not in {"status", "submit", "response"}:
            raise ValueError("Unsupported browser action")
        if self.pending is not None:
            raise ProviderError("Concurrent browser actions are not supported")
        future = asyncio.get_running_loop().create_future()
        command = dict(id=secrets.token_hex(16), action=action, payload=payload)
        self.pending = dict(command=command, future=future, delivered=False)
        try:
            return await asyncio.wait_for(future, wait_seconds)
        except TimeoutError as exc:
            raise ProviderError(
                "Existing Edge stopped responding; command has an unknown outcome. "
                "No automatic replay occurred. Inspect the selected Copilot tab."
            ) from exc
        finally:
            self.pending = None

    def _dispatch(self, path, data):
        if data.get("protocol") != 2:
            if path == "/next" and self.identity is None:
                self.connection_error = (
                    "PilotPatch Edge extension needs an update. Run connect, then Reload "
                    "the extension at edge://extensions and select your tab again. "
                    "No prompt was submitted."
                )
                self.connected.set()
            return 409, {"error": "extension_upgrade_required"}
        client, tab = data.get("client"), data.get("tab")
        if not isinstance(client, str) or not 1 <= len(client) <= 128 or type(tab) is not int:
            return 400, {"error": "invalid_identity"}
        identity = (client, tab)
        if self.identity is not None and self.identity != identity:
            return 409, {"error": "different_selected_tab_or_profile"}
        if path == "/next":
            self.identity = identity
            self.connected.set()
            if self.pending and not self.pending["delivered"]:
                self.pending["delivered"] = True
                return 200, self.pending["command"]
            return 200, {"idle": True}
        if path == "/commit":
            pending = self.pending
            if (
                not pending
                or not pending["delivered"]
                or pending["future"].done()
                or pending["command"]["action"] != "submit"
                or data.get("id") != pending["command"]["id"]
                or pending.get("commit_granted")
            ):
                return 409, {"error": "submit_not_pending"}
            pending["commit_granted"] = True
            return 200, {"authorized": True}
        if path == "/result":
            pending = self.pending
            if (
                not pending
                or not pending["delivered"]
                or pending["future"].done()
                or data.get("id") != pending["command"]["id"]
            ):
                return 409, {"error": "stale_result"}
            if (
                pending["command"]["action"] == "submit"
                and isinstance(data.get("result"), dict)
                and data["result"].get("submitted") is True
                and not pending.get("commit_granted")
            ):
                return 409, {"error": "commit_not_authorized"}
            if isinstance(data.get("error"), str):
                # Extension returns fixed error codes, never page text or credentials.
                explanations = {
                    "composer_has_draft": "Selected Copilot tab has an unsent draft. "
                    "Your draft was preserved; send it or clear it manually before retrying.",
                    "send_control_not_unique": "A unique Copilot Send button was not recognized. "
                    "Update selectors.send; no prompt was submitted.",
                    "send_disabled": "Copilot's Send control was not ready. Inspect the draft.",
                    "turn_lost": "The Copilot page changed during this turn; outcome is unknown.",
                    "not_ready": "Copilot is signed out, busy or unavailable. "
                    "Check the selected tab.",
                    "selected_tab_left_copilot": "The selected tab has left Copilot.",
                }
                message = explanations.get(
                    data["error"],
                    "Existing Copilot tab could not complete the action. Check the extension "
                    "and selected tab; outcome may be unknown.",
                )
                pending["future"].set_exception(
                    ProviderError(message + " No automatic replay occurred.")
                )
            elif isinstance(data.get("result"), dict):
                pending["future"].set_result(data["result"])
            else:
                return 400, {"error": "invalid_result"}
            return 200, {"ok": True}
        return 404, {"error": "unknown_route"}

    async def _handle(self, reader, writer):
        task = asyncio.current_task()
        if len(self.handlers) >= 8:
            writer.close()
            return
        self.handlers.add(task)
        code, result = 400, {"error": "invalid_request"}
        nonce, sign_response, encrypted = "", False, False
        try:
            async with asyncio.timeout(4):
                head = await reader.readuntil(b"\r\n\r\n")
                lines = head.decode("ascii").split("\r\n")
                method, path, version = lines[0].split(" ")
                headers = {}
                for line in lines[1:]:
                    if not line:
                        continue
                    key, value = line.split(":", 1)
                    key = key.lower()
                    if key in headers:
                        raise ValueError("Duplicate header")
                    headers[key] = value.strip()
                origin = headers.get("origin")
                if (
                    headers.get("host") != f"127.0.0.1:{self.port}"
                    or origin != f"chrome-extension://{self.extension_id}"
                ):
                    code, result = 403, {"error": "forbidden"}
                elif method != "POST" or version != "HTTP/1.1":
                    code, result = 405, {"error": "post_required"}
                elif "transfer-encoding" in headers:
                    code, result = 400, {"error": "unsupported_encoding"}
                else:
                    size = int(headers.get("content-length", "-1"))
                    if not 0 <= size <= MAX_BODY:
                        code, result = 413, {"error": "invalid_size"}
                    elif headers.get("content-type") != "application/json":
                        code, result = 400, {"error": "json_required"}
                    else:
                        raw = await reader.readexactly(size)
                        nonce = headers.get("x-pilotpatch-nonce", "")
                        if not re.fullmatch(r"[a-f0-9]{64}", nonce):
                            code, result = 403, {"error": "invalid_nonce"}
                        elif path == "/hello":
                            sign_response = True
                            code, result = 200, {"session": self.session, "protocol": 2}
                        else:
                            message = (f"request\n{self.session}\n{path}\n{nonce}\n").encode() + raw
                            expected = self.mac(message)
                            supplied = headers.get("x-pilotpatch-mac", "")
                            if (
                                not hmac.compare_digest(supplied, expected)
                                or nonce in self.nonces
                                or len(self.nonces) >= 100000
                            ):
                                code, result = 403, {"error": "invalid_proof"}
                            else:
                                self.nonces.add(nonce)
                                sign_response = True
                                encrypted = True
                                aad = f"request\n{self.session}\n{path}\n{nonce}"
                                data = json.loads(self.decrypt(raw, aad))
                                if isinstance(data, dict):
                                    code, result = self._dispatch(path, data)
        except (
            ValueError,
            KeyError,
            TypeError,
            InvalidTag,
            binascii.Error,
            UnicodeError,
            asyncio.IncompleteReadError,
            asyncio.LimitOverrunError,
            TimeoutError,
        ):
            pass
        except asyncio.CancelledError:
            writer.close()
            raise
        finally:
            self.handlers.discard(task)
        try:
            body = json.dumps(result).encode()
            if encrypted:
                body = self.encrypt(body, f"response\n{self.session}\n{path}\n{nonce}")
            proof = ""
            if sign_response:
                message = f"response\n{nonce}\n{code}\n".encode() + body
                proof = f"X-PilotPatch-Mac: {self.mac(message)}\r\n"
            writer.write(
                (
                    f"HTTP/1.1 {code} Response\r\nContent-Type: application/json\r\n"
                    f"Content-Length: {len(body)}\r\nCache-Control: no-store\r\n"
                    f"{proof}Connection: close\r\n\r\n"
                ).encode()
                + body
            )
            await writer.drain()
        except (ConnectionError, OSError):
            pass
        finally:
            writer.close()
            await writer.wait_closed()

    def mac(self, message: bytes) -> str:
        return hmac.new(bytes.fromhex(self.token), message, hashlib.sha256).hexdigest()

    def encrypt(self, plaintext: bytes, associated: str) -> bytes:
        key = bytes.fromhex(self.mac(f"encryption\n{self.session}".encode()))
        iv = secrets.token_bytes(12)
        ciphertext = AESGCM(key).encrypt(iv, plaintext, associated.encode())
        return json.dumps(
            dict(iv=base64.b64encode(iv).decode(), ciphertext=base64.b64encode(ciphertext).decode())
        ).encode()

    def decrypt(self, envelope: bytes, associated: str) -> bytes:
        data = json.loads(envelope)
        iv = base64.b64decode(data["iv"], validate=True)
        if len(iv) != 12:
            raise ValueError("Invalid encryption nonce")
        key = bytes.fromhex(self.mac(f"encryption\n{self.session}".encode()))
        ciphertext = base64.b64decode(data["ciphertext"], validate=True)
        return AESGCM(key).decrypt(iv, ciphertext, associated.encode())
