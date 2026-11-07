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
<header class="masthead"><span class="brand-mark" aria-hidden="true">P<span>↗</span></span>
<div><p class="eyebrow">YOUR PROJECT, IN FLIGHT</p><h1>PilotPatch</h1></div></header>
<main>
  <section class="workspace-section" aria-label="Target project">
    <div class="section-label">WORKSPACE <button id="workspace" class="text-button">Change</button></div>
    <strong id="workspace-name">No project open</strong>
    <p id="workspace-path" class="path">Open a local folder to get started.</p>
  </section>
  <section id="setup" class="setup" aria-labelledby="setup-title" hidden>
    <h2 id="setup-title">Connect your local harness</h2>
    <p>Select the Python executable from your PilotPatch virtual environment. You only need to do this once per editor.</p>
    <button id="configure" class="secondary">Select backend Python</button>
  </section>
  <form id="task-form">
    <div class="composer-heading"><h2>A prompt. A patch.</h2><span class="provider">MICROSOFT COPILOT</span></div>
    <label for="prompt">What would you like to change?</label>
    <textarea id="prompt" rows="8" maxlength="16000" spellcheck="false" placeholder="Add a health-check endpoint and cover it with tests." aria-describedby="prompt-help"></textarea>
    <div class="composer-footer"><span id="prompt-help">Ctrl / ⌘ + Enter to run</span><span id="counter">0 / 16,000</span></div>
    <div class="options">
      <div class="mode"><label for="mode">Permissions</label><select id="mode">
        <option value="approve">Approve changes</option><option value="read-only">Read only</option>
        <option value="auto-edit">Auto-edit files</option></select></div>
      <label class="checkbox"><input id="dry-run" type="checkbox"> Preview only</label>
    </div>
    <p id="mode-note" class="subtle">Review edits and approve commands in the terminal.</p>
    <div class="submit-row"><button id="run" type="submit" class="primary">Run task <span aria-hidden="true">↗</span></button>
      <button id="stop" type="button" class="secondary" hidden>Stop task</button></div>
  </form>
  <section class="execution" aria-label="Execution status"><p class="status-label" id="phase">READY</p>
    <p id="status" role="status" aria-live="polite">Ready when you are.</p>
    <p id="panel-error" role="alert" hidden></p></section>
  <section id="activity-section" class="activity" hidden><h2>Recent activity</h2><ol id="activity"></ol></section>
</main>
<footer><div class="tools" aria-label="Copilot setup and diagnostics">
  <button id="login" class="text-button">Sign in</button><button id="probe" class="text-button">Test connection</button>
  <button id="doctor" class="text-button">Check setup</button><button id="settings" class="text-button">Backend</button>
</div><p class="privacy">Routes to Microsoft Copilot Web.<br>Source-sharing consent and approvals happen in your terminal.</p></footer>
<script nonce="${nonce}" src="${resource('panel.js')}"></script></body></html>`;
}

module.exports = {renderPanel};
