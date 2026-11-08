"""Local Edge checks for the extension's packaged webview. No model requests."""

import asyncio
import subprocess
from pathlib import Path

import pytest
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]
EXTENSION = ROOT / "editors/vscode"


@pytest.fixture
async def editor_panel():
    renderer = """
const {renderPanel}=require('./src/panel');
const webview={cspSource:'https://pilotpatch.test',asWebviewUri:value=>value};
const Uri={joinPath:(_,directory,name)=>'https://pilotpatch.test/'+name};
process.stdout.write(renderPanel(webview,'extension',Uri));
"""
    rendered = (
        await asyncio.to_thread(
            subprocess.run,
            ["node", "-e", renderer],
            cwd=EXTENSION,
            check=True,
            capture_output=True,
            encoding="utf-8",
        )
    ).stdout
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(
            channel="msedge", headless=True, chromium_sandbox=True
        )
        page = await browser.new_page(viewport={"width": 360, "height": 1100})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        await page.add_init_script("""
window.panelMessages=[];
window.acquireVsCodeApi=()=>({getState:()=>null,setState:value=>{window.draft=value;},
postMessage:value=>window.panelMessages.push(value)});
""")

        async def route(request):
            name = request.request.url.rsplit("/", 1)[-1]
            if name in {"panel.css", "panel.js"}:
                await request.fulfill(
                    body=(EXTENSION / "media" / name).read_text(encoding="utf-8"),
                    content_type="text/css" if name.endswith("css") else "text/javascript",
                )
            else:
                await request.fulfill(body=rendered, content_type="text/html")

        await page.route("https://pilotpatch.test/**", route)
        await page.goto("https://pilotpatch.test/")
        yield page, errors
        assert not errors
        await browser.close()


async def publish(page, **overrides):
    state = dict(
        type="state",
        phase="idle",
        message="Ready when you are.",
        busy=False,
        workspace="Sample project",
        project="C:\\Work\\Sample project",
        configured=True,
        trusted=True,
        remote=False,
        activity=[],
    )
    state.update(overrides)
    await page.evaluate("value => window.postMessage(value, '*')", state)
    await page.wait_for_timeout(50)


@pytest.mark.browser
async def test_panel_empty_setup_then_keyboard_submission(editor_panel):
    page, _ = editor_panel
    assert await page.get_by_role("button", name="Run task").is_disabled()
    await publish(page)
    task = 'Fix "login"; $(whoami) & echo x\nAdd tests.'
    await page.get_by_label("What would you like to change?").fill(task)
    await page.get_by_label("Permissions").select_option("read-only")
    await page.get_by_label("Preview only").check()
    await page.get_by_label("What would you like to change?").press("Control+Enter")
    message = await page.evaluate("window.panelMessages.at(-1)")
    assert message == dict(type="run", prompt=task, mode="read-only", dryRun=True)
    assert await page.get_by_role("button", name="Run task").is_disabled()


@pytest.mark.browser
async def test_panel_safe_text_running_stop_and_error_states(editor_panel):
    page, _ = editor_panel
    await publish(page)
    await page.get_by_role("button", name="Connect existing Edge").click()
    assert await page.evaluate("window.panelMessages.at(-1)") == {"type": "connect"}
    await publish(page, workspace='<img src=x onerror="alert(1)">')
    assert await page.locator("#workspace-name").inner_text() == '<img src=x onerror="alert(1)">'
    assert await page.locator("#workspace-name img").count() == 0
    await publish(page, phase="running", busy=True, message="Review approvals in terminal.")
    assert await page.get_by_role("button", name="Run task").is_disabled()
    await page.get_by_role("button", name="Stop task").click()
    assert await page.evaluate("window.panelMessages.at(-1)") == {"type": "stop"}
    await publish(page, phase="error", message="Backend Python was not found.")
    assert "Backend Python" in await page.get_by_role("status").inner_text()


@pytest.mark.browser
async def test_panel_responsive_layout_and_screenshot(editor_panel):
    page, _ = editor_panel
    await publish(page)
    await page.get_by_label("What would you like to change?").fill(
        "Add a health-check endpoint and cover it with tests."
    )
    for width in [320, 768, 1024, 1440]:
        await page.set_viewport_size({"width": width, "height": 1100})
        assert await page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    await page.set_viewport_size({"width": 360, "height": 1100})
    (ROOT / "artifacts").mkdir(exist_ok=True)
    await page.screenshot(path=str(ROOT / "artifacts/pilotpatch-panel.png"), full_page=True)
