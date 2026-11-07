"""Visible UI automation only. No internal endpoints, cookie extraction or stealth."""

import asyncio
import secrets
import time
from pathlib import Path
from urllib.parse import urlparse

from pilotpatch.browser.session import EdgeSession
from pilotpatch.config import Config
from pilotpatch.providers.base import AuthenticationRequired, ProviderError

COPILOT_HOSTS = {"copilot.microsoft.com", "copilot.com", "copilot.ai"}


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
        matches = self.page.locator(selector)
        return [
            matches.nth(i)
            for i in range(await matches.count())
            if await matches.nth(i).is_visible()
        ]

    def _copilot_origin(self) -> bool:
        url = urlparse(self.page.url)
        return url.scheme == "https" and url.hostname in COPILOT_HOSTS

    async def status(self) -> dict:
        if not self.page or self.page.is_closed():
            return dict(authenticated=False, state="browser_closed", account="unavailable")
        if not self._copilot_origin():
            return dict(
                authenticated=False, state="manual_authentication_required", account="unavailable"
            )
        profiles = await self._visible(self.config.selectors.signed_in)
        composers = await self._visible(self.config.selectors.composer)
        authenticated = bool(profiles) and len(composers) == 1
        # No cookies, localStorage, passwords or hidden authentication state are inspected.
        account = "unavailable (inspect the visible Edge account menu)"
        if len(profiles) == 1:
            label = await profiles[0].get_attribute("aria-label")
            if label:
                account = label[:160]
        return dict(
            authenticated=authenticated,
            state="authenticated_ui" if authenticated else "sign_in_or_selector_check_required",
            account=account,
            environment=urlparse(self.page.url).hostname,
        )

    async def login(self, wait_seconds: float = 600) -> dict:
        deadline = time.monotonic() + wait_seconds
        while time.monotonic() < deadline:
            status = await self.status()
            if status["authenticated"]:
                return status
            await asyncio.sleep(1)
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
        if not status["authenticated"]:
            raise AuthenticationRequired(
                "Copilot sign-in expired or UI selectors changed. Run login/status; "
                "complete authentication manually. No fallback is available."
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
