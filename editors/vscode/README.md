# PilotPatch for VS Code

PilotPatch lets you chat about a local project with Microsoft Copilot Web through
the Edge profile and tab you choose. Replies, source-sharing confirmations, proposed
changes and command approvals all appear in the sidebar.

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
replies, ask a question or request a change and click **Send** or press **Ctrl+Enter**.
Click **Share and send** to confirm source sharing for that message.

If the panel cannot find the backend, rerun Windows setup. For a manually installed
backend, choose **Select installed Python** and pick its `.venv\Scripts\python.exe`.
You can override the registered backend in User Settings with `pilotpatch.pythonPath`.

For Cursor or another compatible local desktop fork, build with `build.cmd`, run
`setup-windows.ps1` to register the backend, then use **Extensions → … → Install from VSIX…**
and choose the VSIX in `artifacts`. Windows local workspaces must be trusted.

Read the full setup guide for troubleshooting, managed laptop checks and CLI usage.
[PilotPatch setup guide](https://github.com/Dinesh-Das/PilotPatch/blob/main/setup.md)

## Chat controls

**Permissions and preview** changes how file edits and commands are approved. **Preview only**
proposes changes without writing them or running tests. **Change project** appears
in multi-root workspaces. **Stop message** stops the active turn. Inspect Edge and
your project before retrying an interrupted turn.

The sidebar holds a recent conversation per project while the VS Code window is open.
Follow-ups include recent successful exchanges within the context budget. **Clear
conversation** clears the sidebar history for the current project. Start a new chat
in the selected Copilot tab to clear the remote conversation too. Drafts are stored
in the editor’s local webview state. Chat messages travel to the backend through a
local pipe. The backend applies source-sharing consent before sending project context.

## Build and test

From the repository root, run `build.cmd`. It produces the VSIX under `artifacts`.
Run `node --test editors/vscode/test/*.test.js` with Node.js 20 or newer for editor
unit tests. Use the Python suite for real-browser webview checks.
