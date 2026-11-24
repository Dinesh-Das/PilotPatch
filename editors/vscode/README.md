# PilotPatch for VS Code

PilotPatch sends tasks from a local project to Microsoft Copilot Web through the
Edge profile and tab you choose. The VS Code terminal shows what will be shared,
proposed changes, command approvals and the actual results.

## Start on Windows

From the PilotPatch folder in PowerShell, run:

```powershell
.\setup-windows.ps1 -InstallEditor -OpenEdgeSetup
```

Open your project folder in VS Code, click **PilotPatch** in the activity bar,
and choose **Open Edge setup** if the extension still needs installing. It opens
Edge Extensions and copies the folder path. The panel also lets you copy the pairing
file path. In the Edge extension,
click **Use this tab**. Back in VS Code, click **Test connection**. When Copilot
replies, enter a task and click **Run task** or press **Ctrl+Enter**.

If the panel cannot find the backend, rerun Windows setup. For a manually installed
backend, choose **Select installed Python** and pick its `.venv\Scripts\python.exe`.
You can override the registered backend in User Settings with `pilotpatch.pythonPath`.

For Cursor or another compatible local desktop fork, build with `build.cmd`, run
`setup-windows.ps1` to register the backend, then use **Extensions → … → Install from VSIX…**
and choose the VSIX in `artifacts`. Windows local workspaces must be trusted.

Read the full setup guide for troubleshooting, managed laptop checks and CLI usage.
[PilotPatch setup guide](https://github.com/Dinesh-Das/PilotPatch/blob/main/setup.md)

## Task controls

**Task options** changes how file edits and commands are approved. **Preview only**
proposes changes without writing them or running tests. **Change project** appears
in multi-root workspaces. **Stop task** stops the task started in this window. Check
the terminal and saved session before resuming an interrupted edit.

Drafts are stored in the editor's local webview state. The prompt is visible in
the local task terminal and process arguments. The Python backend applies source-sharing
consent before sending project context.

## Build and test

From the repository root, run `build.cmd`. It produces the VSIX under `artifacts`.
Run `node --test editors/vscode/test/*.test.js` with Node.js 20 or newer for editor
unit tests. Use the Python suite for real-browser webview checks.
