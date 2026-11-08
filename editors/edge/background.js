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

async function operate(tabId, command) {
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
  const result = await chrome.tabs.sendMessage(tabId, {type: "pilotpatch-command", command}, {documentId});
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
    const identity = {client: `${client}:${selection}`, tab: tabId};
    const auth = {key: await PilotPatchConnection.key(pair.token)};
    auth.session = (await post(pair, auth, "/hello", {})).session;
    if (!/^[a-f0-9]{64}$/.test(auth.session)) throw new Error("invalid_session");
    auth.encryptionKey = await PilotPatchConnection.encryptionKey(auth.key, auth.session);
    const selected = async () => {
      const current = await chrome.storage.session.get(["tabId", "selection"]);
      if (current.tabId !== tabId || current.selection !== selection) throw new Error("selection_changed");
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
        result = {result: await operate(tabId, command)};
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
chrome.storage.onChanged.addListener((_, area) => {
  if (area === "session") { wakeRequested = running; void pump(); }
});
void pump();
