# Can I run PilotPatch on my office laptop?

The supported target is Windows 11 x64 with approved 64-bit CPython 3.11–3.13,
Git, Microsoft Edge 120 or newer and a local VS Code installation for the chat panel.
Your organization must allow the extension, the loopback connection, browser automation
and use of the intended Microsoft Copilot account for your project.

## Install it

Transfer the `PilotPatch-Office-0.5.1.zip` produced by `build.cmd` through your
approved route. Extract it to a local folder you can write to, such as
`%LOCALAPPDATA%\Programs\PilotPatch`. The bundle contains the Python dependency wheels,
the VSIX and the source build files. Set up a fresh environment and pairing on each laptop.

In PowerShell, from the extracted folder:

```powershell
.\setup-windows.ps1 -InstallEditor -OpenEdgeSetup
```

Setup uses the included wheels and VSIX. If your editor policy requires manual installation,
run setup without `-InstallEditor` and use the approved process to install the VSIX.
For script restrictions, see the [manual setup commands](../setup.md#2-install-the-python-backend).

## Check the actual laptop

| Check | What it verifies |
| --- | --- |
| `copilot.cmd --project 'C:\Work\Project' doctor --offline` | Python dependencies, executable Git, project access and Edge installation. |
| **Open Edge setup** in VS Code | Opens Extensions and copies the folder path. The panel guides installation and pairing in the intended profile. |
| **Test connection** | Sends a short message with no project files and verifies the full reply on that laptop and account. |
| A task in an approved disposable repository | Checks source-sharing consent, edits and command approvals under the actual setup. |

If Edge won't enable Developer mode or load the unpacked extension, check
`edge://policy` and use your organization's approved installation route. PilotPatch
uses extension ID `jhmhehhjehmldcehodmlbopiajhcghki` and loopback port `127.0.0.1:57423`.
Microsoft 365 Copilot access alone does not establish support for the public
Copilot Web adapter. [Microsoft Edge extension policies](https://learn.microsoft.com/en-us/deployedge/microsoft-edge-manage-extensions-policies)

Use a normal local directory for your project. Managed sync folders and reparse
points can prevent repository reads and writes. Offline checks on the development
machine don't establish managed-device or account access.
