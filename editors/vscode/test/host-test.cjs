'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vscode = require('vscode');

exports.run = async function () {
  const extension = vscode.extensions.getExtension('pilotpatch-local.pilotpatch');
  assert.ok(extension, 'PilotPatch must be registered in the actual editor host');
  const api = await extension.activate();
  assert.ok(api.controller);
  assert.equal(vscode.workspace.isTrusted, true);
  const commands = await vscode.commands.getCommands(true);
  assert.ok(commands.includes('pilotpatch.open'));
  assert.ok(commands.includes('pilotpatch.connect'));
  await vscode.commands.executeCommand('pilotpatch.open');
  const exit = new Promise((resolve, reject) => {
    const timer = setTimeout(() => {listener.dispose(); reject(new Error('Connect setup task did not finish'));}, 60000);
    const listener = vscode.tasks.onDidEndTaskProcess(event => {
      if (event.execution.task.definition.type === 'pilotpatch') {
        clearTimeout(timer); listener.dispose(); resolve(event.exitCode);
      }
    });
  });
  await api.controller.handle({type: 'connect'});
  assert.equal(await exit, 0, 'Real Python connect setup task must succeed');
  assert.equal(api.controller.state.phase, 'finished');
  await api.controller.openReviewDiff('e'.repeat(32), {id: 0, path: 'src/sample.py'},
    {before: 'value = 1\n', after: 'value = 2\n'});
  const diff = vscode.window.tabGroups.activeTabGroup.activeTab?.input;
  assert.ok(diff instanceof vscode.TabInputTextDiff, 'Review opens the native diff editor');
  assert.equal(diff.modified.scheme, 'pilotpatch-review');
  assert.equal((await vscode.workspace.openTextDocument(diff.original)).getText(), 'value = 1\n');
  assert.equal((await vscode.workspace.openTextDocument(diff.modified)).getText(), 'value = 2\n');
  const report = {editor: vscode.env.appName, version: vscode.version,
    activated: true, commandRegistered: true, connectExitCode: 0, verifiedReviewDiff: true,
    phase: api.controller.state.phase, workspace: api.controller.currentFolder().uri.fsPath};
  if (process.env.PILOTPATCH_EDITOR_REPORT) fs.writeFileSync(process.env.PILOTPATCH_EDITOR_REPORT, JSON.stringify(report, null, 2));
};
