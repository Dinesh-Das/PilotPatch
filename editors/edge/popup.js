"use strict";
const $ = id => document.getElementById(id);
async function listTabs() {
  const {tabId} = await chrome.storage.session.get("tabId");
  const tabs = await chrome.tabs.query({url: ["https://copilot.com/*", "https://copilot.microsoft.com/*", "https://copilot.ai/*"]});
  $("tabs").replaceChildren(new Option("Choose a Copilot tab", ""));
  for (const tab of tabs.filter(tab => PilotPatchConnection.isCopilot(tab.url))) {
    $("tabs").add(new Option(`${tab.title || "Copilot"} — tab ${tab.id}`, String(tab.id)));
  }
  $("tabs").value = String(tabId ?? "");
  if (!tabs.length) $("status").textContent = "Open Copilot in this Edge profile, then refresh this list.";
}
async function init() {
  await chrome.storage.local.setAccessLevel({accessLevel: "TRUSTED_CONTEXTS"});
  const {pair} = await chrome.storage.local.get("pair");
  $("paired").textContent = pair ? "This profile is paired." : "Select your pairing file to begin.";
  await listTabs();
}
$("pair").addEventListener("change", async () => {
  try {
    const file = $("pair").files[0];
    if (!file || file.size > 4096) throw new Error("Choose a valid PilotPatch pairing file.");
    const pair = PilotPatchConnection.validatePair(JSON.parse(await file.text()), chrome.runtime.id);
    await chrome.storage.session.clear();
    await chrome.storage.local.set({pair});
    $("paired").textContent = "This profile is paired. Choose your Copilot tab below.";
  } catch { $("paired").textContent = "Invalid pairing file. Run pilotpatch connect and select edge-pairing.json."; }
});
$("refresh").addEventListener("click", () => { void listTabs(); });
$("connect").addEventListener("click", async () => {
  try {
    const {pair, client} = await chrome.storage.local.get(["pair", "client"]);
    if (!pair) throw new Error("Pair this profile first.");
    if (!$("tabs").value) throw new Error("Choose an existing Copilot tab.");
    const tabId = Number($("tabs").value);
    const tab = await chrome.tabs.get(tabId);
    if (!PilotPatchConnection.isCopilot(tab.url)) throw new Error("The selected tab has left Copilot.");
    await chrome.storage.local.set({client: client || crypto.randomUUID()});
    await chrome.storage.session.set({tabId, selection: crypto.randomUUID()});
    await chrome.runtime.sendMessage({type: "wake"});
    $("status").textContent = "Tab selected. Run Sign in or Test connection in PilotPatch. Keep this tab open.";
  } catch (error) { $("status").textContent = error.message; }
});
$("disconnect").addEventListener("click", async () => {
  await chrome.storage.local.remove(["pair", "client", "tabId"]);
  await chrome.storage.session.clear();
  // Stopping the worker also stops any loop holding the old in-memory pairing.
  chrome.runtime.reload();
});
void init();
