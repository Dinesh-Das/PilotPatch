"""Strict, text-only tool protocol. No interpretation by another model."""

import json
import re
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

ToolName = Literal[
    "list_directory", "read_file", "read_file_range", "search_files", "search_content",
    "git_status", "git_diff", "write_file", "replace_in_file", "apply_patch",
    "rename_file", "delete_file", "run_tests", "run_command",
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ToolCall(StrictModel):
    type: Literal["tool_call"]
    id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,80}$")
    tool: ToolName
    arguments: dict[str, Any]


class FinalAnswer(StrictModel):
    type: Literal["final"]
    summary: str = Field(min_length=1, max_length=20000)
    files_changed: list[str] = Field(max_length=500)
    tests: str = Field(max_length=10000)
    remaining_issues: list[str] = Field(max_length=100)


Message = Annotated[ToolCall | FinalAnswer, Field(discriminator="type")]
MESSAGE_ADAPTER = TypeAdapter(Message)


class ProtocolError(ValueError):
    pass


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ProtocolError("Duplicate JSON key")
        result[key] = value
    return result


def parse_message(text: str, max_bytes: int = 100000) -> ToolCall | FinalAnswer:
    if len(text.encode("utf-8")) > max_bytes:
        raise ProtocolError("Response exceeds maximum bytes; request a smaller action")
    stripped = text.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*\n([\s\S]*?)\n```", stripped)
    if fenced:
        stripped = fenced.group(1)
    try:
        data = json.loads(stripped, object_pairs_hook=_unique_object,
                          parse_constant=lambda _: (_ for _ in ()).throw(
                              ProtocolError("Non-finite JSON number")))
        return MESSAGE_ADAPTER.validate_python(data)
    except (ValueError, ValidationError, RecursionError) as exc:
        # Do not echo model/source content into diagnostics.
        raise ProtocolError("Expected one valid tool_call or final JSON object; see protocol schema") from exc
