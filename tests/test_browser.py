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
<button aria-label="Copy message">Copy</button></div>
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
    assistant.insertAdjacentHTML('beforeend','<button aria-label="Copy message">Copy</button>');
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
        context = await browser.new_context()
        page = await context.new_page()
        # Route a fake origin to local HTML: no Microsoft request leaves this browser.
        await context.route(
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
async def test_intervening_user_turn_is_rejected(local_browser):
    await local_browser.page.evaluate("""() => {window.send = () => {
      const user=document.createElement('div'); user.dataset.content='user-message';
      user.textContent=document.querySelector('textarea').value; document.body.append(user);
      document.body.insertAdjacentHTML('beforeend', '<div data-content="user-message">Other</div>' +
        '<div data-content="ai-message"><pre>Wrong</pre>' +
        '<button aria-label="Copy message">Copy</button></div>');
    };} """)
    with pytest.raises(ProviderError, match="Ambiguous"):
        await local_browser.send("Agent request")


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


@pytest.mark.browser
async def test_login_recognizes_case_insensitive_profile_and_labelled_editor(local_browser):
    page = local_browser.page
    await page.set_content(
        '<button aria-label="Open profile menu">Avatar</button>'
        '<div contenteditable="true" aria-label="Message Copilot"></div>'
    )
    status = await local_browser.login(wait_seconds=0.1)
    assert status["authenticated"] is True
    assert status["chat_ready"] is True
    assert status["connection_verified"] is False


@pytest.mark.browser
async def test_sign_in_control_prevents_guest_profile_false_positive(local_browser):
    await local_browser.page.set_content(
        '<button aria-label="Profile">Guest</button>'
        '<button aria-label="Sign In">Sign In</button><textarea></textarea>'
    )
    status = await local_browser.status()
    assert status["authenticated"] is False
    assert status["state"] == "sign_in_required"


@pytest.mark.browser
async def test_login_adopts_authenticated_chat_tab_in_its_own_context(local_browser):
    original = local_browser.page
    await original.set_content('<button aria-label="Sign In">Sign in</button>')
    local_browser.session.context = original.context
    chat = await original.context.new_page()
    await chat.goto("https://copilot.microsoft.com/chat")
    status = await local_browser.login(wait_seconds=0.1)
    assert status["authenticated"] is True
    assert local_browser.page is chat
    assert original.is_closed() is False


@pytest.mark.browser
async def test_multiple_new_chat_tabs_are_not_silently_selected(local_browser):
    original = local_browser.page
    await original.set_content('<button aria-label="Sign In">Sign in</button>')
    local_browser.session.context = original.context
    for _ in range(2):
        page = await original.context.new_page()
        await page.goto("https://copilot.microsoft.com/chat")
    status = await local_browser.status()
    assert status["state"] == "multiple_copilot_tabs"
    assert status["authenticated"] is False
    assert local_browser.page is original


@pytest.mark.browser
async def test_signed_in_service_error_is_distinct_from_login_and_blocks_sending(local_browser):
    await local_browser.page.locator("body").evaluate("""element => element.insertAdjacentHTML(
      'beforeend', '<div role="alert">Your request could not be completed.</div>')""")
    status = await local_browser.login(wait_seconds=0.1)
    assert status["authenticated"] is True
    assert status["state"] == "service_error"
    assert status["chat_ready"] is False
    with pytest.raises(ProviderError, match="signed in.*service error"):
        await local_browser.send("Do not submit this")
    assert await local_browser.page.evaluate("window.sentCount") == 0


@pytest.mark.browser
async def test_login_reports_which_control_is_missing(local_browser):
    await local_browser.page.locator('[aria-label="Account"]').evaluate(
        "element => element.remove()"
    )
    updates = []
    with pytest.raises(ProviderError, match="account control"):
        await local_browser.login(wait_seconds=0.05, on_status=updates.append)
    assert updates[0]["state"] == "account_control_not_recognized"
    assert updates[0]["composer_count"] == 1


@pytest.mark.browser
async def test_signed_in_without_chat_input_returns_login_result_instead_of_waiting(local_browser):
    await local_browser.page.locator("textarea").evaluate("element => element.remove()")
    status = await local_browser.login(wait_seconds=0.1)
    assert status["authenticated"] is True
    assert status["chat_ready"] is False
    assert status["state"] == "chat_input_not_recognized"


@pytest.mark.browser
async def test_service_error_before_assistant_binds_does_not_wait_for_timeout(local_browser):
    await local_browser.page.evaluate("""() => { window.send = () => {
      window.sentCount++;
      document.body.insertAdjacentHTML('beforeend', '<div role="alert">Request failed</div>');
    }; }""")
    with pytest.raises(ProviderError, match="Copilot displayed an error"):
        await local_browser.send("Harmless test")
    assert await local_browser.page.evaluate("window.sentCount") == 1


@pytest.mark.browser
async def test_visible_sign_out_menu_confirms_account_without_legacy_profile_label(local_browser):
    await local_browser.page.set_content(
        '<button aria-label="Settings">Avatar</button>'
        '<div role="menu"><button role="menuitem">Sign out</button></div>'
        "<textarea></textarea>"
    )
    status = await local_browser.login(wait_seconds=0.1)
    assert status["authenticated"] is True
    assert status["chat_ready"] is True


@pytest.mark.browser
async def test_send_readiness_waits_for_client_rendered_chat_controls(local_browser):
    await local_browser.page.set_content(
        "<div>Loading Copilot…</div><script>"
        "setTimeout(() => { document.body.innerHTML = "
        "'<button aria-label=\"Account\">Avatar</button><textarea></textarea>'; }, 250);"
        "</script>"
    )
    await local_browser._check_ready()
    assert (await local_browser.status())["chat_ready"] is True


@pytest.mark.browser
async def test_unknown_account_with_visible_request_error_does_not_wait_for_sign_in(local_browser):
    await local_browser.page.set_content(
        '<textarea></textarea><div role="alert">Request failed</div>'
    )
    status = await local_browser.status()
    assert status["authenticated"] is False
    assert status["state"] == "service_error"
    with pytest.raises(ProviderError, match="service error before sign-in could be verified"):
        await local_browser.login(wait_seconds=0.1)


@pytest.mark.browser
async def test_account_before_chat_input_waits_for_hydration(local_browser):
    await local_browser.page.set_content(
        '<button aria-label="Account">Avatar</button><script>'
        "setTimeout(() => document.body.insertAdjacentHTML("
        '"beforeend", "<textarea></textarea>"), 250);'
        "</script>"
    )
    await local_browser._check_ready()
    assert (await local_browser.status())["chat_ready"] is True


@pytest.mark.browser
async def test_active_conversation_never_switches_to_another_authenticated_chat(local_browser):
    original = local_browser.page
    local_browser.session.context = original.context
    local_browser.conversation_url = original.url
    await original.set_content('<button aria-label="Sign In">Sign in</button>')
    other = await original.context.new_page()
    await other.goto("https://copilot.microsoft.com/chat")
    status = await local_browser.status()
    assert status["authenticated"] is False
    assert local_browser.page is original
