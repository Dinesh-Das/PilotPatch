"""Visible UI automation only. No internal endpoints, cookie extraction or stealth."""

import asyncio
import secrets
import time
from pathlib import Path

from pilotpatch.browser.readiness import copilot_origin, observe, service_error_visible, visible
from pilotpatch.browser.session import EdgeSession
from pilotpatch.config import Config
from pilotpatch.providers.base import AuthenticationRequired, ProviderError


class CopilotBrowser:
    def __init__(self, home: Path, config: Config):
        self.config = config
        self.session = EdgeSession(home, config)
        self.page = None
        self.conversation_url = None
        self.poisoned = False

    async def open(self):
        self.page = await self.session.open()
        return self

    async def close(self):
        await self.session.close()

    async def _visible(self, selector: str):
        return await visible(self.page, selector)

    def _copilot_origin(self) -> bool:
        return copilot_origin(self.page)

    async def status(self) -> dict:
        current = await observe(self.page, self.config.selectors)
        if current["authenticated"] or self.conversation_url is not None:
            return current
        # Microsoft sign-in can finish in a popup/new tab. Only inspect pages in the
        # context this process owns; never attach to another browser/profile/window.
        context = self.session.context
        candidates = []
        for page in context.pages if context else []:
            if page is self.page or page.is_closed() or not copilot_origin(page):
                continue
            status = await observe(page, self.config.selectors)
            if status["authenticated"]:
                candidates.append((page, status))
        if len(candidates) == 1:
            self.page, status = candidates[0]
            self.session.page = self.page
            return status
        if len(candidates) > 1:
            return dict(
                current, state="multiple_copilot_tabs", authenticated=False, chat_ready=False
            )
        return current

    async def login(self, wait_seconds: float = 600, *, on_status=None) -> dict:
        deadline = time.monotonic() + wait_seconds
        previous = None
        status = None
        while time.monotonic() < deadline:
            status = await self.status()
            signature = (status["state"], status["composer_count"], status["account_control_count"])
            if signature != previous and on_status is not None:
                on_status(status)
            previous = signature
            if status["authenticated"]:
                return status
            if status["state"] == "service_error":
                raise ProviderError(
                    "Copilot reports a service error before sign-in could be verified. "
                    "Refresh the chat page manually and retry. No prompt was submitted."
                )
            await asyncio.sleep(min(0.5, max(0, deadline - time.monotonic())))
        if status and status["state"] == "account_control_not_recognized":
            raise AuthenticationRequired(
                "Copilot chat is visible, but its signed-in account control was not recognized. "
                "This is a selector/readiness issue; check selectors.signed_in in operator config."
            )
        raise AuthenticationRequired(
            "Manual sign-in was not detected. Complete Microsoft sign-in/MFA "
            "in the dedicated Edge window; verify selectors if already signed in."
        )

    async def _check_ready(self):
        if self.poisoned:
            raise ProviderError(
                "Previous browser turn has an unknown outcome; resume in a fresh conversation"
            )
        status = await self.status()
        deadline = time.monotonic() + min(15, self.config.response_timeout)
        while status["state"] in {
            "waiting_for_copilot_chat",
            "manual_authentication_required",
            "chat_input_not_recognized",
            "multiple_chat_inputs",
        }:
            if time.monotonic() >= deadline:
                break
            await asyncio.sleep(0.25)
            status = await self.status()
        if status["state"] == "service_error":
            message = (
                "You are signed in, but Copilot reports a service error."
                if status["authenticated"]
                else "Copilot reports a service error; sign-in is unverified."
            )
            raise ProviderError(
                message + " Refresh the Copilot page manually and use Test connection "
                "after it recovers. No prompt was submitted."
            )
        if not status["authenticated"]:
            if status["state"] == "account_control_not_recognized":
                raise AuthenticationRequired(
                    "Copilot chat is visible, but its account control was not recognized. "
                    "Open Copilot's account menu or update selectors.signed_in. "
                    "No prompt was submitted."
                )
            raise AuthenticationRequired(
                "Copilot sign-in expired or UI selectors changed. Run login/status; "
                "complete authentication manually. No fallback is available."
            )
        if not status["chat_ready"]:
            raise ProviderError(
                "Sign-in was detected, but a unique Copilot chat input was not recognized. "
                "Check selectors.composer; no prompt was submitted."
            )

    async def send(self, prompt: str) -> str:
        await self._check_ready()
        if len(prompt.encode("utf-8")) > self.config.max_context_bytes:
            raise ProviderError("Prompt exceeds configured context budget")
        if await self._visible(self.config.selectors.stop):
            raise ProviderError("Copilot is already generating; wait before starting another turn")
        nonce = secrets.token_hex(12)
        submitted = prompt + f"\nPilotPatch request_id: {nonce}. Do not echo this marker."
        composer = (await self._visible(self.config.selectors.composer))[0]
        try:
            await composer.fill(submitted)
            sends = await self._visible(self.config.selectors.send)
            if len(sends) > 1:
                raise ProviderError("Ambiguous Copilot send controls; update selectors")
            # Once submission is attempted we never automatically submit it again.
            if sends:
                await sends[0].click()
            else:
                await composer.press("Enter")
            response = await self._wait_response(nonce)
            self.conversation_url = self.page.url
            return response
        except asyncio.CancelledError:
            self.poisoned = True
            raise
        except Exception as exc:
            self.poisoned = True
            if isinstance(exc, ProviderError):
                raise
            raise ProviderError(
                "Copilot browser turn failed. Prompt may have been accepted; no automatic "
                "resubmission occurred. Inspect Edge, then resume the saved local session."
            ) from exc

    async def _snapshot(self, nonce: str):
        # Match the exact submitted user turn, then accept only a response that follows
        # it in document order. Old/remounted messages cannot satisfy this boundary.
        return await self.page.evaluate(
            """({s, nonce, max}) => {
          const visible = e => !!(e.getClientRects().length);
          const users = [...document.querySelectorAll(s.user)]
            .filter(e => visible(e) && e.innerText.includes(nonce));
          if (users.length !== 1) return {bound: false, ambiguous: users.length > 1};
          const answers = [...document.querySelectorAll(s.assistant)].filter(e =>
            visible(e) && (users[0].compareDocumentPosition(e) & Node.DOCUMENT_POSITION_FOLLOWING));
          if (answers.length !== 1) return {bound: false, ambiguous: answers.length > 1};
          const answer = answers[0];
          const copy = answer.cloneNode(true);
          copy.querySelectorAll('button, svg, script, style, [aria-hidden="true"]')
            .forEach(e => e.remove());
          const blocks = copy.querySelectorAll('pre');
          // Rendered JSON fences can have a separate language label and Copy bar.
          // Exactly one code block is safe to parse; multiple blocks remain ambiguous.
          const text = blocks.length === 1
            ? blocks[0].textContent : (copy.textContent || '');
          if (text.length > max) return {oversize: true};
          const completed = [...answer.querySelectorAll(s.completion)].some(visible);
          const busy = answer.getAttribute('aria-busy') === 'true' ||
            !!answer.querySelector('[aria-busy="true"]');
          const generating = [...document.querySelectorAll(s.stop)].some(visible);
          const errors = [...document.querySelectorAll(s.errors)]
            .filter(visible).map(e => e.innerText).filter(Boolean);
          return {bound: true, text, completed, busy, generating, error: errors.length > 0};
        }""",
            dict(
                s=self.config.selectors.model_dump(),
                nonce=nonce,
                max=self.config.max_response_bytes,
            ),
        )

    async def _wait_response(self, nonce: str) -> str:
        deadline = time.monotonic() + self.config.response_timeout
        previous = None
        stable_since = time.monotonic()
        while time.monotonic() < deadline:
            if not self._copilot_origin():
                raise AuthenticationRequired("Copilot redirected to sign-in; authenticate manually")
            if await service_error_visible(self.page, self.config.selectors):
                raise ProviderError(
                    "Copilot displayed an error before completing its response. "
                    "Inspect the browser; the prompt was not resubmitted."
                )
            data = await self._snapshot(nonce)
            if data.get("ambiguous"):
                raise ProviderError("Ambiguous response turn; update user/assistant selectors")
            if data.get("oversize"):
                raise ProviderError("Copilot response exceeds maximum size; use smaller actions")
            if data.get("error"):
                raise ProviderError(
                    "Copilot displayed an error; inspect the browser (content omitted for privacy)"
                )
            text = data.get("text", "")
            if len(text.encode("utf-8")) > self.config.max_response_bytes:
                raise ProviderError("Copilot response exceeds maximum size")
            # Stability alone never means completion. Require response-owned completion
            # controls, no generation indicator, and no aria-busy state.
            eligible = (
                bool(text)
                and data.get("completed")
                and not data.get("generating")
                and not data.get("busy")
            )
            if text != previous or not eligible:
                stable_since = time.monotonic()
                previous = text
            elif time.monotonic() - stable_since >= self.config.stable_seconds:
                return text
            await asyncio.sleep(self.config.poll_seconds)
        raise ProviderError(
            "Timed out waiting for a complete response. No partial answer was executed and "
            "the prompt was not resubmitted. Inspect Edge and resume."
        )
