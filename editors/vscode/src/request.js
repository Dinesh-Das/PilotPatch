'use strict';
const path = require('node:path');
const actions = new Set(['ready', 'configure', 'workspace', 'stop', 'login', 'probe', 'doctor', 'history']);
const modes = new Set(['approve', 'read-only', 'auto-edit']);

function parseRequest(input) {
  if (!input || typeof input !== 'object' || Array.isArray(input)) throw new Error('Invalid panel request.');
  if (input.type === 'run') {
    if (Object.keys(input).some(key => !['type', 'prompt', 'mode', 'dryRun'].includes(key)) ||
        typeof input.prompt !== 'string' || !input.prompt.trim() || input.prompt.length > 16000 ||
        input.prompt.includes('\0') || !modes.has(input.mode) || typeof input.dryRun !== 'boolean') {
      throw new Error('Enter a task of up to 16,000 characters and select a valid permission mode.');
    }
    return {type: 'run', prompt: input.prompt.trim(), mode: input.mode, dryRun: input.dryRun};
  }
  if (!actions.has(input.type) || Object.keys(input).length !== 1) throw new Error('Unknown panel action.');
  return {type: input.type};
}

function buildInvocation(executable, project, request) {
  for (const value of [executable, project]) {
    if (typeof value !== 'string' || value.includes('\0') ||
        !(path.isAbsolute(value) || path.win32.isAbsolute(value))) throw new Error('Select absolute local paths.');
  }
  const args = ['-m', 'pilotpatch', '--project', project];
  if (request.type === 'run') {
    args.push('--mode', request.mode);
    if (request.dryRun) args.push('--dry-run');
    args.push('run', request.prompt);
  } else if (['login', 'probe', 'doctor', 'history'].includes(request.type)) {
    args.push(request.type);
  } else throw new Error('This action does not launch a backend process.');
  return {executable, args, cwd: project};
}

module.exports = {parseRequest, buildInvocation};
