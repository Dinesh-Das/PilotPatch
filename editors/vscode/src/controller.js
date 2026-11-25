'use strict';
const fs = require('node:fs/promises');
const {readFileSync} = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const crypto = require('node:crypto');
const {execFile} = require('node:child_process');
const {promisify} = require('node:util');
const {parseRequest, buildInvocation} = require('./request');
const {startChat} = require('./chat');
const execute = promisify(execFile);

class Controller {
  constructor(vscode, notify, home = path.join(process.env.LOCALAPPDATA ||
    path.join(os.homedir(), '.local', 'share'), 'PilotPatch'), launchChat = startChat,
    openReviewDiff) {
    this.vscode = vscode;
    this.notify = notify;
    this.home = home;
    this.folder = undefined;
    this.active = undefined;
    this.chats = new Map();
    this.launchChat = launchChat;
    this.openReviewDiff = openReviewDiff;
    this.state = {phase: 'idle', message: '', busy: false, prepared: false, verified: false, activity: []};
    this.disposables = [
      vscode.tasks.onDidStartTaskProcess(event => this.started(event)),
      vscode.tasks.onDidEndTaskProcess(event => this.ended(event)),
      vscode.tasks.onDidEndTask(event => this.closed(event)),
      vscode.workspace.onDidChangeWorkspaceFolders(() => {
        if (this.active?.type === 'chat' && this.active.key !== this.currentFolder()?.uri.toString()) {
          this.stopChat();
        }
        this.publish();
      }),
      vscode.workspace.onDidChangeConfiguration(event => {
        if (event.affectsConfiguration('pilotpatch')) {
          this.state.prepared = this.state.verified = false;
          this.publish();
        }
      }),
    ];
  }

  configuredPython() {
    // Workspace settings are untrusted and must never select an executable.
    const value = this.vscode.workspace.getConfiguration('pilotpatch').inspect('pythonPath')?.globalValue;
    return typeof value === 'string' ? value : '';
  }

  registeredPython() {
    try {
      const registration = path.join(this.home, 'editor-backend.json');
      const python = JSON.parse(readFileSync(registration, 'utf8')).python;
      return typeof python === 'string' && path.isAbsolute(python) ? python : '';
    } catch { return ''; }
  }

  python() { return this.configuredPython() || this.registeredPython(); }

  currentFolder() {
    const folders = this.vscode.workspace.workspaceFolders || [];
    return folders.find(folder => folder.uri.toString() === this.folder) || folders[0];
  }

  publish() {
    const folder = this.currentFolder();
    const key = folder?.uri.toString();
    const configured = this.configuredPython();
    const registered = this.registeredPython();
    this.notify({...this.state, workspace: folder?.name || '', project: folder?.uri.fsPath || '',
      operation: this.active?.type,
      chat: this.chats.get(key) || [], approval: this.active?.key === key ? this.active?.approval : undefined,
      multiRoot: (this.vscode.workspace.workspaceFolders || []).length > 1,
      configured: Boolean(configured || registered), trusted: this.vscode.workspace.isTrusted,
      backendOverride: Boolean(configured && registered && path.relative(configured, registered)),
      remote: Boolean(this.vscode.env.remoteName)});
  }

  update(phase, message, busy = this.state.busy) {
    this.state = {...this.state, phase, message, busy, error: undefined};
    this.publish();
  }

  async configure() {
    if (!this.vscode.workspace.isTrusted || this.vscode.env.remoteName) {
      throw new Error('Open a trusted local editor window to select Python.');
    }
    const files = await this.vscode.window.showOpenDialog({
      title: 'Select Python from the PilotPatch virtual environment',
      openLabel: 'Use this Python', canSelectMany: false, canSelectFolders: false,
      filters: process.platform === 'win32' ? {'Python executable': ['exe']} : undefined,
    });
    if (files?.[0]) {
      if (files[0].scheme !== 'file') throw new Error('Select a local Python executable.');
      try {
        const {stdout} = await execute(files[0].fsPath, ['-I', '-m', 'pilotpatch', '--version'],
          {cwd: os.tmpdir(), timeout: 8000, maxBuffer: 8192, windowsHide: true});
        if (!stdout.startsWith('PilotPatch ')) throw new Error();
      } catch {
        throw new Error('PilotPatch could not start with that Python. Run Windows setup or select its .venv Python.');
      }
      await this.vscode.workspace.getConfiguration('pilotpatch').update('pythonPath', files[0].fsPath,
        this.vscode.ConfigurationTarget.Global);
      this.publish();
    }
  }

