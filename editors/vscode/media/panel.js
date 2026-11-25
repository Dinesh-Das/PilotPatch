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
  let selectedFiles = new Set();
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
      project: state.project || draft?.project, review: state.approval?.files ?
        {id: state.approval.id, selected: [...selectedFiles]} : undefined});
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

  function highlightDiff(parent, diff) {
    let before, after, hunk = false;
    for (const line of diff.split(/\r\n|\r|\n/)) {
      if (!line && !hunk) continue;
      const match = /^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@/.exec(line);
      if (match) {
        [before, after] = match.slice(1).map(Number);
        hunk = true;
      }
      if (!line && hunk) continue;
      const added = hunk && line.startsWith('+');
      const removed = hunk && line.startsWith('-');
      const context = hunk && line.startsWith(' ');
      const row = add(parent, 'div', '', `diff-row ${added ? 'diff-added' : removed ?
        'diff-removed' : context ? 'diff-context' : 'diff-header'}`);
      for (const number of [removed || context ? before++ : '', added || context ? after++ : '']) {
        add(row, 'span', number, 'diff-number').setAttribute('aria-hidden', 'true');
      }
      add(row, 'code', line);
    }
  }

  function renderReviewFiles(parent, files, approvalId) {
    parent.replaceChildren();
    for (const [index, file] of files.entries()) {
      const card = add(parent, 'div', '', 'review-file');
      if (approvalId) {
        const box = add(card, 'input', '', 'review-include');
        box.type = 'checkbox';
        box.dataset.file = String(file.id);
        box.setAttribute('aria-label', `Include ${file.path}`);
        box.addEventListener('change', () => {
          for (const item of files) {
            if (item.id === file.id || (file.group != null && item.group === file.group)) {
              if (box.checked) selectedFiles.add(item.id);
              else selectedFiles.delete(item.id);
            }
          }
          renderSelection();
          renderDraft();
        });
      }
      const details = add(card, 'details', '');
      const header = add(details, 'summary', '', 'review-file-header');
      add(header, 'span', file.path, 'review-path');
      const stats = add(header, 'span', '', 'review-stats');
      const kinds = {added: 'Added', modified: 'Modified', deleted: 'Deleted'};
      add(stats, 'span', file.group == null ? kinds[file.kind] : 'Linked rename', 'review-kind');
      if (file.added) add(stats, 'span', `+${file.added}`, 'review-added');
      if (file.removed) add(stats, 'span', `−${file.removed}`, 'review-removed');
      if (approvalId) {
        const button = add(details, 'button', 'Open diff', 'text-button review-open');
        button.type = 'button';
        button.setAttribute('aria-label', `Open diff for ${file.path}`);
        button.addEventListener('click', () =>
          api.postMessage({type: 'review-open', id: approvalId, file: file.id}));
      }
      const diff = add(details, 'div', '', 'review-diff');
      diff.tabIndex = 0;
      diff.setAttribute('role', 'region');
      diff.setAttribute('aria-label', `Changes in ${file.path}`);
      function showLines() {
        if (details.open && !diff.childElementCount) {
          highlightDiff(diff, file.diff);
          if (file.clipped) add(diff, 'p', approvalId ? 'Open diff to review the remaining lines.' :
            'Inline preview clipped.', 'subtle review-clip');
        }
      }
      details.addEventListener('toggle', showLines);
      if (index === 0 && approvalId) {
        details.open = true;
        showLines();
      }
    }
  }

  function renderSelection() {
    const files = state.approval?.files;
    if (!files) return;
    const size = selectedFiles.size;
    const all = element('review-all');
    all.checked = size === files.length;
    all.indeterminate = size > 0 && size < files.length;
    element('review-count').textContent = `${size} of ${files.length} selected`;
    element('approve').textContent = `Apply ${size} ${size === 1 ? 'file' : 'files'}`;
    element('approve').disabled = size === 0;
    for (const box of element('review-files').querySelectorAll('input[data-file]')) {
      box.checked = selectedFiles.has(Number(box.dataset.file));
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
      if (turn.audit) {
        const audit = turn.audit;
        const label = audit.status === 'complete' ? 'Audit coverage' : 'Partial audit';
        add(row, 'p', `${label} · ${audit.files_supplied} of ${audit.files_discovered} eligible files supplied`, 'review-status');
        const limits = {
          step_limit: 'The audit reached the session’s step limit.',
          inventory_limit: 'The repository scan stopped before it could inventory every file.',
          no_source: 'No eligible source files were found.',
          unreadable_source: 'Some files could not be supplied within the audit limits.',
          provider_reply: 'Copilot did not finish a usable audit report.',
        };
        if (limits[audit.reason]) add(row, 'p', limits[audit.reason], 'subtle');
        if (audit.files_redacted) add(row, 'p', `${audit.files_redacted} files supplied with redactions.`, 'subtle');
        if (audit.files_skipped) {
          const skipped = add(row, 'details', '');
          add(skipped, 'summary', `${audit.files_skipped} eligible files skipped`);
          for (const file of audit.skipped || []) add(skipped, 'p', `${file.path} · ${file.reason}`);
        }
      }
      if (turn.error) add(row, 'p', turn.error, 'turn-error');
      const reviewStatus = {preview: 'Preview only', discarded: 'Draft discarded',
        applied: 'Changes applied', partially_applied: 'Selected changes applied',
        no_draft: 'No changes drafted'}[turn.reviewStatus];
      if (reviewStatus) add(row, 'p', reviewStatus, 'review-status');
      if (turn.files?.length || turn.proposed?.length || turn.checks?.length || turn.notes?.length || turn.previews?.length || turn.dryRun) {
        const details = add(row, 'details', '');
        add(details, 'summary', turn.dryRun ? 'Preview and details' : 'Changes and details');
        for (const file of turn.files || []) add(details, 'p', `Changed ${file}`);
        if (turn.reviewStatus === 'preview' && !turn.reviewFiles) {
          for (const file of turn.proposed || []) add(details, 'p', `Proposed ${file}`);
        }
        if (turn.reviewStatus === 'partially_applied') {
          const applied = new Set(turn.files);
          for (const file of turn.proposed || []) {
            if (!applied.has(file)) add(details, 'p', `Skipped ${file}`);
          }
        }
        if (turn.reviewFiles) renderReviewFiles(add(details, 'div', '', 'preview-files'), turn.reviewFiles);
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
    element('file-review').hidden = !approval?.files;
    element('approval-title').textContent = approval?.source ? 'Share with Microsoft Copilot Web' :
      approval?.review ? 'Review changes' : 'Review proposed action';
    element('approval-message').textContent = approval?.message || '';
    element('approval-diff').textContent = approval?.diff || '';
    element('approval-diff').hidden = !approval?.diff;
    element('approve').textContent = approval?.source ? 'Share and send' : approval?.review ? 'Apply changes' : 'Approve';
    element('decline').textContent = approval?.review ? 'Discard draft' : 'Decline';
    for (const id of ['approve', 'decline']) element(id).disabled = !approval;
    if (allowed && approval && approval.id !== previousApproval) {
      if (approval.files) {
        const saved = draft?.review?.id === approval.id ? draft.review.selected : null;
        selectedFiles = new Set(approval.files.map(file => file.id).filter(id => !saved || saved.includes(id)));
        renderReviewFiles(element('review-files'), approval.files, approval.id);
      } else {
        element('review-files').replaceChildren();
      }
      element('approval').scrollIntoView({block: 'nearest'});
    }
    if (approval?.files) renderSelection();
    previousApproval = approval?.id;
  }

  function decide(approved) {
    if (!state.approval) return;
    if (approved && state.approval.files) {
      if (!selectedFiles.size) return;
      api.postMessage({type: 'review-apply', id: state.approval.id, files: [...selectedFiles]});
    } else {
      api.postMessage({type: 'decision', id: state.approval.id, approved});
    }
    element('approve').disabled = element('decline').disabled = true;
  }
  element('approve').addEventListener('click', () => decide(true));
  element('decline').addEventListener('click', () => decide(false));
  element('review-all').addEventListener('change', event => {
    selectedFiles = new Set(event.currentTarget.checked ? state.approval.files.map(file => file.id) : []);
    renderSelection();
    renderDraft();
  });
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
