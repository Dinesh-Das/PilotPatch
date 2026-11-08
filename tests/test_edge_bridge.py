import asyncio
import hashlib
import hmac
import json
import secrets

import pytest

from pilotpatch.browser.bridge import Bridge, pairing
from pilotpatch.config import Config
from pilotpatch.providers.base import ProviderError
from pilotpatch.providers.existing_edge import CopilotExistingEdge
from pilotpatch.providers.factory import browser_provider


def test_default_never_constructs_or_launches_managed_edge(tmp_path):
    assert Config().browser_connection == "existing-edge"
    assert isinstance(browser_provider(tmp_path, Config()), CopilotExistingEdge)


async def request(
    bridge, token=None, origin=None, path="/next", body=None, host=None, nonce=None, session=None
):
    reader, writer = await asyncio.open_connection("127.0.0.1", bridge.port)
    value = dict(body or {"client": "test-client", "tab": 7})
    value.setdefault("protocol", 2)
    payload = json.dumps(value).encode()
    nonce = nonce or secrets.token_hex(32)
    if path != "/hello":
        payload = bridge.encrypt(payload, f"request\n{bridge.session}\n{path}\n{nonce}")
    key = (
        bytes.fromhex(token)
        if token and len(token) == 64
        else (bytes.fromhex(bridge.token) if token is None else b"wrong")
    )
    proof = hmac.new(
        key,
        f"request\n{session or bridge.session}\n{path}\n{nonce}\n".encode() + payload,
        hashlib.sha256,
    ).hexdigest()
    headers = {
        "Host": host or f"127.0.0.1:{bridge.port}",
        "Origin": origin or f"chrome-extension://{bridge.extension_id}",
        "X-PilotPatch-Nonce": nonce,
        "X-PilotPatch-Mac": proof,
        "Content-Type": "application/json",
        "Content-Length": str(len(payload)),
    }
    wire = f"POST {path} HTTP/1.1\r\n" + "".join(f"{k}: {v}\r\n" for k, v in headers.items())
    writer.write(wire.encode() + b"\r\n" + payload)
    await writer.drain()
    response = await reader.read()
    writer.close()
    await writer.wait_closed()
    head, data = response.split(b"\r\n\r\n", 1)
    code = int(head.split()[1])
    if b"X-PilotPatch-Mac:" in head:
        proof = bridge.mac(f"response\n{nonce}\n{code}\n".encode() + data)
        assert f"X-PilotPatch-Mac: {proof}".encode() in head
        if path != "/hello":
            data = bridge.decrypt(data, f"response\n{bridge.session}\n{path}\n{nonce}")
    return code, json.loads(data)


async def test_broker_denies_wrong_token_web_origin_and_rebinding_host(tmp_path):
    bridge = Bridge(tmp_path, port=0)
    await bridge.open()
    try:
        for kwargs in [
            dict(token="wrong"),
            dict(origin="https://copilot.com"),
            dict(host="attacker.example"),
        ]:
            code, _ = await request(bridge, **kwargs)
            assert code == 403
        assert not bridge.connected.is_set()
    finally:
        await bridge.close()


async def test_challenge_proof_and_requests_cannot_replay_across_server_sessions(tmp_path):
    bridge = Bridge(tmp_path, port=0)
    await bridge.open()
    try:
        code, hello = await request(bridge, path="/hello")
        assert code == 200 and hello == {"session": bridge.session, "protocol": 2}
        assert bridge.token not in json.dumps(hello)
        nonce = secrets.token_hex(32)
        assert (await request(bridge, nonce=nonce))[0] == 200
        assert (await request(bridge, nonce=nonce))[0] == 403
        assert (await request(bridge, session="0" * 64))[0] == 403
    finally:
        await bridge.close()


async def test_rpc_delivered_once_bound_to_client_and_tab(tmp_path):
    bridge = Bridge(tmp_path, port=0)
    await bridge.open()
    try:
        call = asyncio.create_task(bridge.call("status", {}, wait_seconds=1))
        code, command = await request(bridge)
        assert code == 200 and command["action"] == "status"
        assert (await request(bridge, body={"client": "other", "tab": 7}))[0] == 409
        assert (await request(bridge, body={"client": "test-client", "tab": 8}))[0] == 409
        result = {
            "client": "test-client",
            "tab": 7,
            "id": command["id"],
            "result": {"state": "authenticated_ui"},
        }
        assert (await request(bridge, path="/result", body=result))[0] == 200
        assert await call == {"state": "authenticated_ui"}
        assert (await request(bridge, path="/result", body=result))[0] == 409
        assert (await request(bridge))[1] == {"idle": True}
    finally:
        await bridge.close()


