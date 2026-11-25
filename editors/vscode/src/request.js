'use strict';
const path = require('node:path');
const actions = new Set(['ready', 'configure', 'workspace', 'open-folder', 'stop',
  'connect', 'edge-setup', 'login', 'probe', 'doctor', 'history', 'copy-extension', 'copy-pairing', 'clear-chat']);
const modes = new Set(['approve', 'read-only', 'auto-edit']);
const reviewId = value => typeof value === 'string' && /^[a-f0-9]{32}$/.test(value);
const fileId = value => Number.isInteger(value) && value >= 0 && value < 1000;

function parseRequest(input) {
  if (!input || typeof input !== 'object' || Array.isArray(input)) throw new Error('Invalid panel request.');
  if (input.type === 'chat') {
    if (Object.keys(input).some(key => !['type', 'prompt', 'mode', 'dryRun'].includes(key)) ||
        typeof input.prompt !== 'string' || !input.prompt.trim() || input.prompt.length > 16000 ||
        input.prompt.includes('\0') || !modes.has(input.mode) || typeof input.dryRun !== 'boolean') {
      throw new Error('Enter a message of up to 16,000 characters and select a valid permission mode.');
    }
    return {type: input.type, prompt: input.prompt.trim(), mode: input.mode, dryRun: input.dryRun};
  }
  if (input.type === 'decision') {
    if (Object.keys(input).length !== 3 || !reviewId(input.id) || typeof input.approved !== 'boolean') {
      throw new Error('Invalid approval decision.');
    }
    return {type: input.type, id: input.id, approved: input.approved};
  }
  if (input.type === 'review-open' || input.type === 'review-apply') {
    if (Object.keys(input).length === 3 && reviewId(input.id)) {
      if (input.type === 'review-open' && fileId(input.file)) {
        return {type: input.type, id: input.id, file: input.file};
      }
      if (input.type === 'review-apply' && Array.isArray(input.files) &&
          input.files.length > 0 && input.files.length <= 1000 && input.files.every(fileId)) {
        return {type: input.type, id: input.id, files: [...new Set(input.files)]};
      }
    }
    throw new Error('Invalid file review request.');
  }
  if (!actions.has(input.type) || Object.keys(input).length !== 1) throw new Error('Unknown panel action.');
  return {type: input.type};
}

function buildInvocation(executable, project, request) {
  for (const value of [executable, project]) {
    if (typeof value !== 'string' || value.includes('\0') ||
        !(path.isAbsolute(value) || path.win32.isAbsolute(value))) throw new Error('Select absolute local paths.');
  }
  // The target project's Python files and inherited PYTHONPATH cannot bootstrap
  // the backend before its consent and permission checks run.
  const args = ['-I', '-m', 'pilotpatch', '--project', project];
  if (request.type === 'chat') {
    args.push('--mode', request.mode);
    if (request.dryRun) args.push('--dry-run');
    args.push('editor-chat');
  } else if (request.type === 'edge-setup') {
    args.push('connect', '--open-edge');
  } else if (['connect', 'login', 'probe', 'doctor', 'history'].includes(request.type)) {
    args.push(request.type);
  } else throw new Error('This action does not launch a backend process.');
  return {executable, args, cwd: project};
}

module.exports = {parseRequest, buildInvocation};