  async useSetupPython() {
    if (!this.vscode.workspace.isTrusted || this.vscode.env.remoteName) {
      throw new Error('Open a trusted local editor window to select Python.');
    }
    this.update('preparing', 'Switching to the Python registered by Windows setup…', true);
    try {
      const registered = this.registeredPython();
      const file = registered && await fs.stat(registered).catch(() => undefined);
      if (!file || !file.isFile()) throw new Error('Run Windows setup to register a working backend.');
      await this.vscode.workspace.getConfiguration('pilotpatch').update(
        'pythonPath', undefined, this.vscode.ConfigurationTarget.Global);
      this.state.prepared = this.state.verified = false;
      this.update('finished', 'Using the Python registered by Windows setup.', false);
    } catch (error) {
      this.update('error', error.message, false);
    }
  }

  async chooseWorkspace() {
    const folders = this.vscode.workspace.workspaceFolders || [];
    if (!folders.length) throw new Error('Open a local project folder in the editor first.');
    if (folders.length === 1) return folders[0];
    const selected = await this.vscode.window.showQuickPick(folders.map(folder => ({
      label: folder.name, description: folder.uri.fsPath, folder,
    })), {title: 'Choose the project PilotPatch should work on'});
    if (selected) this.folder = selected.folder.uri.toString();
    this.publish();
    return selected?.folder;
  }

  async handle(input) {
    try {
      const request = parseRequest(input);
      if (request.type === 'ready') return this.publish();
      if (request.type === 'decision') return this.decide(request);
      if (request.type === 'review-open' || request.type === 'review-apply') return this.review(request);
      if (request.type === 'clear-chat') {
        if (this.state.busy) throw new Error('Stop the current operation before clearing the conversation.');
        this.chats.delete(this.currentFolder()?.uri.toString());
        return this.update('idle', 'Conversation cleared in VS Code. For a fresh Copilot chat, start one in Edge.');
      }
      if (this.state.busy && ['configure', 'use-setup-python', 'workspace', 'open-folder'].includes(request.type)) {
        throw new Error('Wait for the current task before changing its workspace or backend.');
      }
      if (request.type === 'open-folder') return await this.vscode.commands.executeCommand('vscode.openFolder');
      if (request.type === 'configure') return await this.configure();
      if (request.type === 'use-setup-python') return await this.useSetupPython();
      if (request.type === 'workspace') return await this.chooseWorkspace();
      if (request.type === 'copy-extension' || request.type === 'copy-pairing') {
        if (this.state.busy) throw new Error('Wait for the current task before changing Edge setup.');
        if (!this.state.prepared) throw new Error('Set up Copilot first.');
        const name = request.type === 'copy-extension' ? 'edge-extension' : 'edge-pairing.json';
        await this.vscode.env.clipboard.writeText(path.join(this.home, name));
        this.update('finished', request.type === 'copy-extension' ?
          'Folder path copied. Paste it in Edge’s Load unpacked picker.' :
          'Pairing file path copied. Paste it into the PilotPatch popup’s file picker.');
        return;
      }
      if (request.type === 'stop') {
        if (this.active?.type === 'chat') return this.stopChat();
        if (this.active?.execution) {
          this.active.stopping = true;
          this.update('stopping', this.active.type === 'probe' ? 'Stopping the connection test…' :
            'Stopping. Review the terminal and saved session before resuming.');
          this.active.execution.terminate();
        }
        return;
      }
      await this.launch(request);
    } catch (error) {
      if (this.state.busy) {
        this.state = {...this.state, error: error.message};
        this.publish();
      } else this.update('error', error.message, false);
    }
  }

  async launch(request) {
    if (this.state.busy) throw new Error('A PilotPatch task is already running in this window.');
    const api = this.vscode;
    if (!api.workspace.isTrusted) throw new Error('Trust this workspace before running local tools.');
    if (api.env.remoteName) throw new Error('Use a local editor window. Remote/WSL hosts are not supported by this Windows Edge backend.');
    const starting = {
      connect: 'Preparing your Edge extension files…',
      'edge-setup': 'Preparing the extension folder and opening Edge setup…',
      probe: 'Connection test running. Wait for the result or stop the test to run your task.',
      doctor: 'Checking this laptop, project and Edge connection…',
      chat: 'Preparing your message…',
    };
    this.update('preparing', starting[request.type] || 'Preparing the local task…', true);
    try {
      const folder = this.currentFolder();
      if (!folder || folder.uri.scheme !== 'file') throw new Error('Open a local project folder first.');
      const python = this.python();
      if (!python) throw new Error('Select the Python executable from your PilotPatch installation.');
      const invocation = buildInvocation(python, folder.uri.fsPath, request);
      if (!(await fs.stat(python)).isFile()) {
        throw new Error('Backend Python is not a file. Rerun Windows setup or select installed Python.');
      }
      if (request.type === 'chat') {
        if (this.currentFolder()?.uri.toString() !== folder.uri.toString()) {
          throw new Error('The selected project changed. Send again from the intended project.');
        }
        this.beginChat(invocation, request, folder);
        return;
      }
      const id = crypto.randomUUID();
      const label = request.type === 'edge-setup' ? 'Edge setup' : request.type[0].toUpperCase() + request.type.slice(1);
      const execution = new api.ProcessExecution(invocation.executable, invocation.args,
        {cwd: invocation.cwd, env: {PYTHONUTF8: '1'}});
      const task = new api.Task({type: 'pilotpatch', runId: id}, folder,
        `${label} · ${folder.name}`, 'PilotPatch', execution, []);
      task.presentationOptions = {reveal: api.TaskRevealKind.Always, focus: true,
        panel: api.TaskPanelKind.Dedicated, clear: false, showReuseMessage: false};
      this.active = {id, execution: undefined, stopping: false, label, type: request.type,
        project: folder.name, starting: starting[request.type]};
      const running = await api.tasks.executeTask(task);
      if (this.active?.id === id) this.active.execution = running;
    } catch (error) {
      this.active = undefined;
      this.update('error', error.code === 'ENOENT' ?
        'Backend Python was not found. Rerun Windows setup or select installed Python.' : error.message, false);
    }
  }

