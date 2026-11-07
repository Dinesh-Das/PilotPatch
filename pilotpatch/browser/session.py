from pathlib import Path

from filelock import FileLock, Timeout
from playwright.async_api import async_playwright

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
        try:
            profile = self.home / "edge-profile"
            profile.mkdir(exist_ok=True)
            marker = profile / "pilotpatch-owned.json"
            if not marker.exists():
                atomic_json(marker, {"owner": "PilotPatch", "profile_version": 1})
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
            self.context = await self.playwright.chromium.launch_persistent_context(
                str(profile), **options
            )
            self.context.set_default_timeout(10000)
            # A dedicated new page isolates this task from historical conversations.
            self.page = await self.context.new_page()
            await self.page.goto(
                "https://copilot.microsoft.com/", wait_until="domcontentloaded", timeout=45000
            )
            return self.page
        except Exception as exc:
            await self.close()
            raise ProviderError(
                "Cannot initialize Edge/Copilot. Check Edge installation, enterprise "
                "automation policies, proxy/TLS and connectivity; run doctor. "
                "No alternative provider was used."
            ) from exc

    async def close(self):
        try:
            if self.context:
                await self.context.close()
        finally:
            if self.playwright:
                await self.playwright.stop()
            self.context = self.playwright = self.page = None
            if self.lock.is_locked:
                self.lock.release()
