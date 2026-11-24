'use strict';
const {test} = require('node:test');
const assert = require('node:assert/strict');
const {parseRequest, buildInvocation} = require('../src/request');

test('keeps chat text off the command line and passes only fixed backend options', () => {
  const prompt = 'Fix "login"; $(whoami) & echo x\nAdd tests.';
  const request = parseRequest({type: 'chat', prompt, mode: 'approve', dryRun: false});
  const invocation = buildInvocation('C:\\Python path\\python.exe', 'C:\\My project', request);
  assert.equal(invocation.executable, 'C:\\Python path\\python.exe');
  assert.equal(request.prompt, prompt);
  assert.deepEqual(invocation.args.slice(-3), ['--mode', 'approve', 'editor-chat']);
  assert.equal(invocation.cwd, 'C:\\My project');
  assert.ok(!invocation.args.includes('--share-code'));
});

test('read-only and dry-run are passed explicitly', () => {
  const request = parseRequest({type: 'chat', prompt: 'Analyze project', mode: 'read-only', dryRun: true});
  const args = buildInvocation('C:\\Python\\python.exe', 'C:\\repo', request).args;
  assert.ok(args.includes('--dry-run'));
  assert.equal(args[args.indexOf('--mode') + 1], 'read-only');
});

test('rejects unknown messages, extra fields and permission escalation', () => {
  for (const input of [null, [], {type: 'shell', command: 'anything'},
    {type: 'chat', prompt: 'task', mode: 'approve', dryRun: false, shareCode: true},
    {type: 'chat', prompt: 'task', mode: 'unsafe', dryRun: false},
    {type: 'chat', prompt: ' ', mode: 'approve', dryRun: false},
    {type: 'chat', prompt: 'x\u0000y', mode: 'approve', dryRun: false},
    {type: 'chat', prompt: 'x'.repeat(16001), mode: 'approve', dryRun: false},
    {type: 'chat', prompt: 'task', mode: 'approve', dryRun: 'yes'}]) {
    assert.throws(() => parseRequest(input));
  }
});

test('diagnostics are fixed commands without model/source-sharing flags', () => {
  for (const type of ['connect', 'login', 'probe', 'doctor', 'history']) {
    const invocation = buildInvocation('C:\\Python\\python.exe', 'C:\\repo', parseRequest({type}));
    assert.equal(invocation.args.at(-1), type);
    assert.ok(!invocation.args.includes('--share-code'));
  }
});

test('guided setup uses only the fixed connect command and Windows handoff flag', () => {
  const request = parseRequest({type: 'edge-setup'});
  const invocation = buildInvocation('C:\\Python\\python.exe', 'C:\\repo', request);
  assert.deepEqual(invocation.args.slice(-2), ['connect', '--open-edge']);
});
