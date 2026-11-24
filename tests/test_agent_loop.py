import asyncio
import json
import sys

import pytest

from pilotpatch.agent.loop import AgentLoop, AgentStopped
from pilotpatch.agent.state import SessionStore
from pilotpatch.config import Config
from pilotpatch.security.permissions import Permissions
from pilotpatch.tools.command_runner import CommandRunner
from pilotpatch.tools.filesystem import FileTools
from pilotpatch.tools.registry import ToolRegistry
from pilotpatch.tools.repository import Repository


class FakeCopilot:
    """Offline test double only; never exported as a runtime provider."""

    def __init__(self, responses):
        self.responses = iter(responses)
        self.prompts = []

    async def send(self, prompt):
        self.prompts.append(prompt)
        item = next(self.responses)
        if isinstance(item, BaseException):
            raise item
        return item if isinstance(item, str) else json.dumps(item)


def call(id, tool, **arguments):
    return dict(type="tool_call", id=id, tool=tool, arguments=arguments)


def final(tests="Passed"):
    return dict(
        type="final",
        summary="Done",
        tests=tests,
        files_changed=["imaginary.py"],
        remaining_issues=[],
    )


def make_loop(tmp_path, responses, **config):
    project = tmp_path / "repo"
    project.mkdir(exist_ok=True)
    repo = Repository(project, Config(**config))
    store = SessionStore(tmp_path / "home")
    state = store.create(project, "Implement a function")
    permissions = Permissions("auto-edit", lambda _: True)
    registry = ToolRegistry(
        FileTools(repo, store.directory(state["id"]), permissions), CommandRunner(repo, permissions)
    )
    return AgentLoop(FakeCopilot(responses), registry, store, state)


async def test_multistep_edit_duplicate_receipt_and_verified_report(tmp_path):
    action = call("edit1", "write_file", path="hello.py", content="answer = 42\n")
    loop = make_loop(tmp_path, [call("list1", "list_directory"), action, action, final()])
    report = await loop.run()
    assert (tmp_path / "repo/hello.py").read_text() == "answer = 42\n"
    assert report["files_changed"] == ["hello.py"]
    assert report["checks"] == []  # Copilot's 'Passed' is not test evidence.
    assert (
        len(list((loop.store.directory(loop.state["id"]) / "backups").glob("*/manifest.json"))) == 1
    )
    assert loop.store.load(loop.state["id"])["status"] == "completed"


async def test_chat_followup_includes_prior_exchange_and_actual_edit_receipt(tmp_path):
    loop = make_loop(tmp_path, [final()])
    loop.state["task"] = "Where is that setting used?"
    await loop.run(
        conversation=[
            dict(
                user="Find the flight speed setting",
                assistant="It starts at FLIGHT_SPEED in settings.py.",
                changed_files=["settings.py"],
            )
        ]
    )
    policy, payload = loop.provider.prompts[0].split("\n{", 1)
    context = json.loads("{" + payload)
    assert context["user_task"] == "Where is that setting used?"
    assert context["conversation_untrusted"][0]["changed_files"] == ["settings.py"]
    assert "FLIGHT_SPEED" in context["conversation_untrusted"][0]["assistant"]
    assert "Markdown" in policy


async def test_format_correction_is_bounded(tmp_path):
    loop = make_loop(tmp_path, ["bad", "bad", "bad"])
    with pytest.raises(AgentStopped, match="invalid protocol"):
        await loop.run()
    assert loop.state["status"] == "interrupted"


async def test_duplicate_id_with_different_payload_rejected(tmp_path):
    loop = make_loop(tmp_path, [call("a", "list_directory"), call("a", "git_status")])
    with pytest.raises(AgentStopped, match="different arguments"):
        await loop.run()


async def test_loop_detection_with_new_ids(tmp_path):
    loop = make_loop(tmp_path, [call(str(n), "list_directory") for n in range(4)])
    with pytest.raises(AgentStopped, match="Repeated"):
        await loop.run()


async def test_max_steps(tmp_path):
    loop = make_loop(tmp_path, [call("a", "list_directory")], max_steps=1)
    with pytest.raises(AgentStopped, match="Maximum"):
        await loop.run()


async def test_cancelled_call_remains_pending_and_resume_does_not_reexecute(tmp_path):
    loop = make_loop(tmp_path, [call("a", "write_file", path="x", content="x")])

    async def interrupted(_):
        raise asyncio.CancelledError

    loop.registry.execute = interrupted
    with pytest.raises(asyncio.CancelledError):
        await loop.run()
    assert loop.state["pending"]["id"] == "a"
    with pytest.raises(AgentStopped, match="unknown outcome"):
        await loop.run(resume=True)
    loop.provider = FakeCopilot([final()])
    report = await loop.run(resume=True, resolve_pending=True)
    assert report["files_changed"] == []
    assert not (tmp_path / "repo/x").exists()


async def test_actual_test_failure_then_repair(tmp_path):
    loop = make_loop(
        tmp_path,
        [
            call("fail", "run_tests", name="unit"),
            call("fix", "write_file", path="feature.py", content="answer = 42\n"),
            call("pass", "run_tests", name="unit"),
            final(),
        ],
        test_commands={
            "unit": [sys.executable, "-c", "from feature import answer; assert answer == 42"]
        },
    )
    report = await loop.run()
    assert [c["exit_code"] for c in report["checks"]] == [1, 0]
    assert "ModuleNotFoundError" in loop.provider.prompts[1]
