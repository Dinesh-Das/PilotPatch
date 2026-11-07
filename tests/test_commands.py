import asyncio
import sys

import pytest

from pilotpatch.config import Config
from pilotpatch.security.permissions import Permissions
from pilotpatch.tools.command_runner import CommandRunner
from pilotpatch.tools.repository import Repository


def runner(tmp_path, confirm=lambda _: True, **kwargs):
    return CommandRunner(Repository(tmp_path, Config(**kwargs)), Permissions("approve", confirm))


async def test_command_failure_and_bounded_output(tmp_path):
    result = await runner(tmp_path).run(
        [sys.executable, "-c", "print('x'*20000);raise SystemExit(3)"]
    )
    assert result["exit_code"] == 3
    assert result["truncated"] is True
    assert len(result["output"].encode()) <= 16000


async def test_command_timeout(tmp_path):
    result = await runner(tmp_path, command_timeout=1).run(
        [sys.executable, "-c", "import time;time.sleep(20)"]
    )
    assert result["timed_out"] is True
    assert result["exit_code"] != 0


async def test_denial_cannot_create_file(tmp_path):
    with pytest.raises(PermissionError):
        await runner(tmp_path, confirm=lambda _: False).run(
            [sys.executable, "-c", "open('bad','w').write('x')"]
        )
    assert not (tmp_path / "bad").exists()


async def test_command_cancellation(tmp_path):
    task = asyncio.create_task(
        runner(tmp_path).run([sys.executable, "-c", "import time;time.sleep(20)"])
    )
    await asyncio.sleep(0.2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


async def test_exact_preauthorization_not_prefix_matching(tmp_path):
    argv = [sys.executable, "-c", "print(42)"]
    instance = runner(tmp_path, confirm=lambda _: False, allowed_commands=[argv])
    assert (await instance.run(argv))["exit_code"] == 0
    with pytest.raises(PermissionError):
        await instance.run(argv + ["extra"])
