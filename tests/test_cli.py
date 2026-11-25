import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from pilotpatch.cli import parser


@pytest.mark.parametrize(
    "argv,task",
    [
        (["--project", "C:/Work space/repo", "Fix the bug"], "Fix the bug"),
        (["run", "Fix the bug", "--dry-run"], "run"),
        (["--share-code", "run", "Fix the bug"], "run"),
    ],
)
def test_cli_argument_forms(argv, task):
    assert parser().parse_intermixed_args(argv).command_or_task == task


def test_help_version_and_history_without_browser(tmp_path):
    environment = dict(os.environ, PYTHONIOENCODING="utf-8")
    for args in [["--help"], ["--version"], ["--home", str(tmp_path), "history"]]:
        result = subprocess.run(
            [sys.executable, "-m", "pilotpatch", *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=environment,
            timeout=15,
        )
        assert result.returncode == 0, result.stderr + result.stdout


def test_editor_registration_and_literal_prompt(tmp_path):
    project = tmp_path / "project"
    home = tmp_path / "private"
    project.mkdir()
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pilotpatch",
            "--home",
            str(home),
            "--project",
            str(project),
            "register-editor",
        ],
        capture_output=True,
        encoding="utf-8",
        timeout=15,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert json.loads((home / "editor-backend.json").read_text()) == {"python": sys.executable}
    args = parser().parse_intermixed_args(["run", "--", "--share-code"])
    assert args.arguments == ["--share-code"]
    assert not args.share_code


