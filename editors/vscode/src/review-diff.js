'use strict';
const path = require('node:path');

function createReviewDiffs(vscode) {
  const scheme = 'pilotpatch-review';
  const documents = new Map();
  const registration = vscode.workspace.registerTextDocumentContentProvider(scheme, {
    provideTextDocumentContent: uri => documents.get(uri.toString()),
  });
  const closes = vscode.workspace.onDidCloseTextDocument(document => {
    if (document.uri.scheme === scheme) documents.delete(document.uri.toString());
  });

  return {
    async show(review, file, {before, after}) {
      const name = path.posix.basename(file.path);
      const uri = side => vscode.Uri.from({scheme, authority: review, path: `/${file.id}/${side}/${name}`});
      const original = uri('original');
      const proposed = uri('proposed');
      documents.set(original.toString(), before);
      documents.set(proposed.toString(), after);
      try {
        await vscode.commands.executeCommand('vscode.diff', original, proposed, `PilotPatch · ${file.path}`,
          {preview: true});
      } catch (error) {
        documents.delete(original.toString());
        documents.delete(proposed.toString());
        throw error;
      }
    },
    dispose() {
      closes.dispose();
      registration.dispose();
      documents.clear();
    },
  };
}

module.exports = {createReviewDiffs};
