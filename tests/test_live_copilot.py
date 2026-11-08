"""Account-bound acceptance checks. No mocks and no alternate model providers."""

import secrets
import sys

import pytest

from pilotpatch.agent.loop import AgentLoop
from pilotpatch.agent.state import SessionStore
from pilotpatch.config import default_home, load_config
from pilotpatch.providers.factory import browser_provider
from pilotpatch.security.permissions import Permissions
from pilotpatch.tools.command_runner import CommandRunner
from pilotpatch.tools.filesystem import FileTools
from pilotpatch.tools.registry import ToolRegistry
from pilotpatch.tools.repository import Repository

pytestmark = pytest.mark.live


@pytest.fixture
async def live_provider():
    provider = browser_provider(default_home(), load_config())
    await provider.open()
    try:
        yield provider
    finally:
        await provider.close()


async def test_live_manual_login(live_provider, request):
    if not request.config.getoption("--live-login"):
        pytest.skip("Use --live --live-login to wait for interactive Microsoft login")
    assert (await live_provider.login())["authenticated"] is True


async def test_live_persistent_session_reuse(live_provider):
    assert (await live_provider.status())["authenticated"] is True
    await live_provider.close()
    await live_provider.open()
    assert (await live_provider.status())["authenticated"] is True


async def test_live_submission_retrieval_and_multiturn(live_provider):
    nonce = secrets.token_hex(8)
    first = await live_provider.send(f"Remember the marker {nonce}. Reply with that marker only.")
    assert nonce in first
    second = await live_provider.send("Reply with the marker from my previous message only.")
    assert nonce in second


async def test_live_read_edit_and_test_failure_repair(live_provider, tmp_path):
    project = tmp_path / "sample"
    project.mkdir()
    (project / "feature.py").write_text("def answer():\n    return 1\n", encoding="utf-8")
    (project / "test_feature.py").write_text(
        "import unittest\nfrom feature import answer\n"
        "class FeatureTest(unittest.TestCase):\n"
        "    def test_answer(self):\n        self.assertEqual(answer(), 2)\n",
        encoding="utf-8",
    )
    config = load_config().model_copy(
        update={
            "permission_mode": "auto-edit",
            "max_steps": 25,
            "test_commands": {"unit": [sys.executable, "-m", "unittest", "-v"]},
        }
    )
    repo = Repository(project, config)
    store = SessionStore(tmp_path / "state")
    state = store.create(
        project,
        "First run the unit tests to reproduce the failure. Then read "
        "feature.py and test_feature.py, fix feature.py without changing tests, "
        "and rerun unit tests until they pass. Use the unit test name.",
    )
    permissions = Permissions("auto-edit", lambda _: False)
    registry = ToolRegistry(
        FileTools(repo, store.directory(state["id"]), permissions), CommandRunner(repo, permissions)
    )
    report = await AgentLoop(live_provider, registry, store, state).run()
    assert "feature.py" in report["files_changed"]
    assert len(report["checks"]) >= 2
    assert report["checks"][0]["exit_code"] != 0
    assert report["checks"][-1]["exit_code"] == 0
    assert any(r["result"]["tool"] == "read_file" for r in state["receipts"].values())