@pytest.mark.parametrize(
    "decision",
    [
        "decline-source",
        "decline-edit",
        "approve-edit",
        "preview",
        "stop",
        "stale",
        "select-files",
        "partial-error",
    ],
)
async def test_editor_chat_pipe_only_applies_an_approved_edit(tmp_path, decision):
    # All I/O is real except the Copilot provider, which is replaced only in this test process.
    bootstrap = """
import json
import sys
from pilotpatch import cli

class FixtureCopilot:
    async def open(self):
        pass
    async def close(self):
        pass
    async def status(self):
        return {'chat_ready': True}
    async def send(self, text):
        if text.startswith('You are Microsoft Copilot'):
            message = dict(type='tool_call', id='write1', tool='write_file',
                           arguments=dict(path='answer.py', content='answer = 42\\n'))
        elif '"staged": true' in text and '"id": "write1"' in text:
            message = dict(type='tool_call', id='write2', tool='replace_in_file',
                           arguments=dict(path='answer.py', old_text='42', new_text='43'))
        elif '"staged": true' in text and '"id": "write2"' in text:
            message = dict(type='tool_call', id='write3', tool='write_file',
                           arguments=dict(path='details.txt', content='Details\\n'))
        else:
            message = dict(type='final', summary='Here is what happened.', tests='',
                           files_changed=['answer.py'], remaining_issues=[])
        return json.dumps(message)

cli.browser_provider = lambda *_: FixtureCopilot()
original_apply = cli.FileTools.apply_change
decision = sys.argv.pop(1)
def fixture_apply(self, change):
    if decision == 'partial-error' and change.name == 'details.txt':
        raise OSError('Interrupted during write')
    return original_apply(self, change)
cli.FileTools.apply_change = fixture_apply
cli.main()
"""
    project = tmp_path / "project"
    project.mkdir()
    home = tmp_path / "private"
    child = await asyncio.create_subprocess_exec(
        sys.executable,
        "-B",
        "-I",
        "-c",
        bootstrap,
        decision,
        "--home",
        str(home),
        "--project",
        str(project),
        "--mode",
        "approve",
        *(["--dry-run"] if decision == "preview" else []),
        "editor-chat",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
    )

    async def read(kind):
        while line := await asyncio.wait_for(child.stdout.readline(), timeout=10):
            event = json.loads(line)
            if event["type"] == kind:
                return event
        pytest.fail(f"Chat pipe closed before event {kind}")

    async def send(value):
        child.stdin.write(json.dumps(value).encode() + b"\n")
        await child.stdin.drain()

    try:
        request = dict(prompt="Add the answer", conversation=[])
        if decision == "select-files":
            request["review_ui"] = True
        await send(request)
        source = await read("approval")
        assert source["source"] is True
        await send(dict(id=source["id"], approved=decision != "decline-source"))
        if decision == "decline-source":
            await read("declined")
            assert not list((home / "sessions").iterdir())
        elif decision == "preview":
            assert "+answer = 43" in (await read("preview"))["diff"]
            answer = await read("reply")
            assert answer["result"]["dry_run"] is True
            assert answer["result"]["files_changed"] == []
        else:
            session = await read("session")
            edit = await read("approval")
            assert edit["source"] is False
            assert edit["review"] is True
            if decision == "select-files":
                answer_file, details_file = edit["files"]
                assert answer_file["path"] == "answer.py"
                assert details_file["path"] == "details.txt"
                assert "+answer = 43" in answer_file["diff"]
                assert "+answer = 42" not in answer_file["diff"]
            else:
                assert "+answer = 43" in edit["diff"]
                assert "+answer = 42" not in edit["diff"]
            assert not (project / "answer.py").exists()
            assert not (project / "details.txt").exists()
            # A duplicate source-sharing acknowledgement cannot approve a file edit.
            await send(dict(id=source["id"], approved=True))
            if decision == "stop":
                child.stdin.close()
                await read("stopped")
                state = json.loads((home / "sessions" / session["id"] / "state.json").read_text())
                assert state["pending"] is None
            elif decision == "stale":
                (project / "details.txt").write_text("User changes")
                await send(dict(id=edit["id"], approved=True))
                error = await read("error")
                assert "changed during review" in error["message"]
                assert (project / "details.txt").read_text() == "User changes"
            elif decision == "select-files":
                await send(dict(id=edit["id"], open_file=answer_file["id"]))
                snapshot = await read("review_document")
                assert snapshot["before"] == ""
                assert snapshot["after"] == "answer = 43\n"
                await send(dict(id=edit["id"], selected=[9999]))
                assert (await read("review_error"))["id"] == edit["id"]
                assert not (project / "answer.py").exists()
                await send(dict(id=edit["id"], selected=[answer_file["id"]]))
                answer = await read("reply")
                assert answer["result"]["files_changed"] == ["answer.py"]
                assert answer["result"]["review_status"] == "partially_applied"
                assert not (project / "details.txt").exists()
            elif decision == "partial-error":
                await send(dict(id=edit["id"], approved=True))
                error = await read("error")
                assert error["files_changed"] == ["answer.py"]
                assert error["uncertain_file"] == "details.txt"
            else:
                await send(dict(id=edit["id"], approved=decision == "approve-edit"))
                answer = await read("reply")
                verified_files = ["answer.py", "details.txt"] if decision == "approve-edit" else []
                assert answer["result"]["files_changed"] == verified_files
                assert answer["result"]["review_status"] == (
                    "applied" if decision == "approve-edit" else "discarded"
                )
        assert await asyncio.wait_for(child.wait(), timeout=10) == {
            "stop": 130,
            "stale": 1,
            "partial-error": 1,
        }.get(decision, 0)
        assert (project / "answer.py").exists() is (
            decision in {"approve-edit", "select-files", "partial-error"}
        )
    finally:
        child.stdin.close()
        if child.returncode is None:
            child.kill()
            await child.wait()


