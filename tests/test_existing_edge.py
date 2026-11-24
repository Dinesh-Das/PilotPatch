"""Real MV3 extension + local broker + public DOM fixtures. No Microsoft traffic/account."""

import asyncio
import itertools
import json
from pathlib import Path

import pytest
from playwright.async_api import async_playwright

from pilotpatch.browser.bridge import Bridge, pairing
from pilotpatch.config import Config
from pilotpatch.providers.base import ProviderError
from pilotpatch.providers.existing_edge import CopilotExistingEdge

EXTENSION = Path(__file__).resolve().parents[1] / "editors" / "edge"

FIXTURE = """<!doctype html><html><body>
<button aria-label="Account">Fixture account</button>
<div data-content="user-message">old prompt</div>
<div data-content="ai-message"><pre>old answer</pre>
<button aria-label="Copy message">Copy</button></div>
<textarea></textarea><button aria-label="Send message" onclick="send()">Send</button>
<script>
window.sentCount = 0;
function send() {
  window.sentCount++;
  const user = document.createElement('div'); user.dataset.content='user-message';
  user.textContent=document.querySelector('textarea').value; document.body.append(user);
  document.querySelector('textarea').value='';
  const assistant=document.createElement('div'); assistant.dataset.content='ai-message';
  assistant.innerHTML='<pre>partial</pre>'; document.body.append(assistant);
  setTimeout(() => { assistant.innerHTML='<pre>Complete fixture answer</pre>' +
    '<button aria-label="Copy message">Copy</button>'; }, 100);
}
</script></body></html>"""


@pytest.fixture
async def connected_edge(tmp_path):
    home = tmp_path / "private-state"
    pair = pairing(home, create=True)
    config = Config(
        edge_connect_timeout=10, stable_seconds=0.1, poll_seconds=0.05, response_timeout=5
    )
    provider = CopilotExistingEdge(home, config)
    provider.bridge = Bridge(home, port=0)
    async with async_playwright() as playwright:
        context = await playwright.chromium.launch_persistent_context(
            str(tmp_path / "test-only-profile"),
            channel="chromium",
            headless=True,
            chromium_sandbox=True,
            args=[f"--disable-extensions-except={EXTENSION}", f"--load-extension={EXTENSION}"],
        )
        await context.route(
            "https://**/*", lambda route: route.fulfill(body=FIXTURE, content_type="text/html")
        )
        page = await context.new_page()
        await page.goto("https://copilot.com/chat")
        worker = (
            context.service_workers[0]
            if context.service_workers
            else (await context.wait_for_event("serviceworker"))
        )
        assert worker.url.startswith(f"chrome-extension://{pair['extension_id']}/")
        opening = asyncio.create_task(provider.open())
        try:
            for _ in range(100):
                if provider.bridge.port:
                    break
                await asyncio.sleep(0.01)
            await worker.evaluate(
                """async pair => {
                await chrome.storage.local.setAccessLevel({accessLevel:'TRUSTED_CONTEXTS'});
                const tabs = await chrome.tabs.query({url:'https://copilot.com/*'});
                await chrome.storage.local.set({pair,client:'fixture-client'});
                await chrome.storage.session.set({
                  tabId:tabs[0].id,selection:'fixture-selection',selectedClient:'fixture-client'
                });
                void pump();
            }""",
                dict(pair, port=provider.bridge.port),
            )
            await opening
            yield provider, page, worker
        finally:
            if not opening.done():
                opening.cancel()
            await asyncio.gather(opening, return_exceptions=True)
            await provider.close()
            assert not page.is_closed()  # Closing PilotPatch leaves the selected tab open.
            await context.close()


@pytest.mark.browser
async def test_existing_tab_round_trip_and_multiple_turns(connected_edge):
    provider, page, _ = connected_edge
    assert (await provider.status())["authenticated"]
    assert await provider.send("First fixture request") == "Complete fixture answer"
    assert await provider.send("Second fixture request") == "Complete fixture answer"
    assert await page.evaluate("window.sentCount") == 2


@pytest.mark.browser
async def test_personal_account_control_in_copilot_navigation(connected_edge):
    provider, page, _ = connected_edge
    await page.get_by_role("button", name="Account", exact=True).evaluate("""element => {
      element.outerHTML = '<nav aria-label="Copilot navigation">' +
        '<div role="button" aria-label="Fixture User, Personal account">FU</div></nav>';
    }""")
    status = await provider.status()
    assert status["authenticated"] and status["chat_ready"]
    assert status["account_control_count"] == 1

    await page.locator("nav").evaluate("element => element.removeAttribute('aria-label')")
    assert not (await provider.status())["authenticated"]

    await page.locator("nav").evaluate("""element => {
      element.setAttribute('aria-label', 'Copilot navigation');
      element.insertAdjacentHTML('beforeend', '<button>Sign in</button>');
    }""")
    status = await provider.status()
    assert status["state"] == "sign_in_required"
    assert not status["authenticated"]


