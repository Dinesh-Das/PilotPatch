import argparse
import asyncio
import importlib.metadata
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml
from filelock import FileLock, Timeout

from pilotpatch import __version__
from pilotpatch.agent.loop import AgentLoop
from pilotpatch.agent.state import SessionStore
from pilotpatch.browser.bridge import pairing
from pilotpatch.config import Config, default_home, load_config
from pilotpatch.providers.factory import browser_provider
from pilotpatch.security.permissions import Permissions
from pilotpatch.security.redaction import redact
from pilotpatch.security.storage import atomic_bytes, atomic_json, private_directory
from pilotpatch.security.system import windows_binary
from pilotpatch.tools.command_runner import CommandRunner
from pilotpatch.tools.filesystem import FileTools
from pilotpatch.tools.registry import ToolRegistry
from pilotpatch.tools.repository import Repository
from pilotpatch.ui import terminal as ui
from pilotpatch.ui.editor import EditorConsole

COMMANDS = {
    "login",
    "logout",
    "status",
    "probe",
    "run",
    "resume",
    "diff",
    "history",
    "config",
    "doctor",
    "connect",
    "register-editor",
    "editor-chat",
}


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        prog="copilot-agent", description="PilotPatch — Microsoft Copilot-only local coding agent"
    )
    result.add_argument("--version", action="version", version=f"PilotPatch {__version__}")
    # One parser permits options before or after a subcommand and supports a quoted
    # task directly: copilot-agent --project path "Implement a health endpoint".
    result.add_argument("--project", type=Path, default=Path.cwd())
    result.add_argument(
        "--home", type=Path, default=default_home(), help="Private local state directory"
    )
    result.add_argument(
        "--config", dest="config_path", type=Path, help="Explicit operator-owned YAML"
    )
    result.add_argument("--mode", choices=["read-only", "approve", "auto-edit"])
    result.add_argument(
        "--browser-connection",
        choices=["existing-edge", "managed-edge"],
        help="Default: existing Edge tab through the PilotPatch extension",
    )
    result.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview edits; do not write project files or run commands",
    )
    result.add_argument(
        "--share-code",
        action="store_true",
        help="Explicitly authorize this task's source context to Microsoft Copilot",
    )
    result.add_argument("--max-steps", type=int)
    result.add_argument(
        "--resolve-pending",
        choices=["skip"],
        help="After manual review, mark an interrupted action unknown; never replay it",
    )
    result.add_argument(
        "--offline", action="store_true", help="doctor: skip network/browser navigation"
    )
    result.add_argument(
        "--open-edge",
        action="store_true",
        help="connect: open Edge Extensions and copy the unpacked extension folder on Windows",
    )
    result.add_argument("--init", action="store_true", help="config: write a default global config")
    result.add_argument("command_or_task", nargs="?")
    result.add_argument("arguments", nargs="*")
    return result


def _consent(args, confirm):
    if not args.share_code and not confirm(
        "Send selected repository source, project instructions and tool results for this task to "
        "Microsoft Copilot at https://copilot.com/ using the account in the selected "
        "Edge connection? Confirm your organization permits this destination and account"
    ):
        raise PermissionError(
            "Source sharing declined. Use --share-code only when explicitly authorized"
        )


