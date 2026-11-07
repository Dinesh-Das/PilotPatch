"""Real Edge, local HTML only. These tests do not contact Microsoft Copilot."""

import asyncio
import shutil
import sys
from pathlib import Path

import pytest
from playwright.async_api import async_playwright

from pilotpatch.config import Config
from pilotpatch.providers.base import ProviderError
from pilotpatch.providers.copilot_browser import CopilotBrowser

FIXTURE = """<!doctype html><html><body>
<button aria-label="Account">Test fixture account</button>
<div data-content="user-message">historical prompt</div>
<div data-content="ai-message"><pre>historical response</pre>
<button aria-label="Copy">Copy</button></div>
<textarea></textarea><button aria-label="Send message" onclick="send()">Send</button>
<script>
window.sentCount = 0;
window.send = () => {
  window.sentCount++;
  const user = document.createElement('div'); user.dataset.content='user-message';
  user.textContent=document.querySelector('textarea').value; document.body.append(user);
  const assistant=document.createElement('div'); assistant.dataset.content='ai-message';
  assistant.innerHTML='<span>json</span><pre>partial</pre>'; document.body.append(assistant);
  const stop=document.createElement('button'); stop.setAttribute('aria-label','Stop generating');
  stop.textContent='Stop'; document.body.append(stop);
  setTimeout(() => {
    assistant.querySelector('pre').textContent = JSON.stringify({type:'final',
      summary:'Complete response',files_changed:[],tests:'not run',remaining_issues:[]});
    assistant.insertAdjacentHTML('beforeend','<button aria-label="Copy">Copy</button>');
    stop.remove();
  }, 300);
};
</script></body></html>"""


@pytest.fixture
async def local_browser(tmp_path):
    if sys.platform == "win32":
        paths = [
            Path("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"),
            Path("C:/Program Files/Microsoft/Edge/Application/msedge.exe"),
        ]
        if not any(p.exists() for p in paths):
            pytest.skip("Edge not installed")
    elif not shutil.which("microsoft-edge"):
        pytest.skip("Edge not installed")
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(
            channel="msedge", headless=True, chromium_sandbox=True
        )
        page = await browser.new_page()
        # Route a fake origin to local HTML: no Microsoft request leaves this browser.
        await page.route(
            "https://copilot.microsoft.com/**",
            lambda route: route.fulfill(body=FIXTURE, content_type="text/html"),
        )
        await page.goto("https://copilot.microsoft.com/")
        provider = CopilotBrowser(
            tmp_path, Config(stable_seconds=0.2, poll_seconds=0.05, response_timeout=5)
        )
        provider.page = page
        yield provider
        await browser.close()


@pytest.mark.browser
async def test_submission_stream_completion_and_historical_isolation(local_browser):
    response = await local_browser.send("Return one final JSON object")
    assert "Complete response" in response
    assert "historical" not in response
    assert "Copy" not in response
    assert await local_browser.page.evaluate("window.sentCount") == 1


@pytest.mark.browser
async def test_multiturn_binding(local_browser):
    await local_browser.send("First turn")
    response = await local_browser.send("Second turn")
    assert "Complete response" in response
    assert await local_browser.page.evaluate("window.sentCount") == 2


@pytest.mark.browser
async def test_timeout_never_executes_partial_or_resends(local_browser):
    await local_browser.page.evaluate("() => { window.send = () => { window.sentCount++; }; }")
    with pytest.raises(ProviderError, match="Timed out"):
        await local_browser.send("Slow response")
    assert await local_browser.page.evaluate("window.sentCount") == 1
    with pytest.raises(ProviderError, match="unknown outcome"):
        await local_browser.send("Retry")
    assert await local_browser.page.evaluate("window.sentCount") == 1


@pytest.mark.browser
async def test_composer_is_not_proof_of_authentication(local_browser):
    await local_browser.page.locator('[aria-label="Account"]').evaluate("e => e.remove()")
    assert (await local_browser.status())["authenticated"] is False


@pytest.mark.browser
async def test_cancellation_during_generation(local_browser):
    await local_browser.page.evaluate("() => { window.send = () => { window.sentCount++; }; }")
    task = asyncio.create_task(local_browser.send("Cancelled turn"))
    await asyncio.sleep(0.2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert local_browser.poisoned is True