@pytest.mark.browser
async def test_toolbar_popup_pairs_and_never_switches_tabs_on_its_own(connected_edge, tmp_path):
    provider, page, worker = connected_edge
    file = tmp_path / "popup-pairing.json"
    file.write_text(
        json.dumps(dict(pairing(provider.home), port=provider.bridge.port)), encoding="utf-8"
    )
    other = await page.context.new_page()
    await other.goto("https://copilot.com/chat?other")
    await page.bring_to_front()
    await worker.evaluate("chrome.action.openPopup()")
    cdp = await page.context.new_cdp_session(page)
    targets = (await cdp.send("Target.getTargets"))["targetInfos"]
    popup = next(item for item in targets if item["url"].endswith("/popup.html"))
    session = (await cdp.send("Target.attachToTarget", {"targetId": popup["targetId"]}))[
        "sessionId"
    ]
    request_ids = itertools.count(1)

    async def call(method, **params):
        response = asyncio.get_running_loop().create_future()
        identifier = next(request_ids)

        def received(event):
            data = json.loads(event["message"])
            if event["sessionId"] == session and data.get("id") == identifier:
                response.set_result(data)

        cdp.on("Target.receivedMessageFromTarget", received)
        try:
            message = json.dumps({"id": identifier, "method": method, "params": params})
            await cdp.send("Target.sendMessageToTarget", {"sessionId": session, "message": message})
            return (await asyncio.wait_for(response, 5))["result"]
        finally:
            cdp.remove_listener("Target.receivedMessageFromTarget", received)

    async def evaluate(expression):
        result = await call("Runtime.evaluate", expression=expression, returnByValue=True)
        return result["result"].get("value")

    async def wait_for(expression):
        for _ in range(100):
            if await evaluate(expression):
                return
            await asyncio.sleep(0.05)
        pytest.fail(f"Popup state did not match: {expression}")

    try:
        await wait_for("!document.querySelector('#disconnect').hidden")
        await evaluate("document.querySelector('#disconnect').click()")
        await wait_for("!document.querySelector('#pair-step').hidden")
        document = await call("DOM.getDocument")
        node = await call("DOM.querySelector", nodeId=document["root"]["nodeId"], selector="#pair")
        await call("DOM.setFileInputFiles", nodeId=node["nodeId"], files=[str(file)])
        await wait_for("!document.querySelector('#tab-step').hidden")
        assert await evaluate("!document.querySelector('#choose').hidden")
        assert await evaluate("document.querySelector('#connect').disabled")
        await other.close()
        await wait_for("document.querySelector('#choose').hidden")
        assert await evaluate("!document.querySelector('#connect').disabled")
        selected = "async () => (await chrome.storage.session.get('tabId')).tabId"
        assert not await worker.evaluate(selected)
        await evaluate("document.querySelector('#connect').click()")
        await wait_for("document.querySelector('#status').textContent === 'Tab selected'")
        chosen = await worker.evaluate(selected)
        assert isinstance(chosen, int)
    finally:
        await cdp.send("Target.detachFromTarget", {"sessionId": session})


@pytest.mark.browser
async def test_content_script_cannot_read_private_pairing(connected_edge):
    _, _, worker = connected_edge
    denied = await worker.evaluate("""async () => {
      const {tabId} = await chrome.storage.session.get('tabId');
      const results = await chrome.scripting.executeScript({target:{tabId},
        world:'ISOLATED', func:async () => {
          try { const value=await chrome.storage.local.get('pair'); return !value.pair; }
          catch { return true; }
        }});
      return results[0].result;
    }""")
    assert denied is True


@pytest.mark.browser
async def test_send_control_can_appear_only_after_typing(connected_edge):
    provider, page, _ = connected_edge
    await page.locator('[aria-label="Send message"]').evaluate(
        "e => {e.style.display='none'; document.querySelector('textarea').addEventListener("
        "'input', () => {e.style.display='';});}"
    )
    assert await provider.send("Button appears after input") == "Complete fixture answer"
    assert await page.evaluate("window.sentCount") == 1


@pytest.mark.browser
async def test_existing_draft_is_preserved_and_never_submitted(connected_edge):
    provider, page, _ = connected_edge
    await page.locator("textarea").fill("User's unsent draft")
    with pytest.raises(ProviderError):
        await provider.send("Task")
    assert await page.locator("textarea").input_value() == "User's unsent draft"
    assert await page.evaluate("window.sentCount") == 0
    with pytest.raises(ProviderError, match="unknown outcome"):
        await provider.send("Retry")


