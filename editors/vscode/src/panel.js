'use strict';
const crypto = require('node:crypto');

function escapeAttribute(value) {
  return String(value).replace(/[&<>"']/g, character =>
    ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[character]));
}

function renderPanel(webview, extensionUri, Uri) {
  const nonce = crypto.randomBytes(24).toString('base64');
  const resource = name => escapeAttribute(webview.asWebviewUri(Uri.joinPath(extensionUri, 'media', name)));
  const source = escapeAttribute(webview.cspSource);
  return `<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src ${source}; script-src 'nonce-${nonce}'; img-src ${source}; connect-src 'none'; base-uri 'none'; form-action 'none';">
<link rel="stylesheet" href="${resource('panel.css')}"><title>PilotPatch</title></head>
<body>
<header class="masthead"><h1>PilotPatch</h1><p>Microsoft Copilot Web</p></header>
<main>
  <section class="workspace-section" aria-label="Target project">
    <strong id="workspace-name">Checking workspace…</strong>
    <p id="workspace-path" class="path"></p>
    <button id="workspace" class="text-button" hidden>Change project</button>
  </section>
  <section id="project-setup" class="setup" hidden>
    <p>Open the local folder you want PilotPatch to work in.</p>
    <button id="open-folder" class="primary">Open folder</button>
  </section>
  <section id="backend-setup" class="setup" hidden>
    <h2>Install the PilotPatch backend</h2>
    <p>Run <code>setup-windows.ps1</code> from your PilotPatch folder. If you installed it manually, select the Python executable in its <code>.venv</code> folder.</p>
    <button id="configure" class="secondary">Select installed Python</button>
  </section>
  <section id="connection" class="setup" aria-labelledby="setup-title" hidden>
    <h2 id="setup-title">Connect Copilot in Edge</h2>
    <p id="connect-intro">Open Edge Extensions and copy the folder you’ll select there. Already paired? Test your connection.</p>
    <button id="connect" class="primary">Open Edge setup</button>
    <ol class="setup-steps" id="edge-steps" hidden>
      <li>In your intended Edge profile, turn on <strong>Developer mode</strong> at <code>edge://extensions</code> and click <strong>Load unpacked</strong>. In the folder dialog, press <kbd>Ctrl+L</kbd>, paste the path, and press Enter. Click <strong>Select Folder</strong>. For an existing PilotPatch install, click <strong>Reload</strong> on its card.
        <button id="copy-extension" class="secondary">Copy extension folder path</button></li>
      <li>Open <strong>PilotPatch</strong> from Edge’s Extensions menu. If it asks for a pairing file, paste the file path in the picker. Open Copilot, sign in, and click <strong>Use this tab</strong> in PilotPatch.
        <button id="copy-pairing" class="secondary">Copy pairing file path</button></li>
    </ol>
    <button id="probe" class="secondary">Test connection</button>
    <p class="subtle">The test sends a short message with no project files. Managed Edge may block loading the extension.</p>
  </section>
  <section class="execution" aria-label="Execution status">
    <p id="status" role="status" aria-live="polite"></p>
    <p id="panel-error" role="alert" hidden></p>
    <button id="stop" type="button" class="secondary" hidden>Stop task</button>
  </section>
  <form id="task-form" hidden>
    <label for="prompt">What would you like to change?</label>
    <textarea id="prompt" rows="8" maxlength="16000" spellcheck="false" placeholder="Add a health-check endpoint and cover it with tests." aria-describedby="prompt-help"></textarea>
    <div class="composer-footer"><span id="prompt-help">Ctrl / ⌘ + Enter to run</span><span id="counter">0 / 16,000</span></div>
    <details class="task-options"><summary>Task options</summary><div class="options">
      <div class="mode"><label for="mode">Permissions</label><select id="mode">
        <option value="approve">Approve changes</option><option value="read-only">Read only</option>
        <option value="auto-edit">Auto-edit files</option></select></div>
      <label class="checkbox"><input id="dry-run" type="checkbox"> Preview only</label>
    </div>
    <p id="mode-note" class="subtle">Review edits and approve commands in the terminal.</p></details>
    <button id="run" type="submit" class="primary">Run task</button>
    <p class="subtle">Review source sharing, edits and command approvals in the terminal.</p>
  </form>
  <section id="activity-section" class="activity" hidden><h2>Recent activity</h2><ol id="activity"></ol></section>
</main>
<footer id="tools" hidden><details><summary>Troubleshooting</summary><div class="tools">
  <button id="repair" class="text-button">Show Edge setup paths</button>
  <button id="retest" class="text-button" hidden>Test Copilot connection</button>
  <button id="login" class="text-button">Check Microsoft sign-in</button>
  <button id="doctor" class="text-button">Check this laptop</button>
  <button id="settings" class="text-button">Change backend Python</button>
</div></details></footer>
<script nonce="${nonce}" src="${resource('panel.js')}"></script></body></html>`;
}

module.exports = {renderPanel};
