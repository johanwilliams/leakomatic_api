"""Tests for LeakomaticClient that do not need Home Assistant running."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from http.cookies import SimpleCookie
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest
import websockets
import yarl

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


async def test_stop_websocket_forgets_callbacks() -> None:
    """HA-262: after stop, no message or connectivity callback is delivered anywhere."""
    client = LeakomaticClient("user@example.com", "secret")
    client._ws_callbacks.append(lambda message: None)
    client.register_connectivity_callback(lambda connected, phase: None)

    await client.stop_websocket()

    assert client._ws_callbacks == []
    assert client._connectivity_callbacks == []
    assert client._ws_running is False


async def test_cancel_interrupts_long_retry_sleep() -> None:
    """HA-262: cancelling the loop while it waits 12 hours (phase 3) stops it at once."""
    client = _client_for_reconnect_tests()
    client._reconnection_phase = 3

    with patch.object(client, "_attempt_websocket_connection", AsyncMock(return_value=False)):
        task = asyncio.create_task(client._persistent_websocket_connection("ws-token"))
        await asyncio.sleep(0.05)  # let it reach the 12-hour sleep
        assert not task.done()

        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, timeout=1)


def _client_for_reconnect_tests() -> LeakomaticClient:
    client = LeakomaticClient("user@example.com", "secret")
    # Logged in, with a token that does not need refreshing, so the loop
    # never goes to the network
    client._user_id = "1"
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


# --- HA-199: login errors are classified so setup can retry or ask for a new password

START_PAGE = '<html><head><meta name="csrf-token" content="csrf"></head></html>'
LOGIN_OK = '<html><body><a href="/users/1">me</a><table><tr id="device_1001"></tr></table></body></html>'
LOGIN_REJECTED = '<html><body><div class="alert-danger">Invalid Email or password.</div></body></html>'


class FakeHttpSession:
    """Stand-in for aiohttp.ClientSession: get() is the start page, post() the login."""

    def __init__(self, start: FakeResponse | Exception, login: FakeResponse | Exception) -> None:
        self._start = start
        self._login = login

    def _respond(self, response: FakeResponse | Exception) -> FakeResponse:
        if isinstance(response, Exception):
            raise response
        return response

    def get(self, *args, **kwargs) -> FakeResponse:
        return self._respond(self._start)

    def post(self, *args, **kwargs) -> FakeResponse:
        return self._respond(self._login)

    async def close(self) -> None:
        return None


async def _authenticate(start: FakeResponse | Exception, login: FakeResponse | Exception) -> LeakomaticClient:
    client = LeakomaticClient("user@example.com", "secret")
    session = FakeHttpSession(start, login)
    with patch("custom_components.leakomatic.leakomatic_client.aiohttp.ClientSession", return_value=session):
        client.auth_result = await client.async_authenticate()
    return client


async def test_authenticate_ok() -> None:
    client = await _authenticate(FakeResponse(START_PAGE), FakeResponse(LOGIN_OK))
    assert client.auth_result is True
    assert client.error_code is None
    assert client._user_id == "1"


@pytest.mark.parametrize(
    ("start", "login", "expected"),
    [
        (FakeResponse(START_PAGE), FakeResponse(LOGIN_REJECTED), "invalid_credentials"),
        (FakeResponse(START_PAGE), FakeResponse("", status=401), "invalid_credentials"),
        (FakeResponse(START_PAGE), FakeResponse("", status=422), "invalid_credentials"),
        (FakeResponse(START_PAGE), FakeResponse("", status=500), "cannot_connect"),
        (FakeResponse(START_PAGE), FakeResponse("", status=503), "cannot_connect"),
        (FakeResponse("", status=502), FakeResponse(LOGIN_OK), "cannot_connect"),
        (aiohttp.ClientConnectionError("DNS failure"), FakeResponse(LOGIN_OK), "cannot_connect"),
        (FakeResponse(START_PAGE), asyncio.TimeoutError(), "cannot_connect"),
        (FakeResponse("<html>maintenance</html>"), FakeResponse(LOGIN_OK), "auth_token_missing"),
    ],
)
async def test_authenticate_error_codes(start, login, expected: str) -> None:
    """Only a rejected login means invalid credentials; network and server errors do not."""
    client = await _authenticate(start, login)
    assert client.auth_result is False
    assert client.error_code == expected


# --- HA-269: the websocket loop logs in and gets its token itself


async def _run_until_first_attempt(client: LeakomaticClient, **patches) -> list[str]:
    """Run the loop until the first real connection attempt; return the tokens it used."""
    tokens: list[str] = []

    async def attempt(ws_token: str) -> bool:
        tokens.append(ws_token)
        client._ws_running = False
        return True

    with (
        patch.object(client, "_attempt_websocket_connection", side_effect=attempt),
        patch("custom_components.leakomatic.leakomatic_client.asyncio.sleep", AsyncMock()),
        patch.multiple(client, **patches),
    ):
        await client._persistent_websocket_connection()
    return tokens


async def test_loop_fetches_its_own_token() -> None:
    client = LeakomaticClient("user@example.com", "secret")
    client._user_id = "1"
    get_token = AsyncMock(return_value="fresh-token")

    tokens = await _run_until_first_attempt(client, async_get_websocket_token=get_token)

    assert tokens == ["fresh-token"]
    assert client._ws_token_expiry is not None


async def test_loop_retries_when_token_fetch_fails() -> None:
    """A failed token fetch (e.g. DNS down at startup) is retried, not the end of the websocket."""
    client = LeakomaticClient("user@example.com", "secret")
    client._user_id = "1"
    get_token = AsyncMock(side_effect=[None, None, "fresh-token"])

    tokens = await _run_until_first_attempt(client, async_get_websocket_token=get_token)

    assert tokens == ["fresh-token"]
    assert get_token.await_count == 3


async def test_loop_logs_in_when_user_id_is_missing() -> None:
    client = LeakomaticClient("user@example.com", "secret")

    async def login() -> bool:
        client._user_id = "1"
        return True

    authenticate = AsyncMock(side_effect=login)
    get_token = AsyncMock(return_value="fresh-token")

    tokens = await _run_until_first_attempt(
        client, async_authenticate=authenticate, async_get_websocket_token=get_token
    )

    authenticate.assert_awaited_once()
    assert tokens == ["fresh-token"]


# --- HA-261: an expired session is renewed once, and never reported as success


class FakeHttpResponse:
    """Response with the attributes the session helper looks at."""

    def __init__(self, status: int = 200, path: str = "/devices/1001.json",
                 content_type: str = "application/json", body: object = None) -> None:
        self.status = status
        self.url = yarl.URL("https://cloud.example.com" + path)
        self.content_type = content_type
        self.cookies: SimpleCookie = SimpleCookie()
        self._body = body

    async def json(self) -> object:
        return self._body

    async def text(self) -> str:
        return str(self._body)

    async def __aenter__(self) -> "FakeHttpResponse":
        return self

    async def __aexit__(self, *exc) -> None:
        return None


class ScriptedSession:
    """Session whose request() returns the next scripted response."""

    def __init__(self, responses: list[FakeHttpResponse]) -> None:
        self._responses = responses

    def request(self, *args, **kwargs) -> FakeHttpResponse:
        return self._responses.pop(0)

    def get(self, *args, **kwargs) -> FakeHttpResponse:
        return self._responses.pop(0)

    def post(self, *args, **kwargs) -> FakeHttpResponse:
        return self._responses.pop(0)

    async def close(self) -> None:
        return None

    async def __aenter__(self) -> "ScriptedSession":
        return self

    async def __aexit__(self, *exc) -> None:
        return None


LOGGED_OUT = FakeHttpResponse(path="/users/sign_in", content_type="text/html", body="<html>login</html>")


def _logged_in_client(responses: list[FakeHttpResponse]) -> tuple[LeakomaticClient, AsyncMock]:
    """A client that is logged in, answers with the scripted responses, and can log in again."""
    client = LeakomaticClient("user@example.com", "secret")
    client._device_ids = ["1001"]
    client._xsrf_token = "old-xsrf"
    client._cookies = SimpleCookie()
    session = ScriptedSession(responses)
    client._create_session = AsyncMock(return_value=session)

    async def login() -> bool:
        client._xsrf_token = "new-xsrf"
        return True

    authenticate = AsyncMock(side_effect=login)
    client.async_authenticate = authenticate
    return client, authenticate


@pytest.mark.parametrize(
    "logged_out",
    [
        LOGGED_OUT,
        FakeHttpResponse(status=401, content_type="application/json", body={"error": "sign in"}),
        FakeHttpResponse(path="/devices/1001.json", content_type="text/html", body="<html>login</html>"),
    ],
)
async def test_expired_session_is_renewed(logged_out: FakeHttpResponse) -> None:
    """Redirect to the login page, 401, or HTML instead of JSON: log in again and retry once."""
    client, authenticate = _logged_in_client([logged_out, FakeHttpResponse(body={"mode": 0})])

    assert await client.async_get_device_data("1001") == {"mode": 0}
    authenticate.assert_awaited_once()


async def test_still_logged_out_after_relogin_gives_up() -> None:
    """Only one new login per request, so wrong credentials cannot cause a login storm."""
    client, authenticate = _logged_in_client([LOGGED_OUT, LOGGED_OUT])

    assert await client.async_get_device_data("1001") is None
    authenticate.assert_awaited_once()


async def test_change_mode_on_expired_session_is_not_reported_as_success() -> None:
    """The login page answers 200, which used to be logged as 'Successfully changed mode'."""
    client, _ = _logged_in_client([LOGGED_OUT, LOGGED_OUT])

    assert await client.async_change_mode("away", "1001") is False


async def test_change_mode_after_renewed_session() -> None:
    client, authenticate = _logged_in_client([LOGGED_OUT, FakeHttpResponse(path="/devices/1001/change_mode.json", body="")])

    assert await client.async_change_mode("away", "1001") is True
    authenticate.assert_awaited_once()


async def test_rejected_login_calls_auth_failed_callback() -> None:
    """A login that Leakomatic rejects during operation triggers reauthentication."""
    rejected = MagicMock()
    client = LeakomaticClient("user@example.com", "secret")
    client.set_auth_failed_callback(rejected)
    session = FakeHttpSession(FakeResponse(START_PAGE), FakeResponse(LOGIN_REJECTED))
    with patch("custom_components.leakomatic.leakomatic_client.aiohttp.ClientSession", return_value=session):
        assert await client.async_authenticate() is False

    rejected.assert_called_once()


async def test_connection_error_does_not_call_auth_failed_callback() -> None:
    rejected = MagicMock()
    client = LeakomaticClient("user@example.com", "secret")
    client.set_auth_failed_callback(rejected)
    session = FakeHttpSession(FakeResponse(START_PAGE), FakeResponse("", status=503))
    with patch("custom_components.leakomatic.leakomatic_client.aiohttp.ClientSession", return_value=session):
        assert await client.async_authenticate() is False

    rejected.assert_not_called()


# --- HA-270: the connection counts as established only when the server confirms it

WELCOME = '{"type": "welcome"}'
CONFIRM = '{"identifier": "{}", "type": "confirm_subscription"}'
REJECT = '{"identifier": "{}", "type": "reject_subscription"}'


class FakeWebSocket:
    """Websocket that returns the given frames, then reports the connection closed."""

    def __init__(self, frames: list[str]) -> None:
        self._frames = list(frames)
        self.sent: list[str] = []

    async def send(self, data: str) -> None:
        self.sent.append(data)

    async def recv(self) -> str:
        if self._frames:
            return self._frames.pop(0)
        raise websockets.ConnectionClosed(None, None)

    async def __aenter__(self) -> "FakeWebSocket":
        return self

    async def __aexit__(self, *exc) -> None:
        return None


async def _connect_once(client: LeakomaticClient, frames: list[str]) -> tuple[bool, list[bool]]:
    """Run one connection attempt against the frames; return its result and the connectivity reports."""
    reports: list[bool] = []
    client.register_connectivity_callback(lambda connected, phase: reports.append(connected))
    with patch(
        "custom_components.leakomatic.leakomatic_client.websockets.connect",
        return_value=FakeWebSocket(frames),
    ):
        result = await client._attempt_websocket_connection("ws-token")
    return result, reports


async def test_new_client_reports_not_connected() -> None:
    """HA-270: before any connection attempt the connectivity sensor is told 'not connected'."""
    client = LeakomaticClient("user@example.com", "secret")
    reports: list[bool] = []

    client.register_connectivity_callback(lambda connected, phase: reports.append(connected))

    assert reports == [False]


async def test_confirmed_subscription_counts_as_connected() -> None:
    client = _client_for_reconnect_tests()

    result, reports = await _connect_once(client, [WELCOME, CONFIRM])

    assert reports == [False, True]
    assert result is True  # a live connection existed and then dropped


async def test_welcome_without_confirmation_is_not_connected() -> None:
    """HA-270: a socket that closes before the subscription is confirmed is a failed attempt."""
    client = _client_for_reconnect_tests()

    result, reports = await _connect_once(client, [WELCOME])

    assert reports == [False]
    assert result is False  # the caller applies backoff


async def test_rejected_subscription_is_not_connected() -> None:
    """HA-270: reject_subscription ends the attempt as failed and forces a new token."""
    client = _client_for_reconnect_tests()

    result, reports = await _connect_once(client, [WELCOME, REJECT, CONFIRM])

    assert reports == [False]
    assert result is False
    assert client._should_refresh_token()


async def test_disconnect_without_reconnect_forces_new_token() -> None:
    """HA-270: ActionCable's disconnect with reconnect=false means the token is refused."""
    client = _client_for_reconnect_tests()
    refused = '{"type": "disconnect", "reason": "unauthorized", "reconnect": false}'

    result, reports = await _connect_once(client, [refused])

    assert reports == [False]
    assert result is False
    assert client._should_refresh_token()


async def test_disconnect_with_reconnect_keeps_token(caplog: pytest.LogCaptureFixture) -> None:
    """A server restart (reconnect=true) after a confirmed subscription is an ordinary drop."""
    client = _client_for_reconnect_tests()
    restart = '{"type": "disconnect", "reason": "server_restart", "reconnect": true}'

    result, reports = await _connect_once(client, [WELCOME, CONFIRM, restart])

    assert reports == [False, True]
    assert result is True
    assert not client._should_refresh_token()
    assert not _warnings(caplog)