async def test_login_reports_sign_in_separately_from_chat_service_error(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from pilotpatch import cli
    from pilotpatch.config import Config

    status = dict(
        authenticated=True,
        chat_ready=False,
        connection_verified=False,
        state="service_error",
        account="test account control",
    )

    async def login(*, on_status):
        on_status(dict(state="account_control_not_recognized"))
        return status

    provider = SimpleNamespace(open=AsyncMock(), close=AsyncMock(), login=login)
    monkeypatch.setattr(cli, "browser_provider", lambda *_: provider)
    messages = []
    monkeypatch.setattr(cli.ui, "event", messages.append)
    assert await cli._browser_command("login", SimpleNamespace(home=tmp_path), Config()) == 0
    assert any("sign-in detected" in message for message in messages)
    assert any("service error" in message for message in messages)
    assert not any("communication verified" in message for message in messages)
    provider.close.assert_awaited_once()


async def test_status_returns_failure_when_signed_in_but_chat_has_error(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from pilotpatch import cli
    from pilotpatch.config import Config

    provider = SimpleNamespace(
        open=AsyncMock(),
        close=AsyncMock(),
        status=AsyncMock(
            return_value=dict(authenticated=True, chat_ready=False, state="service_error")
        ),
    )
    monkeypatch.setattr(cli, "browser_provider", lambda *_: provider)
    monkeypatch.setattr(cli.ui, "event", lambda _: None)
    assert await cli._browser_command("status", SimpleNamespace(home=tmp_path), Config()) == 2


@pytest.mark.parametrize(
    "reply,matches",
    [
        ("PILOTPATCH_OK_fixture", True),
        ("PILOTPATCH_OK_fixture.", True),
        ("PILOTPATCH_OK_previous.", False),
        ("PILOTPATCH_OK_fixture. Additional prose", False),
    ],
)
async def test_probe_requires_the_current_nonce(tmp_path, monkeypatch, reply, matches):
    import secrets

    from pilotpatch import cli
    from pilotpatch.config import Config

    provider = cli.CopilotExistingEdge(tmp_path, Config())
    for name, method in (
        ("open", AsyncMock()),
        ("close", AsyncMock()),
        ("send", AsyncMock(return_value=reply)),
        ("record_probe_success", AsyncMock()),
    ):
        monkeypatch.setattr(provider, name, method)
    monkeypatch.setattr(cli, "browser_provider", lambda *_: provider)
    monkeypatch.setattr(secrets, "token_hex", lambda _: "fixture")
    args = SimpleNamespace(home=tmp_path)
    if matches:
        assert await cli._browser_command("probe", args, Config()) == 0
    else:
        with pytest.raises(RuntimeError, match="did not match the probe nonce"):
            await cli._browser_command("probe", args, Config())
    provider.send.assert_awaited_once()
    assert provider.record_probe_success.await_count == int(matches)


def test_connect_packages_assets_and_logout_preserves_profile(tmp_path, monkeypatch):
    from pilotpatch import cli
    from pilotpatch.browser.bridge import pairing
    from pilotpatch.config import Config

    messages = []
    monkeypatch.setattr(cli.ui.console, "print", lambda message, **_: messages.append(message))
    open_setup = Mock()
    monkeypatch.setattr(cli, "_open_edge_setup", open_setup)
    cli._connect(tmp_path)
    open_setup.assert_not_called()
    token = pairing(tmp_path)["token"]
    assert (tmp_path / "edge-extension" / "manifest.json").is_file()
    assert str(tmp_path / "edge-extension") in messages[0]
    assert "Load unpacked" in messages[0]
    assert "manifest.json" in messages[0]
    assert not any(token in message for message in messages)
    cli._connect(tmp_path, open_edge=True)
    open_setup.assert_called_once_with(tmp_path / "edge-extension")
    assert pairing(tmp_path)["token"] == token
    profile = tmp_path / "edge-profile"
    profile.mkdir()
    (profile / "keep.txt").write_text("do not touch")
    cli._logout(tmp_path, Config())
    assert (profile / "keep.txt").read_text() == "do not touch"
    assert not (tmp_path / "edge-pairing.json").exists()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows Edge and clipboard commands")
def test_guided_edge_setup_opens_fixed_page_and_copies_only_folder(tmp_path, monkeypatch):
    from pilotpatch import cli

    edge = tmp_path / "Browser with spaces" / "msedge.exe"
    folder = tmp_path / "Édge files"
    copy = Mock()
    start = Mock()
    monkeypatch.setattr(cli, "_registered_edge", lambda: edge)
    monkeypatch.setattr(cli.subprocess, "run", copy)
    monkeypatch.setattr(cli.subprocess, "Popen", start)
    cli._open_edge_setup(folder)
    assert copy.call_args.args == ([cli.windows_binary("clip.exe")],)
    assert copy.call_args.kwargs["input"].decode("utf-16") == str(folder)
    assert start.call_args.args == ([str(edge), "edge://extensions/"],)
    assert start.call_args.kwargs["cwd"] == edge.parent


@pytest.mark.parametrize(
    "offline,chat_ready,writable,mode,expected",
    [
        (False, False, True, "approve", 2),
        (False, True, True, "approve", 0),
        (True, False, False, "approve", 2),
        (True, False, False, "read-only", 0),
    ],
)
async def test_doctor_requires_usable_project_and_chat(
    tmp_path, monkeypatch, offline, chat_ready, writable, mode, expected
):
    from pilotpatch import cli
    from pilotpatch.config import Config

    provider = SimpleNamespace(
        open=AsyncMock(),
        close=AsyncMock(),
        status=AsyncMock(return_value={"chat_ready": chat_ready}),
    )
    monkeypatch.setattr(cli, "browser_provider", lambda *_: provider)
    monkeypatch.setattr(cli.Repository, "_git", lambda *_: "git version test")
    monkeypatch.setattr(cli.shutil, "which", lambda _: sys.executable)
    monkeypatch.setattr(cli.os, "access", lambda _, mode: writable if mode == os.W_OK else True)
    messages = []
    monkeypatch.setattr(cli.ui, "event", messages.append)
    args = SimpleNamespace(project=tmp_path, home=tmp_path / "state", offline=offline)
    assert await cli._doctor(args, Config(permission_mode=mode)) == expected
    result = json.loads(messages[-1])
    assert result["project_writable"] is (None if mode == "read-only" else writable)
    if offline:
        provider.open.assert_not_awaited()
    else:
        assert result["live_reply_verified"] is False
        provider.close.assert_awaited_once()


async def test_doctor_rejects_git_inside_target_project(tmp_path, monkeypatch):
    from pilotpatch import cli
    from pilotpatch.config import Config

    local_git = tmp_path / "git.exe"
    local_git.write_bytes(b"not a trusted Git executable")
    monkeypatch.setattr(
        cli.shutil, "which", lambda name: str(local_git) if name == "git" else sys.executable
    )
    monkeypatch.setattr(cli.ui, "event", lambda _: None)
    args = SimpleNamespace(project=tmp_path, home=tmp_path / "state", offline=True)
    assert await cli._doctor(args, Config()) == 2


async def test_doctor_detects_write_denial_even_when_access_reports_writable(tmp_path, monkeypatch):
    import tempfile

    from pilotpatch import cli
    from pilotpatch.config import Config

    def denied(**_):
        raise PermissionError("NTFS ACL denies create")

    monkeypatch.setattr(tempfile, "TemporaryFile", denied)
    monkeypatch.setattr(cli.os, "access", lambda *_: True)
    monkeypatch.setattr(cli.Repository, "_git", lambda *_: "git version test")
    monkeypatch.setattr(cli.shutil, "which", lambda _: sys.executable)
    messages = []
    monkeypatch.setattr(cli.ui, "event", messages.append)
    args = SimpleNamespace(project=tmp_path, home=tmp_path / "state", offline=True)
    assert await cli._doctor(args, Config()) == 2
    assert json.loads(messages[-1])["project_writable"] is False


@pytest.mark.parametrize("use_pythonpath", [False, True])
def test_editor_backend_ignores_project_modules_and_pythonpath(tmp_path, use_pythonpath):
    root = Path(__file__).resolve().parents[1]
    project = tmp_path / "Office project"
    project.mkdir()
    (project / "pilotpatch.py").write_text("raise SystemExit(87)\n")
    pythonpath = tmp_path / "pythonpath"
    pythonpath.mkdir()
    (pythonpath / "sitecustomize.py").write_text("raise SystemExit(88)\n")
    invocation = subprocess.run(
        [
            "node",
            "-e",
            "process.stdout.write(JSON.stringify(require('./src/request').buildInvocation("
            "process.argv[1], process.argv[2], {type:'history'})))",
            sys.executable,
            str(project),
        ],
        cwd=root / "editors/vscode",
        capture_output=True,
        encoding="utf-8",
        check=True,
        timeout=15,
    )
    command = json.loads(invocation.stdout)
    result = subprocess.run(
        [command["executable"], *command["args"], "--home", str(tmp_path / "state")],
        cwd=command["cwd"],
        env=dict(os.environ, PYTHONPATH=str(pythonpath) if use_pythonpath else ""),
        capture_output=True,
        encoding="utf-8",
        timeout=15,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "[]" in result.stdout
