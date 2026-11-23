"use strict";
const $ = id => document.getElementById(id);
const tabPatterns = ["copilot.com", "copilot.microsoft.com", "copilot.ai"].map(host => `https://${host}/*`);
let busy = false;
let renderId = 0;
let chosenId = "";
let profileClient;

async function render() {
  const id = ++renderId;
  const [{pair, client}, selection, tabs] = await Promise.all([
    chrome.storage.local.get(["pair", "client"]),
    chrome.storage.session.get(["tabId", "selection", "selectedClient", "connectedSelection"]),
    chrome.tabs.query({url: tabPatterns})
  ]);
  if (id !== renderId) return;
  if (!pair || client !== profileClient) chosenId = "";
  profileClient = client;
  const eligible = tabs.filter(tab => PilotPatchConnection.isCopilot(tab.url));
  const selected = eligible.find(tab => tab.id === selection.tabId && selection.selectedClient === client);
  $("tabs").replaceChildren(new Option("Choose a Copilot tab", ""));
  for (const [index, tab] of eligible.entries()) {
    const host = new URL(tab.url).hostname;
    $("tabs").add(new Option(`${tab.title || "Copilot"} · ${host} · ${index + 1}`, String(tab.id)));
  }
  if (eligible.some(tab => String(tab.id) === chosenId)) $("tabs").value = chosenId;
  else if (selected || eligible.length === 1) $("tabs").value = String((selected || eligible[0]).id);

  $("pair-step").hidden = Boolean(pair);
  $("tab-step").hidden = !pair;
  $("choose").hidden = eligible.length < 2;
  $("open").hidden = eligible.length > 0;
  $("connect").hidden = !eligible.length;
  $("disconnect").hidden = !pair;
  $("connect").disabled = busy || !$("tabs").value;
  $("pair").disabled = busy;
  $("disconnect").disabled = busy;
  const connected = selected && selection.connectedSelection === selection.selection;
  $("status").textContent = !pair ? "Waiting for pairing file" :
    connected ? "Connected to PilotPatch" : selected ? "Tab selected" :
      eligible.length ? "Choose the tab PilotPatch can use" : "Open Copilot to continue";
  $("tab-help").textContent = connected ? "You can return to VS Code. Keep this Copilot tab open." :
    selected ? "In VS Code, click Test connection. Edge may take up to 30 seconds to connect." :
      eligible.length === 1 ? `Use ${eligible[0].title || "the open Copilot tab"}, then return to VS Code.` :
        eligible.length ? "Choose the tab signed into the account you want to use." :
          "Sign in on the Copilot website, then open this extension again.";
  $("connect").textContent = selected && String(selected.id) === $("tabs").value ?
    "Reconnect" : "Use this tab";
}

async function update() {
  try { await render(); }
  catch { $("error").textContent = "PilotPatch could not read Edge settings. Reload the extension and try again."; }
}

async function act(getMessage) {
  if (busy) return;
  busy = true;
  $("error").textContent = "";
  $("pair").disabled = $("connect").disabled = $("disconnect").disabled = true;
  try {
    const reply = await chrome.runtime.sendMessage(await getMessage());
    if (!reply?.ok) throw new Error(reply?.error || "Reload the PilotPatch extension and try again.");
  } catch (error) { $("error").textContent = error.message; }
  finally {
    busy = false;
    await update();
  }
}

$("pair").addEventListener("change", () => {
  const file = $("pair").files[0];
  $("pair").value = "";
  if (!file) return;
  void act(async () => {
    try {
      if (file.size > 4096) throw new Error();
      const pair = PilotPatchConnection.validatePair(JSON.parse(await file.text()), chrome.runtime.id);
      return {type: "pair", pair};
    } catch {
      throw new Error("Choose edge-pairing.json from Set up Copilot in VS Code.");
    }
  });
});
$("tabs").addEventListener("change", () => {
  chosenId = $("tabs").value;
  void update();
});
$("connect").addEventListener("click", () => void act(() => ({
  type: "select", tabId: Number($("tabs").value)
})));
$("disconnect").addEventListener("click", () => void act(() => ({type: "disconnect"})));
chrome.tabs.onUpdated.addListener((_, change) => {
  if (change.url || change.title || change.status === "complete") void update();
});
chrome.tabs.onRemoved.addListener(update);
chrome.storage.onChanged.addListener(update);
void update();
