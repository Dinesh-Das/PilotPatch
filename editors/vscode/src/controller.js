'use strict';
const fs = require('node:fs/promises');
const crypto = require('node:crypto');
const {parseRequest, buildInvocation} = require('./request');

class Controller {
  constructor(vscode, notify) {
    this.vscode = vscode;
    this.notify = notify;
    this.folder = undefined;
    this.active = undefined;
    this.state = {phase: 'idle', message: 'Ready when you are.', busy: false, activity: []};
    this.disposables = [
      vscode.tasks.onDidStartTaskProcess(event => this.started(event)),
      vscode.tasks.onDidEndTaskProcess(event => this.ended(event)),
      vscode.tasks.onDidEndTask(event => this.closed(event)),
      vscode.workspace.onDidChangeWorkspaceFolders(() => this.publish()),
      vscode.workspace.onDidChangeConfiguration(event => {
        if (event.affectsConfiguration('pilotpatch')) this.publish();
      }),
    ];
  }

  python() {
    // Workspace settings are untrusted and must never select an executable.
    return this.vscode.workspace.getConfiguration('pilotpatch').inspect('pythonPath')?.globalValue || '';
  }

  currentFolder() {
    const folders = this.vscode.workspace.workspaceFolders || [];
    return folders.find(folder => folder.uri.toString() === this.folder) || folders[0];
  }

  publish() {
    const folder = this.currentFolder();
    this.notify({...this.state, workspace: folder?.name || '', project: folder?.uri.fsPath || '',
      configured: Boolean(this.python()), trusted: this.vscode.workspace.isTrusted,
      remote: Boolean(this.vscode.env.remoteName)});
  }

  update(phase, message, busy = this.state.busy) {
    this.state = {...this.state, phase, message, busy, error: undefined};
    this.publish();
  }

  async configure() {
    const files = await this.vscode.window.showOpenDialog({
      title: 'Select Python from the PilotPatch virtual environment',
      openLabel: 'Use this Python', canSelectMany: false, canSelectFolders: false,
      filters: process.platform === 'win32' ? {'Python executable': ['exe']} : undefined,
    });
    if (files?.[0]) {
      if (files[0].scheme !== 'file') throw new Error('Select a local Python executable.');
      await this.vscode.workspace.getConfiguration('pilotpatch').update('pythonPath', files[0].fsPath,
        this.vscode.ConfigurationTarget.Global);
      this.publish();
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
      if (this.state.busy && ['configure', 'workspace'].includes(request.type)) {
        throw new Error('Wait for the current task before changing its workspace or backend.');
      }
      if (request.type === 'configure') return await this.configure();
      if (request.type === 'workspace') return await this.chooseWorkspace();
      if (request.type === 'stop') {
        if (this.active?.execution) {
          this.active.stopping = true;
          this.update('stopping', 'Stopping. Review the terminal and saved session before resuming.');
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
    this.update('preparing', 'Preparing the local task…', true);
    try {
      const folder = this.currentFolder();
      if (!folder || folder.uri.scheme !== 'file') throw new Error('Open a local project folder first.');
      const python = this.python();
      if (!python) throw new Error('Select the Python executable from your PilotPatch installation.');
      const invocation = buildInvocation(python, folder.uri.fsPath, request);
      if (!(await fs.stat(python)).isFile()) throw new Error('The configured Python executable is not a file.');
      const id = crypto.randomUUID();
      const label = request.type === 'run' ? 'Task' : request.type[0].toUpperCase() + request.type.slice(1);
      const execution = new api.ProcessExecution(invocation.executable, invocation.args,
        {cwd: invocation.cwd, env: {PYTHONUTF8: '1'}});
      const task = new api.Task({type: 'pilotpatch', runId: id}, folder,
        `${label} · ${folder.name}`, 'PilotPatch', execution, []);
      task.presentationOptions = {reveal: api.TaskRevealKind.Always, focus: true,
        panel: api.TaskPanelKind.Dedicated, clear: false, showReuseMessage: false};
      this.active = {id, execution: undefined, stopping: false, label, project: folder.name};
      const running = await api.tasks.executeTask(task);
      if (this.active?.id === id) this.active.execution = running;
    } catch (error) {
      this.active = undefined;
      this.update('error', error.code === 'ENOENT' ? 'Backend Python was not found. Select it again.' : error.message, false);
    }
  }

  matches(event) { return this.active && event.execution.task.definition.runId === this.active.id; }
  started(event) {
    if (this.matches(event)) this.update('running', 'Running in the terminal. Review source sharing, diffs and approvals there.', true);
  }
  ended(event) {
    if (!this.matches(event)) return;
    const stopped = this.active.stopping;
    const phase = stopped ? 'stopped' : event.exitCode === 0 ? 'finished' : 'error';
    const message = stopped ? 'Stopped. Inspect the saved session before resuming.' :
      event.exitCode === 0 ? 'Process finished. Read the actual Copilot summary and checks in the terminal.' :
        `Process ended${Number.isInteger(event.exitCode) ? ` with exit ${event.exitCode}` : ''}. Check the terminal for details.`;
    this.state.activity = [{label: this.active.label, project: this.active.project, phase,
      time: new Date().toISOString()}, ...this.state.activity].slice(0, 8);
    this.active = undefined;
    this.update(phase, message, false);
  }
  closed(event) {
    if (this.matches(event)) this.ended({...event, exitCode: undefined});
  }
  dispose() { for (const item of this.disposables) item.dispose(); }
}

module.exports = {Controller};
