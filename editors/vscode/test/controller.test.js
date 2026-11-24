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
  const controller = new Controller(api, state => updates.push(state), overrides.home || '');
  return {controller, api, updates, tasks, listeners, terminated: () => terminated};
}
const run = {type: 'run', prompt: 'Implement a health check', mode: 'approve', dryRun: false};

test('starts a real task definition for the selected project with argv and terminal approvals', async () => {
  const f = fixture();
  await f.controller.handle(run);
  const task = f.tasks[0].task;
  assert.equal(task.execution.executable, process.execPath);
  assert.equal(task.execution.options.cwd, 'C:\\Target project');
  assert.equal(task.execution.args.at(-1), run.prompt);
  assert.equal(task.presentationOptions.focus, true);
  assert.equal(f.updates.at(-1).phase, 'running');
  assert.ok(!task.execution.args.includes('--share-code'));
});

test('rejects untrusted, remote, missing-workspace and missing-backend launches', async () => {
  for (const override of [{trusted: false}, {remote: 'wsl'}, {noFolder: true}, {missingPython: true}]) {
    const f = fixture(override);
    await f.controller.handle(run);
    assert.equal(f.tasks.length, 0);
    assert.equal(f.updates.at(-1).phase, 'error');
    assert.equal(f.updates.at(-1).busy, false);
  }
});

test('duplicate clicks do not launch another process or erase the workspace state', async () => {
  const f = fixture();
  await f.controller.handle(run);
  await f.controller.handle(run);
  assert.equal(f.tasks.length, 1);
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
  await f.controller.handle(run);
  f.listeners.end({execution: f.tasks[1], exitCode: 2});
  assert.equal(f.updates.at(-1).phase, 'error');
  assert.match(f.updates.at(-1).message, /exit 2/);
});

test('stopping terminates only the owned task and waits for its end event', async () => {
  const f = fixture();
  await f.controller.handle(run);
  await f.controller.handle({type: 'stop'});
  assert.equal(f.terminated(), 1);
  assert.equal(f.updates.at(-1).phase, 'stopping');
  f.listeners.end({execution: f.tasks[0], exitCode: undefined});
  assert.equal(f.updates.at(-1).phase, 'stopped');
  assert.equal(f.updates.at(-1).busy, false);
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
