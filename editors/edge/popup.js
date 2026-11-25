"use strict";
const $ = id => document.getElementById(id);
const tabPatterns = ["copilot.com", "copilot.microsoft.com", "copilot.ai"].map(host => `https://${host}/*`);
const checkTime = new Intl.DateTimeFormat(undefined, {dateStyle: "medium", timeStyle: "short"});
let busy = false;
let renderId = 0;
let chosenId = "";
let profileClient;

async function render() {
  const id = ++renderId;
  const [{pair, client}, selection, tabs] = await Promise.all([
    chrome.storage.local.get(["pair", "client"]),
    chrome.storage.session.get(["tabId", "selection", "selectedClient", "connectedSelection", "verifiedProbe"]),
    chrome.tabs.query({url: tabPatterns})
  ]);
  if (id !== renderId) return;
  if (!pair || client !== profileClient) chosenId = "";
  profileClient = client;
  const eligible = tabs.filter(tab => PilotPatchConnection.isCopilot(tab.url));
  const selected = selection.selection && selection.selectedClient === client &&
    eligible.find(tab => tab.id === selection.tabId);
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
  const verified = selected && selection.verifiedProbe?.selection === selection.selection &&
    Number.isFinite(selection.verifiedProbe.at);
  $("status").textContent = !pair ? "Waiting for pairing file" :
    verified ? "Copilot reply verified" : connected ? "Edge linked to VS Code" :
      selected ? "Copilot tab selected" : eligible.length ? "Choose a Copilot tab" :
        "No Copilot chat open in this profile";
  $("tab-help").textContent = verified ?
    `Last successful test: ${checkTime.format(selection.verifiedProbe.at)}. Keep this tab open for PilotPatch.` :
    connected ? "The local link is working. VS Code shows the result of the Copilot reply test." :
      selected ? "Click Test connection in the PilotPatch panel in VS Code to verify a Copilot reply." :
      eligible.length === 1 ? `Use ${eligible[0].title || "the open Copilot tab"}, then return to VS Code.` :
        eligible.length ? "Choose the tab signed into the account you want to use." :
          "Open the Copilot website in this Edge profile and sign in.";
  $("connect").textContent = selected && String(selected.id) === $("tabs").value ?
    "Check connection" : "Use this tab";
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
void chrome.runtime.sendMessage({type: "wake"}).catch(() => {});
void update();
