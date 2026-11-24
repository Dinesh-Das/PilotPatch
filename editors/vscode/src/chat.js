'use strict';
const os = require('node:os');
const {spawn} = require('node:child_process');
const readline = require('node:readline');

function startChat(invocation, request, onMessage, onClose) {
  const child = spawn(invocation.executable, invocation.args, {
    cwd: os.tmpdir(), windowsHide: true, stdio: ['pipe', 'pipe', 'ignore'],
  });
  let error;
  child.on('error', failure => {error = failure.message;});
  child.stdin.on('error', () => {}); // A finished backend can close its end before a click arrives.
  const output = readline.createInterface({input: child.stdout, crlfDelay: Infinity});
  output.on('line', line => {
    let message;
    try {message = JSON.parse(line);} catch {return;}
    if (message && typeof message === 'object') onMessage(message);
  });
  child.on('close', (code, signal) => onClose(code, error || signal));
  const write = value => {
    if (!child.stdin.destroyed && !child.stdin.writableEnded) {
      child.stdin.write(`${JSON.stringify(value)}\n`, 'utf8');
    }
  };
  write(request);
  return {decide: write, stop: () => child.stdin.end()};
}

module.exports = {startChat};
