'use strict';
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const {Controller} = require('../src/controller');

function fixture(overrides = {}) {
  const listeners = {};
  const updates = [];
  const tasks = [];
  const chats = [];
  let terminated = 0;
  const listen = name => callback => {listeners[name] = callback; return {dispose() {}};};
  const folder = {name: 'Target project', uri: {scheme: 'file', fsPath: 'C:\\Target project', toString: () => 'file:///target'}};
  const api = {
    env: {remoteName: overrides.remote},
    workspace: {
      isTrusted: overrides.trusted !== false, workspaceFolders: overrides.noFolder ? [] : [folder],
      getConfiguration: () => ({inspect: () => ({globalValue: overrides.missingPython ? '' : process.execPath,
        workspaceValue: 'C:\\untrusted\\python.exe'})}),
      onDidChangeWorkspaceFolders: listen('folders'), onDidChangeConfiguration: listen('config'),
    },
    window: {},
    TaskRevealKind: {Always: 1}, TaskPanelKind: {Dedicated: 1},
    ProcessExecution: class {constructor(executable, args, options) {Object.assign(this, {executable, args, options});}},
    Task: class {constructor(definition, scope, name, source, execution) {Object.assign(this, {definition, scope, name, source, execution});}},
    tasks: {
      onDidStartTaskProcess: listen('start'), onDidEndTaskProcess: listen('end'), onDidEndTask: listen('close'),
      async executeTask(task) {
        const execution = {task, terminate() {terminated++;}};
        tasks.push(execution);
        listeners.start({execution, processId: 42});
        return execution;
      },
    },
  };
  const startChat = (invocation, request, message, close) => {
    const decisions = [];
    const chat = {invocation, request, message, close, decisions, stopped: false};
    chats.push(chat);
    return {decide: value => decisions.push(value), stop: () => {chat.stopped = true;}};
  };
  const controller = new Controller(api, state => updates.push(state), overrides.home || '', startChat,
    overrides.openReviewDiff);
  return {controller, api, updates, tasks, chats, listeners, terminated: () => terminated};
}
const chat = {type: 'chat', prompt: 'Explain the controls', mode: 'approve', dryRun: false};

test('opens only requested snapshots and applies a validated selection', async () => {
  const opened = [];
  const f = fixture({openReviewDiff: async (...args) => {opened.push(args);}});
  await f.controller.handle(chat);
  const first = f.chats[0], id = '1'.repeat(32);
  const a = {id: 0, path: 'app.py'}, b = {id: 1, group: 1, path: 'old.py'};
  const c = {id: 2, group: 1, path: 'new.py'};
  first.message({type: 'approval', id, message: 'Review', review: true, files: [a, b, c]});
  const snapshot = {type: 'review_document', id, file: 0, before: 'old', after: 'new'};
  first.message(snapshot);
  assert.deepEqual(opened, []);
  await f.controller.handle({type: 'review-open', id, file: 0});
  first.message(snapshot);
  assert.deepEqual(opened, [[id, a, snapshot]]);
  await f.controller.handle({type: 'decision', id, approved: true});
  await f.controller.handle({type: 'review-apply', id, files: [1]});
  assert.match(f.updates.at(-1).error, /linked rename/);
  const folder = f.controller.currentFolder().uri.fsPath;
  f.api.workspace.textDocuments = [{isDirty: true, uri: {scheme: 'file', fsPath: path.join(folder, a.path)}}];
  await f.controller.handle({type: 'review-apply', id, files: [0]});
  assert.match(f.updates.at(-1).error, /unsaved edits in app.py/);
  f.api.workspace.textDocuments = [];
  await f.controller.handle({type: 'review-apply', id, files: [0]});
  assert.deepEqual(first.decisions, [{id, open_file: 0}, {id, selected: [0]}]);
});

test('chat accepts only the current approval and includes the last answer in a follow-up', async () => {
  const f = fixture();
  await f.controller.handle(chat);
  const first = f.chats[0];
  assert.equal(first.request.prompt, chat.prompt);
  assert.equal(f.tasks.length, 0);
  assert.ok(!first.invocation.args.includes(chat.prompt));
  assert.ok(!first.invocation.args.includes('--share-code'));
  const id = 'a'.repeat(32);
  first.message({type: 'approval', id, message: 'Share project context?', source: true});
  assert.equal(f.updates.at(-1).approval.id, id);
  await f.controller.handle({type: 'decision', id: 'b'.repeat(32), approved: true});
  assert.deepEqual(first.decisions, []);
  await f.controller.handle({type: 'decision', id, approved: true});
  assert.deepEqual(first.decisions, [{id, approved: true}]);
  first.message({type: 'session', id});
  first.message({type: 'reply', result: {
    copilot: {summary: 'Space makes the bird jump.', remaining_issues: []}, files_changed: [], checks: [],
  }});
  first.close(0);
  assert.equal(f.updates.at(-1).chat[0].reply, 'Space makes the bird jump.');
  await f.controller.handle({...chat, prompt: 'Where is that handled?'});
  assert.deepEqual(f.chats[1].request.conversation, [
    {user: chat.prompt, assistant: 'Space makes the bird jump.', changed_files: []},
  ]);
  assert.match(f.updates.at(-1).message, /Preparing/);
});

