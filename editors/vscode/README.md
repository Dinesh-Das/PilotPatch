# PilotPatch for VS Code

Enter a task in a dedicated PilotPatch panel and run the existing local harness
against your selected workspace. All runtime AI reasoning goes to **Microsoft
Copilot Web** through your selected tab in your existing Edge profile.

## Install

1. Set up the Python backend using the repository's `setup-windows.ps1`.
2. In VS Code, open Extensions, choose **… → Install from VSIX…**, and select the
   supplied `pilotpatch-0.2.1.vsix`.
3. Run **PilotPatch: Open Prompt Panel** from the command palette, or click the
   PilotPatch activity-bar icon.
4. Choose **Select backend Python**, then select the backend virtual environment's
   executable, for example `D:\MyProjects\PilotPatch\.venv\Scripts\python.exe`.
5. Open the project you want to work on. Use **Connect existing Edge** and follow
   the printed one-time extension install/pairing steps. Select your current Copilot
   tab in that Edge profile, then use **Sign in** and **Test connection**.
6. Type a task and choose **Run task** (Ctrl/Cmd+Enter). Review source-sharing
   consent, proposed diffs, command approvals and actual results in the task terminal.

The setting can also be supplied in **User Settings**:

```json
{
  "pilotpatch.pythonPath": "D:\\MyProjects\\PilotPatch\\.venv\\Scripts\\python.exe"
}
```

Workspace settings cannot select the executable. No source-sharing, edit or command
permission is silently granted by this extension. Permission modes and **Preview
only** are passed directly to the harness. The panel's **Finished** label means the
process exited zero; the terminal contains the actual Copilot and verification results.

## VS Code forks

The extension uses stable webview, workspace and process-task APIs. Compatible
desktop forks that support VSIX installation can use the same package. Install via
their **Install from VSIX…** action and select backend Python separately in that
editor's User Settings. Activation, panel registration and a real backend diagnostic
were verified in VS Code 1.141.2 and Cursor 3.20.17 (VS Code API 1.128.0).
The extension does not use GitHub Copilot Chat, Cursor AI,
Windsurf models or the editor's language-model APIs. Fork compatibility must be
verified in the specific version; not every fork has been tested.

Windows local workspaces are the primary target. Restricted/untrusted workspaces,
virtual filesystems and remote/WSL extension hosts are rejected before execution.
Multi-root windows can choose a target with the workspace **Change** action.

## Task controls and privacy

One PilotPatch process runs per editor window. Stop targets only that owned task;
inspect the terminal and saved backend session before resuming an interrupted edit.
VS Code's terminal Ctrl+C also works with the backend's cancellation handling.
Do not close the editor during an active task without checking its terminal.

The panel stores its draft using VS Code's local webview state and keeps a short
in-memory activity list. It makes no network requests. Task text is passed as a
single process argument, so shell syntax in a prompt is not interpreted. It is
visible in the task terminal/process arguments to the local OS user. The backend's
existing private state, redaction and retention policies apply. No telemetry or
runtime NPM dependencies are added.

## Development

Node.js 20+ is required for extension development and its Node tests.

```powershell
cd editors\vscode
npm test
# Use the official @vscode/vsce packaging tool with installation scripts disabled:
npm exec --ignore-scripts --package=@vscode/vsce -- vsce package --no-dependencies
```

For a development host: `code --extensionDevelopmentPath=PATH_TO_THIS_FOLDER PROJECT`.
Tests in `test/` cover strict requests, shell-free argv, trust/remote/duplicate-launch
rejection, terminal approvals and actual task lifecycle reporting. `host-test.cjs`
can be run through `--extensionTestsPath` for an isolated, real editor-host check.

The webview uses only local packaged assets, theme tokens and a restrictive CSP.
Account-bound Microsoft Copilot integration remains subject to the backend's separate
live acceptance tests and your organization's authorization.
