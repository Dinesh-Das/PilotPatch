"""Operate only the Copilot tab selected by the user in their existing Edge profile."""

import asyncio
import secrets
import time
from contextlib import suppress
from pathlib import Path

from pilotpatch.browser.bridge import Bridge, pairing
from pilotpatch.config import Config
from pilotpatch.providers.base import AuthenticationRequired, ProviderError


class CopilotExistingEdge:
    def __init__(self, home: Path, config: Config):
        self.home = home
        self.config = config
        self.bridge = Bridge(home)
        self.poisoned = False
        self.reasoning_mode = None

    async def open(self):
        pairing(self.home)  # Setup must be explicit; do not launch any browser as fallback.
        try:
            await self.bridge.open()
            await asyncio.wait_for(self.bridge.connected.wait(), self.config.edge_connect_timeout)
            if self.bridge.connection_error:
                raise ProviderError(self.bridge.connection_error)
        except TimeoutError as exc:
            await self.close()
            raise ProviderError(
                "Edge did not connect. While Test connection is running, open PilotPatch in "
                "the Edge profile with your Copilot tab. Choose Use this tab if needed. "
                "If the toolbar icon is missing, check whether PilotPatch is enabled at "
                "edge://extensions."
            ) from exc
        except BaseException:
            await self.close()
            raise
        return self

    async def close(self):
        await self.bridge.close()  # Only our local transport; never close Edge or its tabs.

    async def record_probe_success(self) -> bool:
        # Older Edge builds can still run the probe without displaying its receipt.
        if self.bridge.probe_receipts:
            with suppress(ProviderError):
                result = await self.bridge.call("record_probe", {}, wait_seconds=4)
                return result.get("recorded") is True
        return False

    async def status(self):
        status = await self.bridge.call("status", {"selectors": self.config.selectors.model_dump()})
        for key in ("authenticated", "chat_ready"):
            if type(status.get(key)) is not bool:
                raise ProviderError("Invalid browser status; update the PilotPatch Edge extension")
        if not isinstance(status.get("state"), str):
            raise ProviderError("Invalid browser state; update the PilotPatch Edge extension")
        return dict(status, connection_verified=False, connection="existing-edge")

    async def login(self, wait_seconds=600, *, on_status=None):
        deadline = time.monotonic() + wait_seconds
        previous = None
        while True:
            status = await self.status()
            if status["state"] != previous and on_status:
                on_status(status)
            previous = status["state"]
            if status["authenticated"]:
                return status
            if status["state"] == "service_error":
                raise ProviderError(
                    "Copilot shows a service error; sign-in is unverified. Check your selected "
                    "tab manually. No prompt was submitted and no other profile was opened."
                )
            if time.monotonic() >= deadline:
                raise AuthenticationRequired(
                    "Sign-in was not detected in your selected Copilot tab. Complete sign-in "
                    "manually or open its account menu; PilotPatch leaves this tab open."
                )
            await asyncio.sleep(0.5)

    async def send(self, prompt: str) -> str:
        if self.poisoned:
            raise ProviderError(
                "Previous turn has an unknown outcome; inspect Edge before resuming"
            )
        if len(prompt.encode()) > self.config.max_context_bytes:
            raise ProviderError("Prompt exceeds configured context budget")
        status = await self.status()
        if status["state"] == "service_error":
            raise ProviderError("Copilot shows a service error. No prompt was submitted.")
        if not status["authenticated"] or not status["chat_ready"]:
            steps = {
                "manual_authentication_required": "Finish signing in and return to Copilot.",
                "sign_in_required": "Sign in to Copilot in the selected Edge tab.",
                "account_control_not_recognized": "Open the Copilot account menu in this tab.",
                "waiting_for_copilot_chat": "Open a Copilot chat in the selected tab and wait "
                "for the message box.",
            }
            raise AuthenticationRequired(
                steps.get(status["state"], "Check the Copilot message box in the selected tab.")
                + " No prompt was submitted."
            )
        nonce = secrets.token_hex(12)
        payload = dict(
            selectors=self.config.selectors.model_dump(),
            nonce=nonce,
            max=self.config.max_response_bytes,
        )
        try:
            result = await self.bridge.call(
                "submit",
                dict(
                    payload,
                    text=prompt + f"\nPilotPatch request_id: {nonce}. Do not echo this marker.",
                ),
            )
            if result.get("submitted") is not True:
                raise ProviderError("Copilot submission could not be confirmed; inspect Edge")
            mode = result.get("reasoning_mode")
            self.reasoning_mode = mode if mode in ("think_deeper", "auto") else "current"
            deadline = time.monotonic() + self.config.response_timeout
            previous, stable_since = None, time.monotonic()
            while time.monotonic() < deadline:
                data = await self.bridge.call("response", payload)
                if data.get("error") or data.get("ambiguous") or data.get("oversize"):
                    raise ProviderError("Copilot response failed or was ambiguous; inspect Edge")
                text = data.get("text", "")
                if not isinstance(text, str) or len(text.encode()) > self.config.max_response_bytes:
                    raise ProviderError("Invalid or oversized Copilot response")
                eligible = (
                    data.get("bound") is True
                    and bool(text)
                    and data.get("completed") is True
                    and not data.get("busy")
                    and not data.get("generating")
                )
                if text != previous or not eligible:
                    previous, stable_since = text, time.monotonic()
                elif time.monotonic() - stable_since >= self.config.stable_seconds:
                    return text
                await asyncio.sleep(self.config.poll_seconds)
            raise ProviderError("Timed out waiting for a complete Copilot response")
        except BaseException:
            self.poisoned = True
            # Once submit is attempted, cancellation/failure must never cause a replay.
            raise