async def _task(args, config, store, state, *, resume=False, output=ui, conversation=None):
    if output is ui:
        _consent(args, ui.confirm)
    project = Path(state["project"])
    if output is ui:
        ui.banner(project)
        ui.event(f"Session: {state['id']}")
    permissions = Permissions(config.permission_mode, output.confirm)
    repo = Repository(project, config)
    session_dir = store.directory(state["id"])
    lock = store.task_lock(state["id"])
    provider = browser_provider(args.home, config)
    try:
        with lock:
            if resume:
                state = store.load(state["id"])
            if output is not ui:
                output.event("Connecting to your selected Copilot chat in Edge…")
            await provider.open()
            status = await provider.status()
            if output is ui:
                ui.event(f"Microsoft session: {status}")
            if not status["chat_ready"]:
                raise RuntimeError(
                    "Copilot chat is not ready. In Edge, open the selected chat and check your "
                    "Microsoft sign-in. Run Test connection before retrying."
                )
            files = FileTools(
                repo, session_dir, permissions, dry_run=state["dry_run"], preview=output.preview
            )
            tools = ToolRegistry(files, CommandRunner(repo, permissions, state["dry_run"]))
            loop = AgentLoop(provider, tools, store, state, output.event)
            result = await loop.run(
                resume=resume,
                resolve_pending=args.resolve_pending == "skip",
                conversation=conversation,
            )
    except Timeout as exc:
        raise RuntimeError("This task is already running in another process") from exc
    finally:
        await provider.close()
    return result


async def _editor_chat(args, config, store) -> int:
    output = EditorConsole(dry_run=args.dry_run)
    state = None
    try:
        if args.arguments or args.share_code:
            raise ValueError("Editor messages and source approvals must come from the editor")
        request = output.start()
        if not output.confirm(
            "Send your message, recent conversation, selected project files, instructions and "
            "tool results to Microsoft Copilot Web? Confirm your organization permits sharing "
            "with this destination and the account in the selected Edge chat.",
            source=True,
        ):
            output.emit("declined", message="Message was not sent. Source sharing was declined.")
            return 0
        Repository(args.project, config)
        state = store.create(args.project, request.prompt, args.dry_run)
        output.emit("session", id=state["id"])
        result = await _task(
            args,
            config,
            store,
            state,
            output=output,
            conversation=[exchange.model_dump() for exchange in request.conversation],
        )
        output.emit("reply", result=result)
        return 0
    except asyncio.CancelledError:
        output.emit("stopped", message="Stopped. Review the selected Edge chat and local changes.")
        return 130
    except Exception as exc:
        # Validation errors can embed the full input including a user's draft.
        from pydantic import ValidationError

        message = "Invalid editor chat request" if isinstance(exc, ValidationError) else str(exc)
        output.emit("error", message=message)
        return 1


async def _browser_command(command, args, config):
    provider = browser_provider(args.home, config)
    try:
        if config.browser_connection == "existing-edge":
            ui.event(
                "Connecting to your selected Copilot tab in existing Edge. "
                "Keep it open; the PilotPatch extension connects automatically."
            )
        await provider.open()
        if command == "login":
            ui.event(
                "Checking your selected Copilot tab. If needed, sign in manually there, "
                "including MFA. Waiting up to 10 minutes."
            )

            def login_progress(status):
                messages = {
                    "manual_authentication_required": (
                        "Waiting for Microsoft sign-in to return to Copilot…"
                    ),
                    "sign_in_required": (
                        "Copilot still shows Sign in. Complete sign-in in this Edge profile."
                    ),
                    "waiting_for_copilot_chat": (
                        "Waiting for the Copilot page and account controls to load…"
                    ),
                    "account_control_not_recognized": (
                        "Copilot chat is visible. If already signed in, open Copilot's account "
                        "menu so its signed-in controls can be detected."
                    ),
                    "multiple_copilot_tabs": (
                        "Multiple signed-in Copilot tabs found. Keep only the intended tab open."
                    ),
                }
                message = messages.get(status["state"])
                if message:
                    ui.event(message)

            status = await provider.login(on_status=login_progress)
            ui.event("Microsoft sign-in detected. Your Edge connection is ready.")
            if status["state"] == "service_error":
                ui.event(
                    "Copilot is signed in but shows a request/service error. After the login "
                    "task ends, use Test connection to check whether the service has recovered."
                )
            elif not status["chat_ready"]:
                ui.event(
                    "The account is signed in, but the chat input is not ready or recognized. "
                    "Check the page and selectors.composer before running a task."
                )
            else:
                ui.event(
                    "Chat controls are ready. Use Test connection to verify a real Copilot reply."
                )
            ui.event(str(status))
        elif command == "status":
            # Give the client-rendered page a short, bounded opportunity to initialize.
            for _ in range(10):
                status = await provider.status()
                if status["authenticated"]:
                    break
                await asyncio.sleep(0.5)
            ui.event(json.dumps(status, indent=2))
            return 0 if status["chat_ready"] else 2
        elif command == "probe":
            from secrets import token_hex

            ui.event("Edge connected. Testing the selected Copilot chat and waiting for a reply.")
            nonce = token_hex(8)
            token = f"PILOTPATCH_OK_{nonce}"
            response = await provider.send(
                f"Harmless connectivity test. Reply with this exact token and no other text:\n"
                f"{token}"
            )
            if response.strip() not in (token, token + "."):
                raise RuntimeError("Received a live response but it did not match the probe nonce")
            ui.event(
                "Live Copilot communication verified: submitted a nonce and retrieved "
                "its complete response."
            )
    finally:
        await provider.close()
    return 0