  beginChat(invocation, request, folder) {
    const key = folder.uri.toString();
    const chat = this.chats.get(key) || [];
    const conversation = chat.filter(turn => turn.reply).slice(-8).map(turn => ({
      user: turn.user, assistant: turn.reply, changed_files: turn.files,
    }));
    // The protocol's first line is at most one MiB, including JSON escapes.
    const payload = {prompt: request.prompt, conversation, review_ui: true};
    while (conversation.length && Buffer.byteLength(JSON.stringify(payload)) > 1000000) conversation.shift();
    const active = {type: 'chat', key, chat, user: request.prompt, openDiffs: new Set()};
    this.active = active;
    active.transport = this.launchChat(invocation, payload,
      message => this.chatMessage(active, message),
      code => this.chatClosed(active, code));
    this.publish();
  }

  currentApproval(id) {
    const active = this.active;
    if (!active?.approval || active.approval.id !== id || active.stopping ||
        active.key !== this.currentFolder()?.uri.toString() || !this.vscode.workspace.isTrusted) return;
    return active;
  }

  decide({id, approved}) {
    const active = this.currentApproval(id);
    if (!active || (approved && active.approval.files)) return;
    active.approval = undefined;
    active.transport.decide({id, approved});
    this.update('running', approved ? 'Approved. Continuing…' : 'Declined. Waiting for Copilot…');
  }

  review(request) {
    const active = this.currentApproval(request.id);
    const entries = active?.approval.files;
    if (!entries) return;
    if (request.type === 'review-open') {
      if (!entries.some(file => file.id === request.file) || active.openDiffs.has(request.file)) return;
      active.openDiffs.add(request.file);
      active.transport.decide({id: request.id, open_file: request.file});
      return;
    }
    const selected = new Set(request.files);
    const files = entries.filter(file => selected.has(file.id));
    if (files.length !== selected.size || entries.some(file => file.group != null &&
        selected.has(file.id) !== selected.has(file.group))) {
      throw new Error('Keep linked rename files together and select from this review.');
    }
    const folder = this.currentFolder().uri.fsPath;
    const normalize = value => process.platform === 'win32' ? path.normalize(value).toLowerCase() : path.normalize(value);
    const dirty = new Set((this.vscode.workspace.textDocuments || [])
      .filter(document => document.isDirty && document.uri.scheme === 'file')
      .map(document => normalize(document.uri.fsPath)));
    const unsaved = files.find(file => dirty.has(normalize(path.join(folder, file.path))));
    if (unsaved) throw new Error(`Save or discard unsaved edits in ${unsaved.path} before applying.`);
    active.approval = undefined;
    active.transport.decide({id: request.id, selected: request.files});
    this.update('running', 'Applying the selected changes…');
  }

  stopChat() {
    const active = this.active;
    if (!active?.transport || active.stopping) return;
    active.stopping = true;
    active.approval = undefined;
    active.transport.stop();
    this.update('stopping', 'Stopping the current message…');
  }

