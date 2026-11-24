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
    assert not await page.get_by_role("button", name="Send", exact=True).is_visible()
    await publish(page)
    task = 'Fix "login"; $(whoami) & echo x\nAdd tests.'
    await page.get_by_label("Ask a question or request a change").fill(task)
    await page.get_by_text("Permissions and preview", exact=True).click()
    await page.get_by_label("Permissions").select_option("read-only")
    await page.get_by_label("Preview only").check()
    await page.get_by_label("Ask a question or request a change").press("Control+Enter")
    message = await page.evaluate("window.panelMessages.at(-1)")
    assert message == dict(type="chat", prompt=task, mode="read-only", dryRun=True)
    assert await page.get_by_role("button", name="Send", exact=True).is_disabled()


@pytest.mark.browser
async def test_panel_safe_text_running_stop_and_error_states(editor_panel):
    page, _ = editor_panel
    await publish(page)
    await page.get_by_role("button", name="Open Edge setup").click()
    assert await page.evaluate("window.panelMessages.at(-1)") == {"type": "edge-setup"}
    await publish(page, workspace='<img src=x onerror="alert(1)">')
    assert await page.locator("#workspace-name").inner_text() == '<img src=x onerror="alert(1)">'
    assert await page.locator("#workspace-name img").count() == 0
    await publish(page, phase="running", busy=True, message="Review approvals in terminal.")
    assert await page.get_by_role("button", name="Send", exact=True).is_disabled()
    await page.get_by_role("button", name="Stop", exact=True).click()
    assert await page.evaluate("window.panelMessages.at(-1)") == {"type": "stop"}
    await publish(page, phase="error", message="Backend Python was not found.")
    assert "Backend Python" in await page.get_by_role("status").inner_text()


@pytest.mark.browser
async def test_panel_guides_first_setup_and_hides_steps_after_verified_reply(editor_panel):
    page, _ = editor_panel
    await publish(page, project="", workspace="", configured=False)
    assert await page.get_by_role("button", name="Open folder").is_visible()
    await publish(page, configured=False)
    assert await page.get_by_role("button", name="Select installed Python").is_visible()
    await publish(page, prepared=True)
    await page.get_by_role("button", name="Copy pairing file path").click()
    assert await page.evaluate("window.panelMessages.at(-1)") == {"type": "copy-pairing"}
    assert await page.get_by_role("button", name="Test connection").is_visible()
    await publish(page, prepared=True, verified=True)
    assert not await page.get_by_role("button", name="Copy pairing file path").is_visible()


@pytest.mark.browser
async def test_connection_test_explains_blocked_run_and_releases_preserved_draft(editor_panel):
    page, _ = editor_panel
    await publish(page)
    prompt = page.get_by_label("Ask a question or request a change")
    await prompt.fill("Give me an overview of the codebase")
    await publish(page, phase="running", busy=True, operation="probe")
    assert await page.get_by_role("button", name="Connection test running…").is_disabled()
    await page.get_by_role("button", name="Stop connection test").click()
    assert await page.evaluate("window.panelMessages.at(-1)") == {"type": "stop"}
    await publish(page, phase="finished", verified=True)
    assert await page.get_by_role("button", name="Send", exact=True).is_enabled()
    assert await prompt.input_value() == "Give me an overview of the codebase"


@pytest.mark.browser
async def test_panel_responsive_layout_and_screenshot(editor_panel):
    page, _ = editor_panel
    await publish(
        page,
        verified=True,
        chat=[
            dict(
                id="1",
                user="How does a new game start?",
                reply="## Starting a game\n- `app.py` loads the game settings.\n"
                "- `game.py` resets the board and waits for the first jump.",
            )
        ],
    )
    await page.get_by_label("Ask a question or request a change").fill("Where is gravity set?")
    for width in [320, 768, 1024, 1440]:
        await page.set_viewport_size({"width": width, "height": 1100})
        assert await page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    await page.set_viewport_size({"width": 360, "height": 1100})
    (ROOT / "artifacts").mkdir(exist_ok=True)
    await page.screenshot(path=str(ROOT / "artifacts/pilotpatch-panel.png"), full_page=True)


@pytest.mark.browser
async def test_conversation_shows_reply_and_requests_explicit_approval_in_panel(editor_panel):
    page, _ = editor_panel
    await publish(page, verified=True)
    prompt = page.get_by_label("Ask a question or request a change")
    await prompt.fill("How does the jump work?")
    await page.get_by_role("button", name="Send", exact=True).click()
    await publish(
        page,
        busy=True,
        operation="chat",
        verified=True,
        approval=dict(id="a" * 32, source=True, message="Share selected files?"),
    )
    assert await prompt.input_value() == "How does the jump work?"
    await page.get_by_role("button", name="Share and send").click()
    assert await page.evaluate("window.panelMessages.at(-1)") == dict(
        type="decision",
        id="a" * 32,
        approved=True,
    )
    turn = dict(id="1", user="How does the jump work?")
    await publish(page, chat=[turn], busy=True, verified=True, operation="chat")
    assert await prompt.input_value() == ""
    await publish(
        page, chat=[dict(turn, reply="## Jump\n- See `bird.py`.\n<img src=x>")], verified=True
    )
    log = page.get_by_role("log")
    assert await log.get_by_role("heading", name="Jump").is_visible()
    assert await log.locator("code").inner_text() == "bird.py"
    assert "<img src=x>" in await log.inner_text()
    assert await log.locator("img").count() == 0
    await prompt.fill("Where is gravity configured?")
    await prompt.press("Control+Enter")
    assert (await page.evaluate("window.panelMessages.at(-1)"))[
        "prompt"
    ] == "Where is gravity configured?"