def _logout(home: Path, config: Config):
    if config.browser_connection == "existing-edge":
        with FileLock(home / "browser.lock", timeout=0):
            (home / "edge-pairing.json").unlink(missing_ok=True)
        ui.event(
            "Removed PilotPatch pairing. Disconnect in the Edge extension too. "
            "Your Edge tabs and Microsoft sign-in were left intact."
        )
        return
    root = home.resolve()
    profile = home / "edge-profile"
    marker = profile / "pilotpatch-owned.json"
    with FileLock(home / "browser.lock", timeout=0):
        if not profile.exists():
            ui.event("No local PilotPatch browser profile exists.")
            return
        if (
            profile.is_symlink()
            or not profile.resolve().is_relative_to(root)
            or profile.resolve() == root
            or not marker.is_file()
            or json.loads(marker.read_text())["owner"] != "PilotPatch"
        ):
            raise ValueError("Refusing to delete an unrecognized browser profile")
        shutil.rmtree(profile)
    ui.event(
        "Removed the dedicated local Edge profile. Manage server-side session revocation "
        "in your Microsoft account."
    )


async def _doctor(args, config):
    results = {
        "python": sys.version.split()[0],
        "git": False,
        "project_readable": args.project.is_dir() and os.access(args.project, os.R_OK),
        "project_writable": None,
        "provider": config.provider,
        "browser_connection": config.browser_connection,
        "alternative_models": False,
        "telemetry": False,
    }
    try:
        # Use the same trusted Git resolution as repository operations, and actually
        # start it so a PATH entry blocked by laptop policy cannot pass this check.
        results["git_version"] = Repository(args.project, config)._git(["--version"]).strip()
        results["git"] = True
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        results["git_error"] = redact(str(exc))
    if config.permission_mode != "read-only":
        # os.access on Windows does not establish NTFS ACL write permission. Probe
        # only a uniquely owned temporary file; never overwrite project content.
        results["project_writable"] = False
        if os.access(args.project, os.W_OK):
            try:
                with tempfile.TemporaryFile(
                    dir=args.project, prefix=".pilotpatch-doctor-"
                ) as probe:
                    probe.write(b"PilotPatch write check")
                    probe.flush()
                results["project_writable"] = True
            except OSError:
                pass
    for name in ["playwright", "pydantic", "rich", "pathspec", "filelock", "PyYAML"]:
        results[name] = importlib.metadata.version(name)
    results["edge_found"] = _installed_edge() is not None or bool(shutil.which("msedge"))
    if not args.offline:
        session = browser_provider(args.home, config)
        try:
            await session.open()
            results["edge_initialization"] = True
            status = await session.status()
            results["chat_ready"] = status["chat_ready"]
            results["copilot_state"] = status.get("state")
            results["live_reply_verified"] = False
        except Exception as exc:
            results["browser_error"] = redact(str(exc))
        finally:
            await session.close()
    ui.event(json.dumps(results, indent=2))
    return (
        0
        if results["git"]
        and results["project_readable"]
        and (results["project_writable"] or config.permission_mode == "read-only")
        and results["edge_found"]
        and "browser_error" not in results
        and (args.offline or results.get("chat_ready") is True)
        else 2
    )


