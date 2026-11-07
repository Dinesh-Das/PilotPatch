'use strict';
(() => {
  const api = acquireVsCodeApi();
  const element = id => document.getElementById(id);
  const prompt = element('prompt');
  const mode = element('mode');
  const dryRun = element('dry-run');
  let state = {busy: false, workspace: '', configured: false, trusted: true, remote: false};
  const draft = api.getState();
  if (draft && typeof draft.prompt === 'string') prompt.value = draft.prompt.slice(0, 16000);
  if (draft && ['approve', 'read-only', 'auto-edit'].includes(draft.mode)) mode.value = draft.mode;
  dryRun.checked = draft?.dryRun === true;

  function renderDraft() {
    element('counter').textContent = `${prompt.value.length.toLocaleString()} / 16,000`;
    element('run').disabled = state.busy || !state.workspace || !state.configured ||
      !state.trusted || state.remote || !prompt.value.trim();
    element('mode-note').textContent = dryRun.checked ? 'Preview edits only. Commands will not run.' :
      mode.value === 'read-only' ? 'Explore source only. Edits and commands are denied.' :
      mode.value === 'auto-edit' ? 'File edits apply automatically. Commands still need approval.' :
      'Review edits and approve commands in the terminal.';
    api.setState({prompt: prompt.value, mode: mode.value, dryRun: dryRun.checked});
  }
  function send(type) { api.postMessage({type}); }
  function submit(event) {
    event?.preventDefault();
    if (element('run').disabled) return;
    element('run').disabled = true;
    api.postMessage({type: 'run', prompt: prompt.value, mode: mode.value, dryRun: dryRun.checked});
  }
  element('task-form').addEventListener('submit', submit);
  prompt.addEventListener('keydown', event => {
    if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') submit(event);
  });
  for (const input of [prompt, mode, dryRun]) input.addEventListener('input', renderDraft);
  for (const id of ['login', 'probe', 'doctor', 'workspace', 'stop', 'configure']) {
    element(id).addEventListener('click', () => send(id));
  }
  element('settings').addEventListener('click', () => send('configure'));
  window.addEventListener('message', event => {
    if (event.data?.type !== 'state') return;
    state = event.data;
    element('workspace-name').textContent = state.workspace || 'No project open';
    element('workspace-path').textContent = state.project || 'Use File → Open Folder to choose a local project.';
    element('setup').hidden = state.configured;
    element('phase').textContent = (state.phase || 'idle').toUpperCase();
    element('phase').dataset.phase = state.phase;
    element('status').textContent = !state.trusted ? 'Trust this workspace before running local tools.' :
      state.remote ? 'Use a local editor window for the Windows Edge backend.' : state.message;
    element('panel-error').hidden = !state.error;
    element('panel-error').textContent = state.error || '';
    element('stop').hidden = !state.busy;
    element('stop').disabled = state.phase === 'preparing' || state.phase === 'stopping';
    for (const id of ['login', 'probe', 'doctor', 'workspace', 'settings', 'configure', 'mode', 'dry-run']) {
      element(id).disabled = state.busy;
    }
    const list = element('activity');
    list.replaceChildren();
    for (const item of state.activity || []) {
      const row = document.createElement('li');
      const label = document.createElement('strong');
      label.textContent = `${item.label} · ${item.project}`;
      const status = document.createElement('span');
      status.textContent = `${item.phase} · ${new Date(item.time).toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'})}`;
      row.append(label, status);
      list.append(row);
    }
    element('activity-section').hidden = !list.childElementCount;
    renderDraft();
  });
  renderDraft();
  send('ready');
})();
