# PilotPatch for Microsoft Edge

PilotPatch connects the local backend to the Copilot tab you authorize in your current
Edge profile. Browser pairing stays in that profile. Tab selection lasts for the current
browser session.

1. Click **Open Edge setup** in VS Code or run `copilot.cmd connect --open-edge`.
   PilotPatch opens Extensions and copies the exact folder path.
2. In the intended Edge profile, open `edge://extensions`, enable **Developer mode** and
   choose **Load unpacked**. Press **Ctrl+L**, **Ctrl+V** and **Enter**, then click
   **Select Folder**. The copied path contains `manifest.json`. If the extension is
   already installed from this folder, choose **Reload** on its card.
3. From Edge's Extensions menu, open **PilotPatch**. Choose the private pairing file
   if asked. Open **Copilot** in that profile and sign in.
4. Click **Use this tab**. One open Copilot tab is already highlighted. If several
   are open, choose the one you intend to use.
5. In VS Code, click **Test connection**, or run `copilot.cmd probe`. If VS Code is
   waiting for Edge, open the PilotPatch toolbar popup to check for the local task.

The toolbar popup stays in the current window and offers **Open Copilot in a new tab**
if there is no Copilot chat in this profile. **Edge linked to VS Code** and the **ON**
badge indicate that the local bridge is active. **Copilot reply verified** shows the
time of the last successful test for the selected tab. It stays visible after the
test finishes. Confirm the intended tab again after an Edge restart.

Managed Edge may disable **Load unpacked** or block the extension or loopback connection.
Check your organization's approved installation route.
[Microsoft Edge sideloading documentation](https://learn.microsoft.com/en-us/microsoft-edge/extensions/getting-started/extension-sideloading)