def _installed_edge() -> Path | None:
    roots = (
        os.environ.get("PROGRAMFILES(X86)", "C:/Program Files (x86)"),
        os.environ.get("PROGRAMFILES", "C:/Program Files"),
        os.environ.get("LOCALAPPDATA", ""),
    )
    paths = (Path(root) / "Microsoft/Edge/Application/msedge.exe" for root in roots)
    return next((path for path in paths if path.is_absolute() and path.is_file()), None)


def _registered_edge() -> Path | None:
    # Use Windows' application registration for launch. The project and PATH
    # cannot provide a replacement executable.
    import winreg

    key = r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe"
    for registry in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        try:
            with winreg.OpenKey(registry, key) as entry:
                value, _ = winreg.QueryValueEx(entry, "")
            if isinstance(value, str):
                path = Path(value)
                if path.is_absolute() and path.is_file():
                    return path
        except OSError:
            continue
    return None


def _open_edge_setup(folder: Path):
    if sys.platform != "win32":
        ui.event("Open edge://extensions and use the folder printed above.")
        return
    try:
        subprocess.run(
            [windows_binary("clip.exe")],
            input=str(folder).encode("utf-16"),
            capture_output=True,
            check=True,
            timeout=5,
        )
        ui.event(
            "Folder copied. In the Load unpacked dialog, press Ctrl+L, Ctrl+V and Enter. "
            "Then click Select Folder."
        )
    except (OSError, subprocess.SubprocessError):
        ui.event("Clipboard unavailable. Paste the folder printed above into Load unpacked.")

    edge = _registered_edge()
    if edge is None:
        ui.event("Open your Edge profile yourself and go to edge://extensions.")
        return
    try:
        subprocess.Popen(
            [str(edge), "edge://extensions/"],
            cwd=edge.parent,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.DETACHED_PROCESS,
        )
    except OSError:
        ui.event("Edge could not open from here. Go to edge://extensions in your intended profile.")


def _connect(home: Path, *, open_edge: bool = False):
    try:
        with FileLock(home / "browser.lock", timeout=0):
            _prepare_connection(home)
    except Timeout as exc:
        raise RuntimeError("Stop the active PilotPatch task before preparing Edge setup.") from exc
    if open_edge:
        _open_edge_setup(home / "edge-extension")


def _prepare_connection(home: Path):
    pairing(home, create=True)
    source = Path(__file__).resolve().parent / "edge_extension"
    if not source.is_dir():
        source = Path(__file__).resolve().parent.parent / "editors" / "edge"
    destination = home / "edge-extension"
    # Copy only packaged extension assets to a stable location for Load unpacked.
    destination.mkdir(exist_ok=True)
    for name in (
        "manifest.json",
        "background.js",
        "connection.js",
        "content.js",
        "popup.html",
        "popup.css",
        "popup.js",
    ):
        atomic_bytes(destination / name, (source / name).read_bytes())
    ui.console.print(
        "In the Edge profile you want to use:\n"
        "1. Go to edge://extensions, enable Developer mode and click Load unpacked.\n"
        "   Paste this folder path into the picker. It contains manifest.json.\n"
        f"   {destination}\n"
        "   If PilotPatch is already installed from this folder, click Reload on its card.\n"
        "2. Open PilotPatch from Edge's Extensions menu. If asked for a pairing file, use:\n"
        f"   {home / 'edge-pairing.json'}\n"
        "3. Open Copilot in this Edge profile and sign in. In the extension, click Use this tab.\n"
        "   Choose the intended tab if several are open.\n"
        "4. Run probe (Test connection in VS Code) and keep the tab open.\n"
        "Keep the pairing file private.",
        markup=False,
        soft_wrap=True,
    )


