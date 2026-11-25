'use strict';
(() => {
  const api = acquireVsCodeApi();
  const element = id => document.getElementById(id);
  const prompt = element('prompt');
  const mode = element('mode');
  const dryRun = element('dry-run');
  let state = {busy: false, workspace: '', configured: false, trusted: true, remote: false};
  let submitted;
  let previousChat = '';
  let previousApproval;
  const draft = api.getState();
  if (draft && typeof draft.prompt === 'string') prompt.value = draft.prompt.slice(0, 16000);
  if (draft && ['approve', 'read-only', 'auto-edit'].includes(draft.mode)) mode.value = draft.mode;
  dryRun.checked = draft?.dryRun === true;

  function renderDraft() {
    element('counter').textContent = `${prompt.value.length.toLocaleString()} / 16,000`;
    const testing = state.busy && state.operation === 'probe';
    element('run').textContent = testing ? 'Connection test running…' : 'Send';
    element('stop').textContent = testing ? 'Stop connection test' :
      state.operation === 'chat' ? 'Stop message' : 'Stop';
    element('run').disabled = state.busy || !state.workspace || !state.configured ||
      !state.trusted || state.remote || !prompt.value.trim();
    element('mode-note').textContent = dryRun.checked ? 'Preview edits only. Commands will not run.' :
      mode.value === 'read-only' ? 'Explore source only. Edits and commands are denied.' :
      mode.value === 'auto-edit' ? 'File edits apply automatically. Commands still need approval.' :
      'PilotPatch prepares the edits and presents one review before applying them.';
    api.setState({prompt: prompt.value, mode: mode.value, dryRun: dryRun.checked,
      project: state.project || draft?.project});
  }
  function send(type) { api.postMessage({type}); }
  function submit(event) {
    event?.preventDefault();
    if (element('run').disabled) return;
    element('run').disabled = true;
    submitted = {text: prompt.value, project: state.project, last: state.chat?.at(-1)?.id};
    api.postMessage({type: 'chat', prompt: prompt.value, mode: mode.value, dryRun: dryRun.checked});
  }

  function add(parent, tag, text, style) {
    const node = document.createElement(tag);
    node.textContent = text;
    if (style) node.className = style;
    parent.append(node);
    return node;
  }

  function inline(parent, text) {
    for (const part of text.split(/(`[^`\n]+`|\*\*[^*\n]+\*\*)/)) {
      if (part.startsWith('`') && part.endsWith('`') && part.length > 2) add(parent, 'code', part.slice(1, -1));
      else if (part.startsWith('**') && part.endsWith('**') && part.length > 4) add(parent, 'strong', part.slice(2, -2));
      else parent.append(document.createTextNode(part));
    }
  }

  function markdown(parent, reply) {
    let code, list, paragraph;
    for (const line of reply.split(/\r?\n/)) {
      if (/^\s*```/.test(line)) {
        code = code ? undefined : add(add(parent, 'pre', ''), 'code', '');
        list = paragraph = undefined;
      } else if (code) {
        code.append(document.createTextNode(`${line}\n`));
      } else if (!line.trim()) {
        list = paragraph = undefined;
      } else {
        const heading = /^\s*#{1,6}\s+(.*)$/.exec(line);
        const bullet = /^\s*([-*+]|\d+\.)\s+(.*)$/.exec(line);
        if (heading) {
          inline(add(parent, 'h3', ''), heading[1]);
          list = paragraph = undefined;
        } else if (bullet) {
          const tag = /^\d/.test(bullet[1]) ? 'ol' : 'ul';
          if (list?.localName !== tag) list = add(parent, tag, '');
          inline(add(list, 'li', ''), bullet[2]);
          paragraph = undefined;
        } else {
          list = undefined;
          if (paragraph) paragraph.append(document.createTextNode('\n'));
          else paragraph = add(parent, 'p', '');
          inline(paragraph, line);
        }
      }
    }
  }

  function renderChat(chat, canRun) {
    const log = element('messages'), scroll = log.closest('main');
    element('conversation').hidden = !canRun || !chat.length;
    element('clear-chat').disabled = state.busy;
    const snapshot = JSON.stringify(chat);
    if (snapshot === previousChat) return;
    previousChat = snapshot;
    log.replaceChildren();
    for (const turn of chat) {
      const row = add(log, 'article', '', 'turn');
      add(row, 'strong', 'You');
      add(row, 'p', turn.user, 'utterance user-text');
      if (turn.reply) {
        add(row, 'strong', 'Copilot');
        markdown(add(row, 'div', '', 'utterance reply'), turn.reply);
      }
      if (turn.error) add(row, 'p', turn.error, 'turn-error');
      const reviewStatus = {preview: 'Preview only', discarded: 'Draft discarded',
        applied: 'Changes applied', no_draft: 'No changes drafted'}[turn.reviewStatus];
      if (reviewStatus) add(row, 'p', reviewStatus, 'review-status');
      if (turn.files?.length || turn.proposed?.length || turn.checks?.length || turn.notes?.length || turn.previews?.length || turn.dryRun) {
        const details = add(row, 'details', '');
        add(details, 'summary', turn.dryRun ? 'Preview and details' : 'Changes and details');
        for (const file of turn.files || []) add(details, 'p', `Changed ${file}`);
        if (turn.reviewStatus === 'preview') {
          for (const file of turn.proposed || []) add(details, 'p', `Proposed ${file}`);
        }
        for (const check of turn.checks || []) {
          const status = check.timed_out ? 'Timed out' : `Exit ${check.exit_code}`;
          add(details, 'p', `${status} · ${check.argv.join(' ')}`);
        }
        for (const note of turn.notes || []) add(details, 'p', note);
        for (const diff of turn.previews || []) add(details, 'pre', diff);
      }
    }
    if (chat.length) log.lastElementChild?.scrollIntoView({block: 'end'});
    else scroll.scrollTop = 0;
  }

  function renderApproval(approval, allowed) {
    element('approval').hidden = !allowed || !approval;
    element('approval-title').textContent = approval?.source ? 'Share with Microsoft Copilot Web' :
      approval?.review ? 'Review changes' : 'Review proposed action';
    element('approval-message').textContent = approval?.message || '';
    element('approval-diff').textContent = approval?.diff || '';
    element('approval-diff').hidden = !approval?.diff;
    element('approve').textContent = approval?.source ? 'Share and send' : approval?.review ? 'Apply changes' : 'Approve';
    element('decline').textContent = approval?.review ? 'Discard draft' : 'Decline';
    for (const id of ['approve', 'decline']) element(id).disabled = !approval;
    if (allowed && approval && approval.id !== previousApproval) {
      element('approval').scrollIntoView({block: 'nearest'});
    }
    previousApproval = approval?.id;
  }

  function decide(approved) {
    if (!state.approval) return;
    api.postMessage({type: 'decision', id: state.approval.id, approved});
    element('approve').disabled = element('decline').disabled = true;
  }
  element('approve').addEventListener('click', () => decide(true));
  element('decline').addEventListener('click', () => decide(false));
  element('task-form').addEventListener('submit', submit);
  prompt.addEventListener('keydown', event => {
    if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') submit(event);
  });
  for (const input of [prompt, mode, dryRun]) input.addEventListener('input', renderDraft);
  for (const id of ['login', 'probe', 'doctor', 'workspace', 'open-folder',
    'stop', 'configure', 'copy-extension', 'copy-pairing', 'clear-chat']) {
    element(id).addEventListener('click', () => send(id));
  }
  element('connect').addEventListener('click', () => send('edge-setup'));
  element('repair').addEventListener('click', () => send('connect'));
  element('retest').addEventListener('click', () => send('probe'));
  element('settings').addEventListener('click', () => send('configure'));
  window.addEventListener('message', event => {
    if (event.data?.type !== 'state') return;
    const lastProject = state.project || draft?.project;
    state = event.data;
    if (lastProject && state.project !== lastProject) prompt.value = '';
    const lastTurn = state.chat?.at(-1);
    const lastMode = state.chat?.filter(turn => turn.reasoningMode).at(-1)?.reasoningMode;
    const label = {think_deeper: 'Think Deeper', auto: 'Auto', current: 'Mode unverified'}[lastMode];
    element('reasoning').textContent = label ? `Microsoft Copilot Web · ${label}` : 'Microsoft Copilot Web';
    if (lastTurn && submitted && submitted.project === state.project && lastTurn.id !== submitted.last &&
        lastTurn.user === submitted.text.trim()) {
      if (prompt.value === submitted.text) prompt.value = '';
      submitted = undefined;
    }
    if (!state.busy) submitted = undefined;
    element('workspace-name').textContent = state.workspace || 'No project open';
    element('workspace-path').textContent = state.project || '';
    const allowed = state.trusted && !state.remote;
    const canRun = allowed && Boolean(state.workspace) && state.configured;
    element('workspace').hidden = !allowed || !state.multiRoot;
    element('project-setup').hidden = !allowed || Boolean(state.workspace);
    element('backend-setup').hidden = !allowed || !state.workspace || state.configured;
    element('connection').hidden = !canRun || state.verified;
    element('retest').hidden = !state.verified;
    element('connect-intro').hidden = state.prepared;
    element('edge-steps').hidden = !state.prepared;
    element('connect').hidden = state.prepared;
    element('probe').className = state.prepared ? 'primary' : 'secondary';
    element('task-form').hidden = !canRun;
    element('tools').hidden = !canRun;
    element('status').dataset.phase = state.phase;
    element('status').textContent = !state.trusted ? 'Trust this workspace before running local tools.' :
      state.remote ? 'Use a local editor window for the Windows Edge backend.' : state.message;
    element('panel-error').hidden = !state.error;
    element('panel-error').textContent = state.error || '';
    element('stop').hidden = !state.busy;
    element('stop').disabled = state.phase === 'preparing' || state.phase === 'stopping';
    renderChat(state.chat || [], canRun);
    renderApproval(state.approval, canRun);
    for (const id of ['connect', 'login', 'probe', 'doctor', 'workspace', 'settings',
      'configure', 'mode', 'dry-run', 'repair', 'retest', 'open-folder', 'copy-extension', 'copy-pairing']) {
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
