'use strict';
const {test} = require('node:test');
const assert = require('node:assert/strict');
const {parseRequest, buildInvocation} = require('../src/request');

test('preserves task text as a single process argument without shell interpretation', () => {
  const prompt = 'Fix "login"; $(whoami) & echo x\nAdd tests.';
  const request = parseRequest({type: 'run', prompt, mode: 'approve', dryRun: false});
  const invocation = buildInvocation('C:\\Python path\\python.exe', 'C:\\My project', request);
  assert.equal(invocation.executable, 'C:\\Python path\\python.exe');
  assert.deepEqual(invocation.args.slice(-2), ['run', prompt]);
  assert.equal(invocation.cwd, 'C:\\My project');
  assert.ok(!invocation.args.includes('--share-code'));
});

test('read-only and dry-run are passed explicitly', () => {
  const request = parseRequest({type: 'run', prompt: 'Analyze project', mode: 'read-only', dryRun: true});
  const args = buildInvocation('C:\\Python\\python.exe', 'C:\\repo', request).args;
  assert.ok(args.includes('--dry-run'));
  assert.equal(args[args.indexOf('--mode') + 1], 'read-only');
});

test('rejects unknown messages, extra fields and permission escalation', () => {
  for (const input of [null, [], {type: 'shell', command: 'anything'},
    {type: 'run', prompt: 'task', mode: 'approve', dryRun: false, shareCode: true},
    {type: 'run', prompt: 'task', mode: 'unsafe', dryRun: false},
    {type: 'run', prompt: ' ', mode: 'approve', dryRun: false},
    {type: 'run', prompt: 'x\u0000y', mode: 'approve', dryRun: false},
    {type: 'run', prompt: 'x'.repeat(16001), mode: 'approve', dryRun: false},
    {type: 'run', prompt: 'task', mode: 'approve', dryRun: 'yes'}]) {
    assert.throws(() => parseRequest(input));
  }
});

test('diagnostics are fixed commands without model/source-sharing flags', () => {
  for (const type of ['login', 'probe', 'doctor', 'history']) {
    const invocation = buildInvocation('C:\\Python\\python.exe', 'C:\\repo', parseRequest({type}));
    assert.equal(invocation.args.at(-1), type);
    assert.ok(!invocation.args.includes('--share-code'));
  }
});
