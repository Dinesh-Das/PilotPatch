'use strict';
const vscode = require('vscode');
const {Controller} = require('./controller');
const {renderPanel} = require('./panel');

function activate(context) {
  let view;
  const controller = new Controller(vscode, state => view?.webview.postMessage({type: 'state', ...state}));
  context.subscriptions.push(controller);
  context.subscriptions.push(vscode.window.registerWebviewViewProvider('pilotpatch.promptView', {
    resolveWebviewView(resolved) {
      view = resolved;
      view.webview.options = {enableScripts: true,
        localResourceRoots: [vscode.Uri.joinPath(context.extensionUri, 'media')]};
      view.webview.html = renderPanel(view.webview, context.extensionUri, vscode.Uri);
      context.subscriptions.push(view.webview.onDidReceiveMessage(message => controller.handle(message)));
      context.subscriptions.push(view.onDidChangeVisibility(() => controller.publish()));
    },
  }));
  for (const [command, type] of Object.entries({
    'pilotpatch.configure': 'configure', 'pilotpatch.login': 'login',
    'pilotpatch.probe': 'probe', 'pilotpatch.doctor': 'doctor',
  })) context.subscriptions.push(vscode.commands.registerCommand(command, () => controller.handle({type})));
  context.subscriptions.push(vscode.commands.registerCommand('pilotpatch.open', async () => {
    await vscode.commands.executeCommand('workbench.view.extension.pilotpatch');
    controller.publish();
  }));
  return {controller};
}

module.exports = {activate};
