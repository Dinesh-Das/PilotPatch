import os
import subprocess
import sys

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
    monkeypatch.setattr(cli, "CopilotBrowser", lambda *_: provider)
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
    monkeypatch.setattr(cli, "CopilotBrowser", lambda *_: provider)
    monkeypatch.setattr(cli.ui, "event", lambda _: None)
    assert await cli._browser_command("status", SimpleNamespace(home=tmp_path), Config()) == 2
