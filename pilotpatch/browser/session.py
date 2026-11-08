import asyncio
from pathlib import Path

from filelock import FileLock, Timeout
from playwright.async_api import async_playwright

from pilotpatch.browser.diagnostics import startup_failure
from pilotpatch.config import Config
from pilotpatch.providers.base import ProviderError
from pilotpatch.security.storage import atomic_json, private_directory


class EdgeSession:
    def __init__(self, home: Path, config: Config, *, headless: bool = False):
        self.home, self.config, self.headless = home, config, headless
        self.lock = FileLock(home / "browser.lock", timeout=0)
        self.playwright = None
        self.context = None
        self.page = None

    async def open(self):
        private_directory(self.home)
        try:
            self.lock.acquire()
        except Timeout as exc:
            raise ProviderError("PilotPatch Edge profile is in use by another process") from exc
        stage = "preparing the dedicated browser profile"
        try:
            profile = self.home / "edge-profile"
            profile.mkdir(exist_ok=True)
            marker = profile / "pilotpatch-owned.json"
            if not marker.exists():
                atomic_json(marker, {"owner": "PilotPatch", "profile_version": 1})
            stage = "starting Playwright"
            self.playwright = await async_playwright().start()
            options = dict(
                channel="msedge",
                headless=self.headless,
                chromium_sandbox=True,
                accept_downloads=False,
                viewport={"width": 1280, "height": 900},
            )
            if self.config.proxy_server:
                options["proxy"] = {"server": self.config.proxy_server}
            stage = "launching Microsoft Edge"
            self.context = await self.playwright.chromium.launch_persistent_context(
                str(profile), **options
            )
            self.context.set_default_timeout(10000)
            # A dedicated new page isolates this task from historical conversations.
            stage = "creating the Copilot tab"
            self.page = await self.context.new_page()
            stage = "opening the Copilot page"
            await self.page.goto(
                "https://copilot.microsoft.com/", wait_until="domcontentloaded", timeout=45000
            )
            return self.page
        except (Exception, asyncio.CancelledError) as exc:
            cleanup_failed = False
            try:
                await self.close()
            except Exception:
                cleanup_failed = True
            if isinstance(exc, asyncio.CancelledError):
                raise
            raise ProviderError(startup_failure(stage, exc, cleanup_failed=cleanup_failed)) from exc

    async def close(self):
        try:
            if self.context:
                await self.context.close()
        finally:
            try:
                if self.playwright:
                    await self.playwright.stop()
            finally:
                self.context = self.playwright = self.page = None
                if self.lock.is_locked:
                    self.lock.release()
