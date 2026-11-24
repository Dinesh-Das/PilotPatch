'use strict';
const fs = require('node:fs/promises');
const {readFileSync} = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const crypto = require('node:crypto');
const {execFile} = require('node:child_process');
const {promisify} = require('node:util');
const {parseRequest, buildInvocation} = require('./request');
const execute = promisify(execFile);

class Controller {
  constructor(vscode, notify, home = path.join(process.env.LOCALAPPDATA ||
    path.join(os.homedir(), '.local', 'share'), 'PilotPatch')) {
    this.vscode = vscode;
    this.notify = notify;
    this.home = home;
    this.folder = undefined;
    this.active = undefined;
    this.state = {phase: 'idle', message: '', busy: false, prepared: false, verified: false, activity: []};
    this.disposables = [
      vscode.tasks.onDidStartTaskProcess(event => this.started(event)),
      vscode.tasks.onDidEndTaskProcess(event => this.ended(event)),
      vscode.tasks.onDidEndTask(event => this.closed(event)),
      vscode.workspace.onDidChangeWorkspaceFolders(() => this.publish()),
      vscode.workspace.onDidChangeConfiguration(event => {
        if (event.affectsConfiguration('pilotpatch')) {
          this.state.prepared = this.state.verified = false;
          this.publish();
        }
      }),
    ];
  }

  python() {
    // Workspace settings are untrusted and must never select an executable.
    const configured = this.vscode.workspace.getConfiguration('pilotpatch').inspect('pythonPath')?.globalValue;
    if (configured) return configured;
    try {
      const registration = path.join(this.home, 'editor-backend.json');
      const python = JSON.parse(readFileSync(registration, 'utf8')).python;
      return typeof python === 'string' && path.isAbsolute(python) ? python : '';
    } catch { return ''; }
  }

  currentFolder() {
    const folders = this.vscode.workspace.workspaceFolders || [];
    return folders.find(folder => folder.uri.toString() === this.folder) || folders[0];
  }

  publish() {
    const folder = this.currentFolder();
    this.notify({...this.state, workspace: folder?.name || '', project: folder?.uri.fsPath || '',
      operation: this.active?.type,
      multiRoot: (this.vscode.workspace.workspaceFolders || []).length > 1,
      configured: Boolean(this.python()), trusted: this.vscode.workspace.isTrusted,
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
      if (this.state.busy && ['configure', 'workspace', 'open-folder'].includes(request.type)) {
        throw new Error('Wait for the current task before changing its workspace or backend.');
      }
      if (request.type === 'open-folder') return await this.vscode.commands.executeCommand('vscode.openFolder');
      if (request.type === 'configure') return await this.configure();
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
      const id = crypto.randomUUID();
      const label = request.type === 'run' ? 'Task' :
        request.type === 'edge-setup' ? 'Edge setup' : request.type[0].toUpperCase() + request.type.slice(1);
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

  matches(event) { return this.active && event.execution.task.definition.runId === this.active.id; }
  started(event) {
    if (this.matches(event)) this.update('running', this.active.starting ||
      'Running in the terminal. Review source sharing, diffs and approvals there.', true);
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
      probe: 'Copilot replied. Enter a task below.',
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
  dispose() { for (const item of this.disposables) item.dispose(); }
}

module.exports = {Controller};
