import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

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


def test_connect_packages_assets_and_logout_preserves_profile(tmp_path, monkeypatch):
    from pilotpatch import cli
    from pilotpatch.browser.bridge import pairing
    from pilotpatch.config import Config

    messages = []
    monkeypatch.setattr(cli.ui, "event", messages.append)
    cli._connect(tmp_path)
    token = pairing(tmp_path)["token"]
    assert (tmp_path / "edge-extension" / "manifest.json").is_file()
    assert not any(token in message for message in messages)
    cli._connect(tmp_path)
    assert pairing(tmp_path)["token"] == token
    profile = tmp_path / "edge-profile"
    profile.mkdir()
    (profile / "keep.txt").write_text("do not touch")
    cli._logout(tmp_path, Config())
    assert (profile / "keep.txt").read_text() == "do not touch"
    assert not (tmp_path / "edge-pairing.json").exists()


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