@pytest.mark.browser
async def test_service_error_and_guest_are_not_ready(connected_edge):
    provider, page, _ = connected_edge
    await page.locator("body").evaluate(
        "e => e.insertAdjacentHTML('beforeend', '<p role=alert>Error</p>')"
    )
    status = await provider.status()
    assert status["authenticated"] and not status["chat_ready"]
    assert (await provider.login())["state"] == "service_error"
    with pytest.raises(ProviderError, match="service error"):
        await provider.send("Must not submit")
    assert await page.evaluate("window.sentCount") == 0
    await page.locator("[role=alert]").evaluate("e => e.remove()")
    await page.locator("body").evaluate(
        "e => e.insertAdjacentHTML('beforeend', '<button>Sign in</button>')"
    )
    assert not (await provider.status())["authenticated"]


@pytest.mark.browser
async def test_navigation_loses_turn_and_never_resubmits(connected_edge):
    provider, page, _ = connected_edge
    await page.evaluate("() => {window.send = () => {window.sentCount++};}")
    assert await page.evaluate("window.sentCount") == 0
    task = asyncio.create_task(provider.send("Interrupted turn"))
    await page.wait_for_function("window.sentCount === 1")
    await page.reload()
    with pytest.raises(ProviderError):
        await task
    with pytest.raises(ProviderError, match="unknown outcome"):
        await provider.send("No replay")
    assert await page.evaluate("window.sentCount") == 0


@pytest.mark.browser
async def test_intervening_user_turn_is_never_accepted_as_agent_response(connected_edge):
    provider, page, _ = connected_edge
    await page.evaluate("""() => {window.send = () => {
      const marked=document.createElement('div'); marked.dataset.content='user-message';
      marked.textContent=document.querySelector('textarea').value; document.body.append(marked);
      document.body.insertAdjacentHTML('beforeend', '<div data-content="user-message">Other</div>' +
        '<div data-content="ai-message"><pre>Wrong</pre>' +
        '<button aria-label="Copy message">Copy</button></div>');
    };} """)
    with pytest.raises(ProviderError, match="ambiguous"):
        await provider.send("Agent request")
    assert provider.poisoned


@pytest.mark.browser
async def test_tab_reselection_stops_old_pump_and_is_not_persisted_across_restart(connected_edge):
    provider, page, worker = connected_edge
    other = await page.context.new_page()
    await other.goto("https://copilot.com/chat?other")
    await worker.evaluate("""async () => {
      const tabs=await chrome.tabs.query({url:'https://copilot.com/*'});
      const other=tabs.find(tab => tab.url.includes('?other'));
      await chrome.storage.session.set({tabId:other.id,selection:'new-selection'});
    }""")
    assert await worker.evaluate(
        "(async () => !('tabId' in await chrome.storage.local.get(null)))()"
    )
    with pytest.raises(ProviderError):
        await provider.bridge.call("submit", {}, wait_seconds=2)
    assert await page.evaluate("window.sentCount") == 0
    assert await other.evaluate("window.sentCount") == 0


@pytest.mark.browser
async def test_untrusted_local_listener_never_receives_pairing_secret(connected_edge):
    provider, _, worker = connected_edge
    captured = []

    async def impostor(reader, writer):
        head = await reader.readuntil(b"\r\n\r\n")
        length = next(
            int(line.split(b":", 1)[1])
            for line in head.split(b"\r\n")
            if line.lower().startswith(b"content-length:")
        )
        captured.append(head + await reader.readexactly(length))
        body = b'{"session":"forged"}'
        writer.write(
            b"HTTP/1.1 200 OK\r\nContent-Length: "
            + str(len(body)).encode()
            + b"\r\nConnection: close\r\n\r\n"
            + body
        )
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    # Replace the real listener after an authenticated session has been established.
    port = provider.bridge.port
    await provider.close()
    server = await asyncio.start_server(impostor, "127.0.0.1", port)
    try:
        rejected = await worker.evaluate(
            """async port => {
          const {pair}=await chrome.storage.local.get('pair');
          const auth={key:await PilotPatchConnection.key(pair.token)};
          try {await post({...pair,port},auth,'/hello',{}); return false;}
          catch {return true;}
        }""",
            port,
        )
        assert rejected
        rejected_result = await worker.evaluate(
            """async ({port,session}) => {
          const {pair}=await chrome.storage.local.get('pair');
          const auth={key:await PilotPatchConnection.key(pair.token),session};
          auth.encryptionKey=await PilotPatchConnection.encryptionKey(auth.key,session);
          try {await post({...pair,port},auth,'/result',
            {result:{text:'PRIVATE_FIXTURE_ANSWER'}}); return false;}
          catch {return true;}
        }""",
            {"port": port, "session": provider.bridge.session},
        )
        assert rejected_result
        assert captured and all(provider.bridge.token.encode() not in data for data in captured)
        assert all(b"PRIVATE_FIXTURE_ANSWER" not in data for data in captured)
    finally:
        server.close()
        await server.wait_closed()
