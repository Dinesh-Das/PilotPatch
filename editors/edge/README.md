# PilotPatch for Microsoft Edge

PilotPatch connects the local backend to the Copilot tab you authorize in your current
Edge profile. Browser pairing stays in that profile. Tab selection lasts for the current
browser session.

1. Windows setup prints the extension folder and pairing file. To see the paths again,
   click **Set up Copilot** in VS Code or run `copilot.cmd connect`.
2. In the intended Edge profile, open `edge://extensions`, enable **Developer mode** and
   choose **Load unpacked**. Paste the `edge-extension` folder path. That folder
   contains `manifest.json`. If the extension is already installed from this folder,
   choose **Reload** on its card.
3. From Edge's Extensions menu, open **PilotPatch**. Choose the private pairing file
   if asked. Open **Copilot** in that profile and sign in.
4. Click **Use this tab**. One open Copilot tab is already highlighted. If several
   are open, choose the one you intend to use.
5. In VS Code, click **Test connection**, or run `copilot.cmd probe`. Edge can take
   up to 30 seconds to reconnect. Click **Reconnect** in the popup while the test
   is running to wake it immediately.

**Connected to PilotPatch** and the **ON** badge indicate that the local bridge is
active. A successful connection test confirms Copilot replied. Keep the selected tab
open and leave its message box empty when starting a task. Confirm the intended tab
again after an Edge restart. Use **Disconnect this profile** to remove its pairing.

Managed Edge may disable **Load unpacked** or block the extension or loopback connection.
Check your organization's approved installation route.
[Microsoft Edge sideloading documentation](https://learn.microsoft.com/en-us/microsoft-edge/extensions/getting-started/extension-sideloading)