  chatMessage(active, message) {
    if (this.active !== active || (active.stopping && !['error', 'stopped'].includes(message.type))) return;
    if (message.type === 'approval' && typeof message.id === 'string') {
      active.approval = message;
      active.openDiffs.clear();
      this.update('running', message.source ? 'Approve source sharing to send.' :
        message.review ? 'The draft is ready to review.' : 'Review Copilot’s request below.');
    } else if (message.type === 'review_document' && this.currentApproval(message.id) &&
               active.openDiffs.delete(message.file)) {
      const file = active.approval.files?.find(item => item.id === message.file);
      if (file && typeof message.before === 'string' && typeof message.after === 'string' && this.openReviewDiff) {
        void this.openReviewDiff(message.id, file, message).catch(() => {
          if (this.currentApproval(message.id)) {
            this.state = {...this.state, error: 'Could not open the VS Code diff. You can still review the inline changes.'};
            this.publish();
          }
        });
      }
    } else if (message.type === 'review_error' && this.currentApproval(message.id)) {
      active.openDiffs.clear();
      this.state = {...this.state, error: message.message};
      this.publish();
    } else if (message.type === 'session' && !active.turn) {
      active.turn = {id: message.id, user: active.user, previews: []};
      active.chat.push(active.turn);
      if (active.chat.length > 24) active.chat.shift();
      this.chats.set(active.key, active.chat);
      this.publish();
    } else if (message.type === 'progress') {
      this.update('running', message.message);
    } else if (message.type === 'preview' && active.turn) {
      const previews = active.turn.previews;
      if (previews.length < 4) {
        previews.push(message.diff.length > 40000 ? `${message.diff.slice(0, 40000)}\n[Preview truncated]` : message.diff);
        this.publish();
      }
    } else if (['reply', 'declined', 'error', 'stopped'].includes(message.type)) {
      active.outcome = message;
    }
  }

  chatClosed(active, code) {
    if (this.active !== active) return;
    const outcome = active.outcome;
    this.active = undefined;
    if (code === 0 && active.turn && outcome?.type === 'reply') {
      const result = outcome.result;
      Object.assign(active.turn, {reply: result.copilot.summary, notes: result.copilot.remaining_issues,
        files: result.files_changed, checks: result.checks, dryRun: result.dry_run,
        proposed: result.proposed_files, reviewStatus: result.review_status, reasoningMode: result.reasoning_mode,
        audit: result.audit, reviewFiles: result.review_files});
      this.state.verified = true;
      this.update('finished', '', false);
      return;
    }
    const stopped = active.stopping || outcome?.type === 'stopped';
    const declined = outcome?.type === 'declined';
    const message = stopped ? (active.turn ? 'Stopped. Review the selected Edge chat and local changes.' :
      'Stopped. Your message is still in the composer.') : outcome?.message ||
      (active.turn ? 'The backend closed before returning a reply. Review Edge and local changes.' :
        'PilotPatch could not start chat. Rerun setup to update the selected backend.');
    if (active.turn) Object.assign(active.turn, {
      error: message, files: outcome?.files_changed, uncertainFile: outcome?.uncertain_file,
    });
    this.update(stopped ? 'stopped' : declined ? 'idle' : 'error', message, false);
  }

  matches(event) { return this.active && event.execution.task.definition.runId === this.active.id; }
  started(event) {
    if (this.matches(event)) this.update('running', this.active.starting ||
      'Running a setup or diagnostic task in the terminal.', true);
  }
  ended(event) {
    if (!this.matches(event)) return;
    const {stopping: stopped, type} = this.active;
    const succeeded = !stopped && event.exitCode === 0;
    const phase = stopped ? 'stopped' : succeeded ? 'finished' : 'error';
    const success = {
      connect: 'Edge setup files are ready. Follow the steps in this panel.',
      'edge-setup': 'Next, click Load unpacked in Edge and paste the extension folder path.',
      login: 'Microsoft sign-in detected. Test the connection to verify a reply.',
      probe: 'Copilot replied. You can start chatting below.',
      doctor: 'Laptop, project and Copilot chat checks passed. Test connection to verify a reply.',
    };
    const failure = {
      connect: 'Edge setup could not prepare its files. See the terminal for the failed step.',
      'edge-setup': 'Edge setup could not prepare its files. See the terminal for the failed step.',
      probe: 'The test ended before a reply was verified. See the terminal for the reason.',
      doctor: 'A setup check failed. See the terminal for the result and next step.',
    };
    const message = stopped ? (type === 'probe' ? 'Connection test stopped. Your task draft is ready.' :
      'Stopped. Inspect the saved session before resuming.') :
      succeeded ? (success[type] || 'Finished. See the terminal for results and any checks.') :
        failure[type] ||
        `Process ended${Number.isInteger(event.exitCode) ? ` with exit ${event.exitCode}` : ''}. Check the terminal for details.`;
    if (['connect', 'edge-setup'].includes(type) && succeeded) {
      this.state.prepared = true;
      this.state.verified = false;
    }
    if (type === 'probe') this.state.verified = succeeded;
    this.state.activity = [{label: this.active.label, project: this.active.project, phase,
      time: new Date().toISOString()}, ...this.state.activity].slice(0, 8);
    this.active = undefined;
    this.update(phase, message, false);
  }
  closed(event) {
    if (this.matches(event)) this.ended({...event, exitCode: undefined});
  }
  dispose() {
    if (this.active?.type === 'chat') this.active.transport?.stop();
    for (const item of this.disposables) item.dispose();
  }
}

module.exports = {Controller};