test('starts a diagnostic with the selected project and shows its terminal', async () => {
  const f = fixture();
  await f.controller.handle({type: 'doctor'});
  const task = f.tasks[0].task;
  assert.equal(task.execution.executable, process.execPath);
  assert.equal(task.execution.options.cwd, 'C:\\Target project');
  assert.equal(task.execution.args.at(-1), 'doctor');
  assert.equal(task.presentationOptions.focus, true);
  assert.equal(f.updates.at(-1).phase, 'running');
  assert.ok(!task.execution.args.includes('--share-code'));
});

test('rejects untrusted, remote, missing-workspace and missing-backend launches', async () => {
  for (const override of [{trusted: false}, {remote: 'wsl'}, {noFolder: true}, {missingPython: true}]) {
    const f = fixture(override);
    await f.controller.handle(chat);
    assert.equal(f.tasks.length, 0);
    assert.equal(f.chats.length, 0);
    assert.equal(f.updates.at(-1).phase, 'error');
    assert.equal(f.updates.at(-1).busy, false);
  }
});

test('duplicate clicks do not launch another process or erase the workspace state', async () => {
  const f = fixture();
  await f.controller.handle(chat);
  await f.controller.handle(chat);
  assert.equal(f.chats.length, 1);
  assert.equal(f.updates.at(-1).workspace, 'Target project');
  assert.match(f.updates.at(-1).error, /already running/);
});

test('uses actual task exit events and does not label exit zero as tests passed', async () => {
  const f = fixture();
  await f.controller.handle({type: 'history'});
  f.listeners.end({execution: f.tasks[0], exitCode: 0});
  assert.equal(f.updates.at(-1).phase, 'finished');
  assert.equal(f.updates.at(-1).busy, false);
  assert.doesNotMatch(f.updates.at(-1).message, /tests passed/i);
  await f.controller.handle({type: 'login'});
  f.listeners.end({execution: f.tasks[1], exitCode: 2});
  assert.equal(f.updates.at(-1).phase, 'error');
  assert.match(f.updates.at(-1).message, /exit 2/);
});

test('stopping terminates only the owned task and waits for its end event', async () => {
  const f = fixture();
  await f.controller.handle({type: 'probe'});
  await f.controller.handle({type: 'stop'});
  assert.equal(f.terminated(), 1);
  assert.equal(f.updates.at(-1).phase, 'stopping');
  f.listeners.end({execution: f.tasks[0], exitCode: undefined});
  assert.equal(f.updates.at(-1).phase, 'stopped');
  assert.equal(f.updates.at(-1).busy, false);
});

test('stopping chat preserves recorded changes and the interrupted file', async () => {
  const f = fixture();
  await f.controller.handle(chat);
  const turn = f.chats[0];
  turn.message({type: 'session', id: 'a'.repeat(32)});
  await f.controller.handle({type: 'stop'});
  assert.equal(turn.stopped, true);
  turn.message({type: 'stopped', files_changed: ['answer.py'], uncertain_file: 'details.txt'});
  turn.close(130);
  const state = f.updates.at(-1);
  assert.equal(state.phase, 'stopped');
  assert.deepEqual(state.chat[0].files, ['answer.py']);
  assert.equal(state.chat[0].uncertainFile, 'details.txt');
});

test('uses the registered backend and copies only paths for successful setup', async t => {
  const home = await fs.mkdtemp(path.join(os.tmpdir(), 'pilotpatch-editor-'));
  t.after(() => fs.rm(home, {recursive: true, force: true}));
  await fs.writeFile(path.join(home, 'editor-backend.json'), JSON.stringify({python: process.execPath}));
  const f = fixture({missingPython: true, home});
  let clipboard;
  f.api.env.clipboard = {async writeText(value) {clipboard = value;}};
  await f.controller.handle({type: 'copy-pairing'});
  assert.equal(clipboard, undefined);
  await f.controller.handle({type: 'connect'});
  f.listeners.end({execution: f.tasks[0], exitCode: 0});
  assert.equal(f.updates.at(-1).prepared, true);
  assert.equal(f.updates.at(-1).verified, false);
  await f.controller.handle({type: 'copy-pairing'});
  assert.equal(clipboard, path.join(home, 'edge-pairing.json'));
  await f.controller.handle({type: 'probe'});
  assert.equal(f.updates.at(-1).operation, 'probe');
  f.listeners.end({execution: f.tasks[1], exitCode: 0});
  assert.equal(f.updates.at(-1).verified, true);
  assert.equal(f.updates.at(-1).busy, false);
});

test('offers the setup backend when a manual Python setting points elsewhere', async t => {
  const home = await fs.mkdtemp(path.join(os.tmpdir(), 'pilotpatch-editor-'));
  t.after(() => fs.rm(home, {recursive: true, force: true}));
  await fs.writeFile(path.join(home, 'editor-backend.json'), JSON.stringify({python: process.execPath}));
  const f = fixture({home});
  let manual = path.join(home, 'old', 'python.exe');
  f.api.ConfigurationTarget = {Global: 1};
  f.api.workspace.getConfiguration = () => ({
    inspect: () => ({globalValue: manual, workspaceValue: 'untrusted.exe'}),
    async update(key, value, target) {
      assert.deepEqual([key, value, target], ['pythonPath', undefined, f.api.ConfigurationTarget.Global]);
      manual = value;
    },
  });
  await f.controller.handle({type: 'ready'});
  assert.equal(f.updates.at(-1).backendOverride, true);
  await f.controller.handle({type: 'use-setup-python'});
  assert.equal(f.updates.at(-1).backendOverride, false);
  await f.controller.handle({type: 'probe'});
  assert.equal(f.tasks[0].task.execution.executable, process.execPath);
});
