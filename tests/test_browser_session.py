"""Startup failures must be actionable without exposing private browser diagnostics."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from playwright.async_api import Error as PlaywrightError

from pilotpatch.browser.session import EdgeSession
from pilotpatch.config import Config
from pilotpatch.providers.base import ProviderError


def session_fixture(tmp_path, monkeypatch):
    page = SimpleNamespace(goto=AsyncMock())
    context = SimpleNamespace(
        new_page=AsyncMock(return_value=page), set_default_timeout=Mock(), close=AsyncMock()
    )
    launch = AsyncMock(return_value=context)
    driver = SimpleNamespace(
        chromium=SimpleNamespace(launch_persistent_context=launch), stop=AsyncMock()
    )
    start = AsyncMock(return_value=driver)
    monkeypatch.setattr(
        "pilotpatch.browser.session.async_playwright", lambda: SimpleNamespace(start=start)
    )
    monkeypatch.setattr(
        "pilotpatch.browser.session.private_directory",
        lambda path: path.mkdir(parents=True, exist_ok=True),
    )
    return EdgeSession(tmp_path / "home", Config()), driver, launch, context, page, start


async def test_launch_failure_names_stage_and_safe_cause(tmp_path, monkeypatch):
    session, driver, launch, _, _, _ = session_fixture(tmp_path, monkeypatch)
    launch.side_effect = PlaywrightError(
        "BrowserType.launch_persistent_context: Executable doesn't exist at C:/Edge/msedge.exe\n"
        "Browser logs: password=never-print-this"
    )
    with pytest.raises(ProviderError) as caught:
        await session.open()
    assert "launching Microsoft Edge" in str(caught.value)
    assert "Executable doesn't exist" in str(caught.value)
    assert "Browser logs" not in str(caught.value)
    assert "never-print-this" not in str(caught.value)
    driver.stop.assert_awaited_once()
    assert not session.lock.is_locked


async def test_navigation_failure_identifies_network_error_without_auth_query(
    tmp_path, monkeypatch
):
    session, _, _, context, page, _ = session_fixture(tmp_path, monkeypatch)
    page.goto.side_effect = PlaywrightError(
        "Page.goto: net::ERR_CERT_AUTHORITY_INVALID at "
        "https://copilot.microsoft.com/?code=private-code#private-fragment\n"
        "Authorization: Bearer never-print-this"
    )
    with pytest.raises(ProviderError) as caught:
        await session.open()
    message = str(caught.value)
    assert "opening the Copilot page" in message
    assert "net::ERR_CERT_AUTHORITY_INVALID" in message
    assert "certificate" in message.lower()
    assert "private-code" not in message
    assert "private-fragment" not in message
    assert "never-print-this" not in message
    context.close.assert_awaited_once()
    assert not session.lock.is_locked


async def test_cleanup_failure_cannot_hide_startup_cause_or_leak_lease(tmp_path, monkeypatch):
    session, driver, _, context, page, _ = session_fixture(tmp_path, monkeypatch)
    page.goto.side_effect = PlaywrightError("Page.goto: net::ERR_CONNECTION_RESET")
    context.close.side_effect = RuntimeError("context cleanup failed")
    driver.stop.side_effect = RuntimeError("driver cleanup failed")
    with pytest.raises(ProviderError) as caught:
        await session.open()
    assert "net::ERR_CONNECTION_RESET" in str(caught.value)
    assert "cleanup" in str(caught.value).lower()
    assert session.context is None
    assert session.playwright is None
    assert not session.lock.is_locked


async def test_cancelled_startup_cleans_up_and_preserves_cancellation(tmp_path, monkeypatch):
    session, driver, launch, _, _, _ = session_fixture(tmp_path, monkeypatch)
    launch.side_effect = asyncio.CancelledError
    with pytest.raises(asyncio.CancelledError):
        await session.open()
    driver.stop.assert_awaited_once()
    assert not session.lock.is_locked


async def test_profile_contention_does_not_start_or_close_another_session(tmp_path, monkeypatch):
    session, _, launch, context, _, _ = session_fixture(tmp_path, monkeypatch)
    await session.open()
    other = EdgeSession(session.home, Config())
    try:
        with pytest.raises(ProviderError, match="in use by another process"):
            await other.open()
        assert launch.await_count == 1
        context.close.assert_not_awaited()
    finally:
        await session.close()


async def test_successful_startup_preserves_profile_and_security_options(tmp_path, monkeypatch):
    session, _, launch, _, page, _ = session_fixture(tmp_path, monkeypatch)
    try:
        assert await session.open() is page
        assert launch.call_args.kwargs["channel"] == "msedge"
        assert launch.call_args.kwargs["chromium_sandbox"] is True
        assert launch.call_args.kwargs["headless"] is False
        page.goto.assert_awaited_once_with(
            "https://copilot.com/chat", wait_until="domcontentloaded", timeout=45000
        )
        assert (session.home / "edge-profile/pilotpatch-owned.json").is_file()
    finally:
        await session.close()
