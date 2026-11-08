/* Only this trusted extension context holds the pairing token. No page-origin relay. */
"use strict";
importScripts("connection.js");
let running = false;
let wakeRequested = false;
const ready = chrome.storage.local.setAccessLevel({accessLevel: "TRUSTED_CONTEXTS"});

async function post(pair, auth, path, body) {
  const nonce = PilotPatchConnection.hex(crypto.getRandomValues(new Uint8Array(32)));
  let raw = JSON.stringify(body);
  if (path !== "/hello") raw = await PilotPatchConnection.encrypt(auth.encryptionKey, raw,
    `request\n${auth.session}\n${path}\n${nonce}`);
  const headers = {"Content-Type": "application/json", "X-PilotPatch-Nonce": nonce};
  if (path !== "/hello") headers["X-PilotPatch-Mac"] = await PilotPatchConnection.sign(
    auth.key, `request\n${auth.session}\n${path}\n${nonce}\n${raw}`);
  const response = await fetch(`http://127.0.0.1:${pair.port}${path}`, {
    method: "POST", headers,
    body: raw, credentials: "omit", cache: "no-store",
    redirect: "error", signal: AbortSignal.timeout(5000)
  });
  const text = await PilotPatchConnection.readBounded(response);
  if (!await PilotPatchConnection.verify(auth.key,
      `response\n${nonce}\n${response.status}\n${text}`, response.headers.get("X-PilotPatch-Mac"))) {
    throw new Error("listener_not_authenticated");
  }
  if (!response.ok) throw new Error("bridge_rejected");
  return JSON.parse(path === "/hello" ? text : await PilotPatchConnection.decrypt(auth.encryptionKey,
    text, `response\n${auth.session}\n${path}\n${nonce}`));
}

async function operate(tabId, command, selected, authorizeCommit) {
  const tab = await chrome.tabs.get(tabId);
  if (!PilotPatchConnection.isCopilot(tab.url)) {
    if (command.action === "status") return {
      authenticated: false, chat_ready: false, state: "manual_authentication_required",
      composer_count: 0, account_control_count: 0, account: "unavailable"
    };
    throw new Error("selected_tab_left_copilot");
  }
  // Packaged code in an isolated world; never execute strings supplied by the CLI/page.
  const injected = await chrome.scripting.executeScript({
    target: {tabId}, files: ["content.js"], world: "ISOLATED"
  });
  const documentId = injected.find(frame => frame.frameId === 0)?.documentId;
  if (!documentId) throw new Error("selected_document_missing");
  const send = phase => chrome.tabs.sendMessage(tabId,
    {type: "pilotpatch-command-v2", command, phase}, {documentId});
  await selected(); // Injection itself can outlive revocation; do not even prepare afterward.
  let result = await send(command.action === "submit" ? "prepare" : "read");
  if (command.action === "submit" && !result?.failure) {
    if (result?.prepared !== true) throw new Error("prepare_failed");
    // React can update asynchronously after input. There is no delayed click in the
    // content script: the worker revalidates authority before committing this document.
    await new Promise(resolve => setTimeout(resolve, 100));
    await selected();
    await authorizeCommit();
    await selected();
    result = await send("commit");
  }
  if (result?.failure) throw new Error(result.failure);
  return result;
}

async function pump() {
  if (running) return;
  running = true;
  try {
    await ready;
    const {pair, client} = await chrome.storage.local.get(["pair", "client"]);
    const {tabId, selection} = await chrome.storage.session.get(["tabId", "selection"]);
    if (!pair || !client || !selection || !Number.isInteger(tabId)) return;
    const identity = {client: `${client}:${selection}`, tab: tabId, protocol: 2};
    const auth = {key: await PilotPatchConnection.key(pair.token)};
    const hello = await post(pair, auth, "/hello", {});
    if (hello.protocol !== 2) throw new Error("backend_upgrade_required");
    auth.session = hello.session;
    if (!/^[a-f0-9]{64}$/.test(auth.session)) throw new Error("invalid_session");
    auth.encryptionKey = await PilotPatchConnection.encryptionKey(auth.key, auth.session);
    const selected = async () => {
      const [current, authority] = await Promise.all([
        chrome.storage.session.get(["tabId", "selection"]),
        chrome.storage.local.get(["pair", "client"])
      ]);
      if (current.tabId !== tabId || current.selection !== selection
          || authority.client !== client || authority.pair?.token !== pair.token
          || authority.pair?.port !== pair.port || authority.pair?.extension_id !== pair.extension_id
          || authority.pair?.version !== pair.version) {
        throw new Error("selection_changed");
      }
    };
    for (;;) {
      await selected();
      const command = await post(pair, auth, "/next", identity);
      await chrome.action.setBadgeText({text: "ON"});
      if (!command.id) {
        await new Promise(resolve => setTimeout(resolve, 750));
        continue;
      }
      let result;
      try {
        await selected();
        result = {result: await operate(tabId, command, selected, async () => {
          const grant = await post(pair, auth, "/commit", {...identity, id: command.id});
          if (grant.authorized !== true) throw new Error("commit_not_authorized");
        })};
      } catch (error) {
        const codes = new Set(["composer_has_draft", "send_control_not_unique", "send_disabled",
          "turn_lost", "not_ready", "selected_tab_left_copilot"]);
        result = {error: codes.has(error.message) ? error.message : "selected_tab_action_failed"};
      }
      // A failed result delivery is never retried, especially after submit.
      await selected();
      await post(pair, auth, "/result", {...identity, id: command.id, ...result});
    }
  } catch {
    await chrome.action.setBadgeText({text: ""});
  } finally {
    running = false;
    if (wakeRequested) { wakeRequested = false; void pump(); }
  }
}

chrome.runtime.onInstalled.addListener(() => {
  chrome.alarms.create("pilotpatch-connect", {periodInMinutes: 0.5});
  void pump();
});
chrome.runtime.onStartup.addListener(() => {
  chrome.alarms.create("pilotpatch-connect", {periodInMinutes: 0.5});
  void pump();
});
chrome.alarms.onAlarm.addListener(alarm => {
  if (alarm.name === "pilotpatch-connect") void pump();
});
chrome.runtime.onMessage.addListener((message, sender, reply) => {
  // A content script or website must never reconfigure pairing or select a tab.
  if (sender.id !== chrome.runtime.id || sender.tab
      || sender.url !== chrome.runtime.getURL("popup.html")) return false;
  if (message?.type === "wake") {
    wakeRequested = running;
    void pump();
    reply({ok: true});
  }
  return false;
});
chrome.storage.onChanged.addListener((changes, area) => {
  const pairChanged = changes.pair?.oldValue
    && JSON.stringify(changes.pair.oldValue) !== JSON.stringify(changes.pair.newValue);
  const clientChanged = changes.client?.oldValue && changes.client.oldValue !== changes.client.newValue;
  if (area === "local" && (pairChanged || clientChanged)) {
    // Replacing/removing authority revokes the existing selection. Initial pairing
    // has no previous authority and still requires the user to select a tab.
    void chrome.storage.session.clear();
  }
  if (area === "session") { wakeRequested = running; void pump(); }
});
void pump();