async def test_submit_commit_grant_requires_live_pending_command_and_is_one_shot(tmp_path):
    bridge = Bridge(tmp_path, port=0)
    await bridge.open()
    try:
        call = asyncio.create_task(bridge.call("submit", {}, wait_seconds=2))
        _, command = await request(bridge)
        body = {"client": "test-client", "tab": 7, "id": command["id"]}
        assert (await request(bridge, path="/result", body=dict(body, result={"submitted": True})))[
            0
        ] == 409
        assert (await request(bridge, path="/commit", body=body))[1] == {"authorized": True}
        assert (await request(bridge, path="/commit", body=body))[0] == 409
        assert (await request(bridge, path="/result", body=dict(body, result={"submitted": True})))[
            0
        ] == 200
        assert await call == {"submitted": True}
        assert (await request(bridge, path="/commit", body=body))[0] == 409
    finally:
        await bridge.close()


async def test_legacy_worker_never_receives_the_submit_payload(tmp_path):
    bridge = Bridge(tmp_path, port=0)
    await bridge.open()
    try:
        call = asyncio.create_task(
            bridge.call("submit", {"text": "private prompt"}, wait_seconds=0.05)
        )
        code, body = await request(
            bridge, body={"client": "old-client", "tab": 7, "protocol": None}
        )
        assert code == 409 and body == {"error": "extension_upgrade_required"}
        assert "private prompt" not in json.dumps(body)
        assert bridge.connection_error and "Reload" in bridge.connection_error
        with pytest.raises(ProviderError):
            await call
    finally:
        await bridge.close()


async def test_timeout_discards_command_instead_of_replaying_it(tmp_path):
    bridge = Bridge(tmp_path, port=0)
    await bridge.open()
    try:
        with pytest.raises(ProviderError, match="unknown outcome"):
            await bridge.call("submit", {}, wait_seconds=0.01)
        assert (await request(bridge))[1] == {"idle": True}
        with pytest.raises(ValueError):
            await bridge.call("evaluate", {}, wait_seconds=1)
    finally:
        await bridge.close()


async def test_http_framing_limits_and_unknown_routes_are_rejected(tmp_path):
    bridge = Bridge(tmp_path, port=0)
    await bridge.open()
    try:
        assert (await request(bridge, path="/evaluate"))[0] == 404
        for extra, code in [
            ("Content-Length: 1\r\nContent-Length: 2", 400),
            ("Transfer-Encoding: chunked\r\nContent-Length: 0", 400),
            ("Content-Length: 12000001", 413),
        ]:
            reader, writer = await asyncio.open_connection("127.0.0.1", bridge.port)
            wire = (
                f"POST /next HTTP/1.1\r\nHost: 127.0.0.1:{bridge.port}\r\n"
                f"Origin: chrome-extension://{bridge.extension_id}\r\n"
                f"X-PilotPatch-Nonce: {secrets.token_hex(32)}\r\n{extra}\r\n\r\n"
            )
            writer.write(wire.encode())
            await writer.drain()
            response = await reader.read()
            writer.close()
            await writer.wait_closed()
            assert int(response.split()[1]) == code
    finally:
        await bridge.close()


async def test_delivered_submit_is_never_redelivered_even_if_result_is_lost(tmp_path):
    bridge = Bridge(tmp_path, port=0)
    await bridge.open()
    try:
        call = asyncio.create_task(bridge.call("submit", {}, wait_seconds=0.15))
        code, command = await request(bridge)
        assert code == 200 and command["action"] == "submit"
        assert (await request(bridge))[1] == {"idle": True}
        with pytest.raises(ProviderError, match="unknown outcome"):
            await call
        assert (await request(bridge))[1] == {"idle": True}
        assert (
            await request(
                bridge,
                path="/result",
                body={
                    "client": "test-client",
                    "tab": 7,
                    "id": command["id"],
                    "result": {"submitted": True},
                },
            )
        )[0] == 409
    finally:
        await bridge.close()


async def test_active_connection_lease_is_not_taken_over(tmp_path):
    first, second = Bridge(tmp_path, port=0), Bridge(tmp_path, port=0)
    await first.open()
    try:
        with pytest.raises(ProviderError, match="Another PilotPatch"):
            await second.open()
        await second.close()
        assert (await request(first))[0] == 200
    finally:
        await first.close()


async def test_unpaired_provider_explains_setup_without_starting_a_server(tmp_path):
    provider = CopilotExistingEdge(tmp_path, Config())
    with pytest.raises(ProviderError, match="connect"):
        await provider.open()
    assert provider.bridge.server is None
    assert not (tmp_path / "edge-profile").exists()


def test_pairing_reused_without_reading_browser_credentials(tmp_path):
    first = pairing(tmp_path, create=True)
    assert pairing(tmp_path) == first
    assert len(first["token"]) == 64
    assert set(first) == {"version", "token", "port", "extension_id"}
