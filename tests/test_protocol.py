import json

import pytest

from pilotpatch.agent.protocol import ProtocolError, parse_message


def test_fenced_tool_call():
    message = parse_message(
        '```json\n{"type":"tool_call","id":"r1","tool":"read_file",'
        '"arguments":{"path":"a.py"}}\n```'
    )
    assert message.id == "r1"
    assert message.arguments == {"path": "a.py"}


@pytest.mark.parametrize(
    "text",
    [
        "hello",
        '{"type":"tool_call"}',
        '{"type":"tool_call","id":"a","tool":"shell","arguments":{}}',
        '{"type":"final","summary":"ok","tests":"Passed","files_changed":[],"remaining_issues":[],"extra":1}',
        '{"type":"final","type":"tool_call"}',
        "prefix ```json\n{}\n```",
        '{"type":"tool_call","id":"a","tool":"read_file","arguments":{"x":NaN}}',
    ],
)
def test_invalid_messages_are_never_executed(text):
    with pytest.raises(ProtocolError):
        parse_message(text)


def test_response_size_is_bounded():
    with pytest.raises(ProtocolError):
        parse_message(" " * 100, max_bytes=50)


def test_final_message():
    message = parse_message(
        json.dumps(
            dict(
                type="final", summary="done", files_changed=[], tests="not run", remaining_issues=[]
            )
        )
    )
    assert message.type == "final"
