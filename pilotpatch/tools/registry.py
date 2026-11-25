import json
import subprocess
from typing import Annotated, Any

from pydantic import Field

from pilotpatch.agent.protocol import StrictModel, ToolCall
from pilotpatch.security.redaction import redact
from pilotpatch.tools.command_runner import CommandRunner
from pilotpatch.tools.filesystem import FileTools


class Empty(StrictModel):
    pass


class PathArgs(StrictModel):
    path: str = Field(min_length=1, max_length=500)


class PathsArgs(StrictModel):
    paths: list[Annotated[str, Field(min_length=1, max_length=500)]] = Field(
        min_length=1, max_length=6
    )


class ListArgs(StrictModel):
    path: str = "."


class RangeArgs(PathArgs):
    start: int = Field(ge=1, le=100000)
    end: int = Field(ge=1, le=100000)


class FindArgs(StrictModel):
    pattern: str = Field(default="*", max_length=500)


class SearchArgs(FindArgs):
    query: str = Field(min_length=1, max_length=500)


class DiffArgs(StrictModel):
    path: str | None = None


class WriteArgs(PathArgs):
    content: str = Field(max_length=1000000)
    expected_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


class ReplaceArgs(PathArgs):
    old_text: str = Field(min_length=1, max_length=1000000)
    new_text: str = Field(max_length=1000000)


class PatchArgs(StrictModel):
    patch: str = Field(min_length=1, max_length=1000000)


class DeleteArgs(PathArgs):
    expected_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class RenameArgs(DeleteArgs):
    destination: str = Field(min_length=1, max_length=500)


class CommandArgs(StrictModel):
    argv: list[str] = Field(min_length=1, max_length=100)
    cwd: str = "."


class TestArgs(StrictModel):
    name: str = Field(min_length=1, max_length=100)


ARGUMENTS = {
    "list_directory": ListArgs,
    "read_file": PathArgs,
    "read_files": PathsArgs,
    "read_file_range": RangeArgs,
    "search_files": FindArgs,
    "search_content": SearchArgs,
    "git_status": Empty,
    "git_diff": DiffArgs,
    "write_file": WriteArgs,
    "replace_in_file": ReplaceArgs,
    "apply_patch": PatchArgs,
    "delete_file": DeleteArgs,
    "rename_file": RenameArgs,
    "run_command": CommandArgs,
    "run_tests": TestArgs,
}
MUTATIONS = {"write_file", "replace_in_file", "apply_patch", "delete_file", "rename_file"}
EFFECTS = MUTATIONS | {"run_command", "run_tests"}


def tool_schemas() -> dict:
    return {name: model.model_json_schema() for name, model in ARGUMENTS.items()}


class ToolRegistry:
    def __init__(self, files: FileTools, commands: CommandRunner, *, preparing_edits=False):
        self.files = files
        self.commands = commands
        self.preparing_edits = preparing_edits

    async def execute(self, action: ToolCall) -> dict[str, Any]:
        try:
            args = ARGUMENTS[action.tool].model_validate(action.arguments).model_dump()
            repo, fs = self.files.repo, self.files
            path = args.get("path")
            if action.tool in {"run_command", "run_tests"} and (
                self.preparing_edits or getattr(repo, "changes", None)
            ):
                raise PermissionError(
                    "Commands cannot check proposed changes before they are applied. "
                    "Finish the draft and list the verification command in your reply."
                )
            match action.tool:
                case "list_directory":
                    result = repo.listing(path)
                case "read_file":
                    result = repo.read(path)
                case "read_files":
                    result = self.read_files(args["paths"])
                case "read_file_range":
                    result = repo.read_range(path, args["start"], args["end"])
                case "search_files":
                    names = repo.files(args["pattern"])
                    result = dict(paths=names, truncated=len(names) >= 2000)
                case "search_content":
                    result = repo.search(args["query"], args["pattern"])
                case "git_status":
                    result = repo.git_status()
                case "git_diff":
                    result = repo.git_diff(path)
                case "write_file":
                    result = fs.write(path, args["content"], args["expected_sha256"])
                case "replace_in_file":
                    result = fs.replace(path, args["old_text"], args["new_text"])
                case "apply_patch":
                    result = fs.patch(args["patch"])
                case "delete_file":
                    result = fs.delete(path, args["expected_sha256"])
                case "rename_file":
                    result = fs.rename(path, args["destination"], args["expected_sha256"])
                case "run_command":
                    result = await self.commands.run(args["argv"], args["cwd"])
                case "run_tests":
                    argv = repo.config.test_commands.get(args["name"])
                    if not argv:
                        raise ValueError(
                            "Unknown test name; configure test_commands or request run_command"
                        )
                    result = await self.commands.run(argv, test_name=args["name"])
                case _:
                    raise ValueError("Unsupported tool")
            return dict(
                type="tool_result", id=action.id, tool=action.tool, success=True, result=result
            )
        except (OSError, ValueError, PermissionError, subprocess.SubprocessError) as exc:
            # Pydantic validation messages may echo untrusted argument contents.
            from pydantic import ValidationError

            error = (
                "Invalid tool arguments; consult tool schema"
                if isinstance(exc, ValidationError)
                else redact(str(exc))
            )
            return dict(
                type="tool_result",
                id=action.id,
                tool=action.tool,
                success=False,
                error=dict(code=type(exc).__name__, message=error[:1000]),
            )

    def read_files(self, paths: list[str]) -> dict:
        available = self.files.repo.config.max_context_bytes // 2
        files = []
        for path in dict.fromkeys(paths):
            try:
                data = self.files.repo.read(path)
                size = len(json.dumps(data, ensure_ascii=False).encode())
                if size > available:
                    files.append(dict(path=path, note="Use read_file_range for this file"))
                else:
                    available -= size
                    files.append(data)
            except (ValueError, OSError, UnicodeError) as exc:
                files.append(dict(path=path[:500], error=redact(str(exc))[:500]))
        return dict(files=files)
