"""Tests for LeakomaticClient that do not need Home Assistant running."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from http.cookies import SimpleCookie
from unittest.mock import AsyncMock, patch

import pytest

from custom_components.leakomatic.const import MAX_QUICK_RETRIES
from custom_components.leakomatic.leakomatic_client import LeakomaticClient

LOGIN_PAGE_WITHOUT_USER_LINK = """
<html><body>
  <table>
    <tr id="device_1001"><td>Leakomatic</td></tr>
  </table>
</body></html>
"""


class FakeResponse:
    """Minimal stand-in for aiohttp.ClientResponse."""

    def __init__(self, text: str, status: int = 200) -> None:
        self.status = status
        self._text = text
        self.cookies: SimpleCookie = SimpleCookie()
        self.cookies["XSRF-TOKEN"] = "xsrf-value"

    async def text(self) -> str:
        return self._text

    async def __aenter__(self) -> "FakeResponse":
        return self

    async def __aexit__(self, *exc) -> None:
        return None


class FakeSession:
    """Session whose post() always returns the given response."""

    def __init__(self, response: FakeResponse) -> None:
        self._response = response

    def post(self, *args, **kwargs) -> FakeResponse:
        return self._response


async def test_login_without_user_link(caplog: pytest.LogCaptureFixture) -> None:
    """HA-193: a login page without the users link still logs in and warns clearly."""
    client = LeakomaticClient("user@example.com", "secret")
    client._session = FakeSession(FakeResponse(LOGIN_PAGE_WITHOUT_USER_LINK))
    client._cookies = SimpleCookie()
    client._auth_token = "csrf"

    assert await client._async_login() is True
    assert client.device_ids == ["1001"]
    assert client._user_id is None
    assert "Could not find the user ID after login" in caplog.text


def _client_for_reconnect_tests() -> LeakomaticClient:
    client = LeakomaticClient("user@example.com", "secret")
    # A token that does not need refreshing, so the loop never goes to the network
    client._ws_token_expiry = datetime.now(tz=timezone.utc) + timedelta(days=1)
    return client


def _warnings(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.levelno >= logging.WARNING]


async def test_server_disconnect_is_not_a_warning(caplog: pytest.LogCaptureFixture) -> None:
    """HA-210: the server closing a live connection (nightly at 01:00) is not a warning."""
    client = _client_for_reconnect_tests()

    async def one_dropped_connection(ws_token: str) -> bool:
        client._ws_running = False  # stop after this round
        return True  # a connection existed and was closed

    with (
        patch.object(client, "_attempt_websocket_connection", side_effect=one_dropped_connection),
        patch("custom_components.leakomatic.leakomatic_client.asyncio.sleep", AsyncMock()),
    ):
        await client._persistent_websocket_connection("ws-token")

    assert not _warnings(caplog)


async def test_giving_up_on_quick_retries_is_a_warning(caplog: pytest.LogCaptureFixture) -> None:
    """HA-210: when quick reconnection fails and phase 2 starts, that is worth a warning."""
    client = _client_for_reconnect_tests()
    attempts = 0

    async def always_fails(ws_token: str) -> bool:
        nonlocal attempts
        attempts += 1
        if attempts > MAX_QUICK_RETRIES:
            client._ws_running = False
        return False

    with (
        patch.object(client, "_attempt_websocket_connection", side_effect=always_fails),
        patch("custom_components.leakomatic.leakomatic_client.asyncio.sleep", AsyncMock()),
    ):
        await client._persistent_websocket_connection("ws-token")

    assert client._reconnection_phase == 2
    warnings = _warnings(caplog)
    assert len(warnings) == 1
    assert "phase 2" in warnings[0].getMessage()
