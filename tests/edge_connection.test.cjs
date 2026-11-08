const {test} = require('node:test');
const assert = require('node:assert/strict');
const {createHash} = require('node:crypto');
const fs = require('node:fs');
const connection = require('../editors/edge/connection');
const manifest = require('../editors/edge/manifest.json');

test('manifest has stable pairing identity and scoped permissions', () => {
  const id = [...createHash('sha256').update(Buffer.from(manifest.key, 'base64')).digest().subarray(0,16)]
    .flatMap(b => [b >> 4, b & 15]).map(n => String.fromCharCode(97 + n)).join('');
  assert.equal(id, 'jhmhehhjehmldcehodmlbopiajhcghki');
  assert.deepEqual(manifest.permissions, ['storage', 'alarms', 'scripting']);
  assert.equal(manifest.host_permissions.length, 4);
  assert.ok(manifest.host_permissions.every(p => !p.includes('<all_urls>') && !p.includes('https://*')));
  const source = fs.readFileSync('editors/edge/background.js', 'utf8');
  assert.ok(!source.includes('chrome.tabs.create'));
  assert.ok(!source.includes('chrome.windows.create'));
});

test('only exact public Copilot origins are eligible', () => {
  for (const url of ['https://copilot.com/chat', 'https://copilot.microsoft.com/']) assert.ok(connection.isCopilot(url));
  for (const url of ['http://copilot.com', 'https://copilot.com.attacker.test/',
    'https://attacker.test/?copilot.com', 'https://copilot.com:444/', 'https://user@copilot.com/', 'edge://settings']) {
    assert.equal(connection.isCopilot(url), false);
  }
});

test('pairing accepts a local token, never an arbitrary target or extension identity', () => {
  const pair = {version: 1, extension_id: 'expected', token: 'a'.repeat(64), port: 57423};
  assert.deepEqual(connection.validatePair(pair, 'expected'), pair);
  for (const edit of [{port: 80}, {token: 'wrong'}, {extension_id: 'other'}, {version: 2}]) {
    assert.throws(() => connection.validatePair({...pair, ...edit}, 'expected'));
  }
});

test('unauthenticated streaming response is capped before buffering the whole body', async () => {
  let cancelled = false;
  const response = new Response(new ReadableStream({
    pull(controller) { controller.enqueue(new Uint8Array(12)); },
    cancel() { cancelled = true; }
  }));
  await assert.rejects(connection.readBounded(response, 16), /oversized_response/);
  assert.equal(cancelled, true);
});