async def dispatch(args) -> int:
    command = args.command_or_task
    if command is None:
        parser().print_help()
        return 0
    if args.open_edge and command != "connect":
        raise ValueError("--open-edge is available with connect")
    args.home = args.home.expanduser().resolve()
    # State must not be placed inside a repository which the agent can read/share.
    project = args.project.expanduser().resolve()
    args.project = project
    if args.home.is_relative_to(project):
        raise ValueError(
            "--home must be outside the project to isolate browser credentials and backups"
        )
    private_directory(args.home)
    if command == "register-editor":
        registration = args.home / "editor-backend.json"
        atomic_json(registration, {"python": str(Path(sys.executable))})
        ui.console.print(
            f"Saved VS Code backend registration to {registration}", markup=False, soft_wrap=True
        )
        return 0
    config = load_config(args.config_path or args.home / "config.yaml")
    overrides = config.model_dump()
    if args.browser_connection:
        overrides["browser_connection"] = args.browser_connection
    if args.mode:
        overrides["permission_mode"] = args.mode
    if args.max_steps is not None:
        overrides["max_steps"] = args.max_steps
    config = Config.model_validate(overrides)
    if command in {"login", "status", "probe"}:
        return await _browser_command(command, args, config)
    if command == "logout":
        _logout(args.home, config)
        return 0
    if command == "connect":
        _connect(args.home, open_edge=args.open_edge)
        return 0
    if command == "doctor":
        return await _doctor(args, config)
    if command == "config":
        target = args.config_path or args.home / "config.yaml"
        if args.init:
            if target.exists():
                raise ValueError("Configuration already exists; edit it explicitly")
            atomic_bytes(target, yaml.safe_dump(Config().model_dump(), sort_keys=False).encode())
            ui.event(f"Created operator configuration: {target}")
        else:
            ui.event(redact(yaml.safe_dump(config.model_dump(), sort_keys=False)))
        return 0
    store = SessionStore(args.home)
    store.prune(config.retention_days)
    if command == "editor-chat":
        return await _editor_chat(args, config, store)
    if command == "history":
        ui.event(json.dumps(store.history(), indent=2))
    elif command == "diff":
        if args.arguments:
            state = store.load(args.arguments[0])
            for receipt in state["receipts"].values():
                result = receipt["result"].get("result", {})
                if result.get("diff"):
                    ui.preview(result["diff"])
        else:
            ui.preview(Repository(project, config).git_diff()["output"])
    elif command == "resume":
        if len(args.arguments) != 1:
            raise ValueError("Usage: copilot-agent resume SESSION_ID")
        state = store.load(args.arguments[0])
        resumed_project = await asyncio.to_thread(Path(state["project"]).resolve)
        if args.home.is_relative_to(resumed_project):
            raise ValueError("State directory must be outside resumed project")
        ui.report(await _task(args, config, store, state, resume=True))
    else:
        task = " ".join(args.arguments if command == "run" else [command, *args.arguments]).strip()
        if not task:
            raise ValueError("Provide a task instruction")
        Repository(project, config)  # Validate before creating persistent task state.
        state = store.create(project, task, args.dry_run)
        ui.report(await _task(args, config, store, state))
    return 0


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    try:
        args = parser().parse_intermixed_args(argv)
        code = asyncio.run(dispatch(args))
    except KeyboardInterrupt:
        ui.event("Cancelled. Local state was saved; inspect history before resuming.")
        code = 130
    except Exception as exc:
        ui.console.print(f"PilotPatch: {redact(str(exc))}", style="red", markup=False)
        code = 1
    raise SystemExit(code)
