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


async def test_resume_skips_an_interrupted_review_write_without_replaying_it(tmp_path):
    loop = make_loop(tmp_path, [final()])
    loop.state["pending"] = dict(id="apply_review", tool="apply_review", path="details.txt")
    report = await loop.run(resume=True, resolve_pending=True)
    assert report["files_changed"] == []
    assert loop.state["pending"] is None
    assert loop.state["receipts"] == {}
    assert "Check details.txt on disk." in loop.provider.prompts[0]
    assert not (tmp_path / "repo/details.txt").exists()


async def test_editor_recovers_when_copilot_says_no_tools_for_ui_change(tmp_path):
    refusal = {**final(), "summary": "I can't access the repository tools."}
    loop = make_loop(
        tmp_path,
        [
            "Please provide lab.css.",
            refusal,
            call("read-css", "read_file", path="web/lab.css"),
            call(
                "edit-css",
                "replace_in_file",
                path="web/lab.css",
                old_text="color: red",
                new_text="color: navy",
            ),
            final(),
        ],
    )
    project = tmp_path / "repo"
    (project / "web").mkdir()
    (project / "web/lab.css").write_text("body { color: red; }")
    loop.state["task"] = "Can you make changes to the codebase and polish the UI?"
    report = await loop.run(conversation=[])
    assert report["files_changed"] == ["web/lab.css"]
    assert "body { color: red; }" in loop.provider.prompts[0]
    assert "tool_call" in loop.provider.prompts[1]
    assert "PilotPatch runs" in loop.provider.prompts[2]


async def test_audit_supplies_flutter_sources_and_continues_after_an_early_final(tmp_path):
    premature = {**final(), "summary": "Audit blocked. Please provide the Dart source."}
    conclusions = {
        **final(),
        "summary": "Handle invalid input at lib/main.dart:3.",
        "files_changed": [],
    }
    loop = make_loop(tmp_path, [premature, conclusions])
    loop.state["task"] = "Audit the codebase and suggest improvements"
    project = tmp_path / "repo"
    (project / "lib").mkdir()
    (project / "test").mkdir()
    (project / "pubspec.yaml").write_text("name: flight_lab\n")
    (project / "lib/main.dart").write_text("void main() { launch(); }\n")
    (project / "test/widget_test.dart").write_text("void widgetTest() { assert(true); }\n")
    (project / ".env").write_text("PRIVATE_AUDIT_FIXTURE=excluded\n")
    result = await loop.run(conversation=[])
    assert result["copilot"]["summary"] == conclusions["summary"]
    assert result["audit"]["status"] == "complete"
    assert result["audit"]["files_supplied"] == result["audit"]["files_discovered"] == 3
    assert "name: flight_lab" in loop.provider.prompts[0]
    assert "launch()" in loop.provider.prompts[0]
    assert "widgetTest()" in loop.provider.prompts[0]
    assert all("PRIVATE_AUDIT_FIXTURE" not in prompt for prompt in loop.provider.prompts)


async def test_audit_step_limit_reports_partial_coverage(tmp_path):
    loop = make_loop(tmp_path, [final()], max_steps=1, max_context_bytes=12000)
    loop.state["task"] = "Audit this codebase"
    project = tmp_path / "repo"
    for index in range(16):
        (project / f"module{index}.dart").write_text("void method() {}\n" * 150)
    result = await loop.run()
    assert result["audit"]["status"] == "partial"
    assert 0 < result["audit"]["files_supplied"] < result["audit"]["files_discovered"] == 16
    assert result["audit"]["reason"] == "step_limit"


async def test_audit_advances_multiple_batches_and_blocks_project_writes(tmp_path):
    responses = [
        call("unsafe-edit", "write_file", path="extra.dart", content="bad"),
        *[final()] * 9,
    ]
    loop = make_loop(tmp_path, responses, max_context_bytes=12000, permission_mode="auto-edit")
    loop.state["task"] = "Audit this codebase"
    project = tmp_path / "repo"
    for index in range(7):
        (project / f"module{index}.dart").write_text(f"void unique{index}() {{}}\n" * 150)
    report = await loop.run()
    prompts = loop.provider.prompts
    assert sum("Inspect source batch" in prompt for prompt in prompts) > 1
    assert all(any(f"unique{index}()" in prompt for prompt in prompts) for index in range(7))
    assert all(len(prompt.encode()) <= 12000 for prompt in prompts)
    assert "This audit is read only." in prompts[1]
    assert not (project / "extra.dart").exists()
    assert report["audit"]["files_supplied"] == 7
    assert report["audit"]["status"] == "complete"


async def test_audit_distinguishes_supplied_source_from_missing_model_findings(tmp_path):
    blocked = {**final(), "summary": "Audit blocked. Please provide the source."}
    loop = make_loop(tmp_path, [blocked] * 3)
    loop.state["task"] = "Audit the codebase"
    (tmp_path / "repo/app.dart").write_text("void main() {}\n")
    report = await loop.run()
    assert report["audit"]["files_supplied"] == 1
    assert report["audit"]["status"] == "partial"
    assert report["audit"]["reason"] == "provider_reply"


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
