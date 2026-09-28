"""Client for the Leakomatic API.

This module provides a client for interacting with the Leakomatic API, including:
- Authentication and session management
- Device data retrieval
- Real-time updates via WebSocket connection
- Message handling for various device events
"""
from __future__ import annotations

import logging
import re
import asyncio
import random
import time
from typing import Any, Optional, Callable, Dict
from datetime import datetime, timedelta, timezone

import aiohttp
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.util.ssl import get_default_context
import websockets
from bs4 import BeautifulSoup
import urllib.parse
import json

from .const import (
    LOGGER_NAME, START_URL, LOGIN_URL, STATUS_URL, WEBSOCKET_URL,
    MessageType, DEFAULT_HEADERS, WEBSOCKET_HEADERS, MAX_QUICK_RETRIES, INITIAL_RETRY_DELAY,
    MAX_RETRY_DELAY, RETRY_BACKOFF_FACTOR, MEDIUM_RETRY_INTERVAL, MAX_MEDIUM_RETRIES,
    LONG_RETRY_INTERVAL, STALE_CONNECTION_TIMEOUT, DUPLICATE_MESSAGE_WINDOW,
    ERROR_AUTH_TOKEN_MISSING, ERROR_INVALID_CREDENTIALS, ERROR_XSRF_TOKEN_MISSING, ERROR_NO_DEVICES_FOUND,
    ERROR_CANNOT_CONNECT, LOGIN_REJECTED_STATUSES,
    XSRF_TOKEN_HEADER, DeviceMode, XSRF_TOKEN_PATTERN
)

_LOGGER = logging.getLogger(LOGGER_NAME)

# Where Leakomatic sends a browser whose session has expired
LOGIN_PATHS = ("/login", "/users/sign_in")


class LeakomaticRequestError(Exception):
    """A request with the login session failed."""


class LeakomaticClient:
    """Client for the Leakomatic API.
    
    This class handles all communication with the Leakomatic API, including
    authentication, data retrieval, and WebSocket connections for real-time updates.
    """

    def __init__(self, email: str, password: str, hass=None) -> None:
        """Initialize the client.
        
        Args:
            email: The email address for authentication
            password: The password for authentication
            hass: Optional Home Assistant instance for scheduling callbacks
        """
        self._email = email
        self._password = password
        self._hass = hass
        self._auth_token: Optional[str] = None
        self._device_ids: list[str] = []
        self._user_id: Optional[str] = None
        self._session: Optional[aiohttp.ClientSession] = None
        self._error_code: Optional[str] = None
        self._xsrf_token: Optional[str] = None
        self._ws_running = True
        self._ws_callbacks: list[Callable[[dict], None]] = []
        self._device_data_cache: dict[str, Any] = {}
        self._device_data_cache_time: dict[str, datetime] = {}
        
        # New attributes for persistent reconnection
        self._ws_connected = False
        self._last_ws_message: Optional[datetime] = None
        self._ws_token_expiry: Optional[datetime] = None
        self._reconnection_phase = 1  # 1=quick, 2=medium, 3=long
        self._connectivity_callbacks: list[Callable[[bool, int], None]] = []
        # Recently received device message frames (raw text -> monotonic time)
        self._recent_frames: dict[str, float] = {}
        self._auth_failed_callback: Optional[Callable[[], None]] = None

    def _get_session(self) -> aiohttp.ClientSession:
        """The client's HTTP session, created on first use.

        One session for the client's lifetime, with its own cookie jar: the
        login depends on Leakomatic's session and XSRF cookies, which must not
        mix with other integrations' cookies in Home Assistant's shared session.
        With hass, Home Assistant closes it when it stops; async_close closes
        it when the integration unloads.
        """
        if self._session is None or self._session.closed:
            if self._hass is not None:
                self._session = async_create_clientsession(self._hass, cookie_jar=aiohttp.CookieJar())
            else:
                self._session = aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar())
        return self._session

    def _request_headers(self, headers: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        """Headers for a request: the given ones (or the defaults) plus the XSRF token."""
        request_headers = dict(headers) if headers is not None else DEFAULT_HEADERS.copy()
        if self._xsrf_token:
            request_headers[XSRF_TOKEN_HEADER] = urllib.parse.unquote(self._xsrf_token)
        else:
            _LOGGER.warning("No XSRF token available for session headers")
        return request_headers

    async def _update_session_from_response(self, response: aiohttp.ClientResponse) -> None:
        """Update cookies and XSRF token from a response.
        
        Args:
            response: The aiohttp ClientResponse to extract cookies and XSRF token from.
        """
        new_xsrf_token = await self._async_get_xsrf_token(response)
        if new_xsrf_token:
            self._xsrf_token = new_xsrf_token
        else:
            _LOGGER.warning("No new XSRF token found in response")

    async def async_authenticate(self) -> bool:
        """Authenticate with the Leakomatic API.

        On failure, error_code tells why: ERROR_INVALID_CREDENTIALS only when
        the server rejected the email or password, ERROR_CANNOT_CONNECT for
        network and server errors. The failures are logged at debug level;
        the caller decides what to report (Home Assistant retries setup itself).
        """
        self._error_code = None
        try:
            _LOGGER.debug("Initiating authentication process with Leakomatic")

            # A fresh login: forget the cookies of any earlier session
            session = self._get_session()
            session.cookie_jar.clear()

            # Get the auth token from the start page
            self._auth_token = await self._async_get_startpage()
            if not self._auth_token:
                self._error_code = self._error_code or ERROR_AUTH_TOKEN_MISSING
                _LOGGER.debug("Authentication failed at the start page (%s)", self._error_code)
                return False

            # Login with the auth token
            login_success = await self._async_login()
            if not login_success:
                _LOGGER.debug("Authentication failed at login (%s)", self._error_code)
                if self._error_code == ERROR_INVALID_CREDENTIALS and self._auth_failed_callback:
                    self._auth_failed_callback()
                return False

            _LOGGER.debug("Authentication successful with Leakomatic API")
            return True

        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            _LOGGER.debug("Authentication failed, cannot connect: %s", err)
            self._error_code = ERROR_CANNOT_CONNECT
            return False
        except Exception as err:
            _LOGGER.error("Authentication error: %s", err)
            return False

    def connection_state(self) -> dict[str, Any]:
        """The connection's state, for diagnostics. No credentials or tokens."""
        def iso(moment: Optional[datetime]) -> Optional[str]:
            return moment.isoformat() if moment else None

        return {
            "logged_in": bool(self._xsrf_token),
            "error_code": self._error_code,
            "device_ids": list(self._device_ids),
            "websocket_connected": self._ws_connected,
            "reconnection_phase": self._reconnection_phase,
            "last_websocket_message": iso(self._last_ws_message),
            "websocket_token_expiry": iso(self._ws_token_expiry),
            "device_data_fetched": {
                device_id: iso(fetched) for device_id, fetched in self._device_data_cache_time.items()
            },
        }

    def cached_device_data(self, device_id: str) -> Optional[dict[str, Any]]:
        """The latest device data fetched from the REST API, if any."""
        return self._device_data_cache.get(device_id)

    @property
    def error_code(self) -> Optional[str]:
        """Get the error code if authentication failed."""
        return self._error_code
    
    @property
    def device_ids(self) -> list[str]:
        """Get the list of device IDs."""
        return self._device_ids

    @property
    def user_id(self) -> Optional[str]:
        """The Leakomatic user ID found at login, if any."""
        return self._user_id

    def set_auth_failed_callback(self, callback: Optional[Callable[[], None]]) -> None:
        """Set a function to call when Leakomatic rejects the credentials.

        The integration uses it to start reauthentication when a login during
        normal operation (for example after the session expired) is rejected.
        """
        self._auth_failed_callback = callback

    def register_connectivity_callback(self, callback: Callable[[bool, int], None]) -> None:
        """Register a callback for WebSocket connectivity status changes.
        
        Args:
            callback: Function to call when connectivity status changes.
                     Takes two parameters: (connected: bool, phase: int)
        """
        _LOGGER.debug("Registering connectivity callback")
        self._connectivity_callbacks.append(callback)
        _LOGGER.debug("Total connectivity callbacks: %d", len(self._connectivity_callbacks))
        # Immediately notify the new callback of the current state
        try:
            if self._hass:
                self._hass.add_job(callback, self._ws_connected, self._reconnection_phase)
                _LOGGER.debug("Immediately scheduled connectivity callback on main thread")
            else:
                callback(self._ws_connected, self._reconnection_phase)
                _LOGGER.debug("Immediately called connectivity callback directly")
        except Exception as e:
            _LOGGER.error("Error in immediate connectivity callback: %s", str(e))

    def _notify_connectivity_callbacks(self, connected: bool, phase: int) -> None:
        """Notify all registered connectivity callbacks of status changes.
        
        Args:
            connected: Whether the WebSocket is currently connected
            phase: The current reconnection phase (1, 2, or 3)
        """
        _LOGGER.debug("Notifying %d connectivity callbacks: connected=%s, phase=%d", 
                     len(self._connectivity_callbacks), connected, phase)
        
        for callback in self._connectivity_callbacks:
            try:
                if self._hass:
                    # Schedule the callback on the event loop (sync add_job API; async_add_job is deprecated)
                    self._hass.add_job(callback, connected, phase)
                    _LOGGER.debug("Scheduled connectivity callback on main thread")
                else:
                    # Direct call if no hass instance available
                    callback(connected, phase)
                    _LOGGER.debug("Called connectivity callback directly")
            except Exception as e:
                _LOGGER.error("Error in connectivity callback: %s", str(e))

    async def _async_get_startpage(self) -> Optional[str]:
        """Get the auth token from the start page."""
        try:
            _LOGGER.debug("Requesting authentication token from Leakomatic...")
            
            async with self._session.get(START_URL) as response:
                if response.status != 200:
                    _LOGGER.debug("Connection failed - server returned %s", response.status)
                    self._error_code = ERROR_CANNOT_CONNECT
                    return None
                
                
                text = await response.text()
                soup = BeautifulSoup(text, 'html.parser')
                
                # Find the auth token
                auth_token = soup.find('meta', {'name': 'csrf-token'})
                if not auth_token or not auth_token.get('content'):
                    _LOGGER.warning("Connection failed - authentication token not found")
                    return None
                
                _LOGGER.debug("Authentication token successfully retrieved")
                return auth_token['content']

        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            _LOGGER.debug("Connection error: %s", err)
            self._error_code = ERROR_CANNOT_CONNECT
            return None
        except Exception as err:
            _LOGGER.error("Connection error: %s", err)
            return None

    async def _async_get_xsrf_token(self, response: aiohttp.ClientResponse) -> Optional[str]:
        """Get the XSRF token from the response cookies."""
        # Get the XSRF-TOKEN cookie value
        xsrf_token = response.cookies.get('XSRF-TOKEN')
        if not xsrf_token:
            _LOGGER.warning("XSRF token not found in cookies")
            return None
            
        # Convert to string
        xsrf_token_str = str(xsrf_token)
        
        # Use regex to extract just the token value
        match = re.search(XSRF_TOKEN_PATTERN, xsrf_token_str)
        if match:
            xsrf_token_value = match.group(1)
            return xsrf_token_value
        else:
            _LOGGER.warning("Failed to extract XSRF token using regex pattern")
            return None

    async def _async_login(self) -> bool:
        """Login to the Leakomatic API."""
        try:
            _LOGGER.debug("Attempting login with provided credentials...")
            
            # Prepare login data
            login_data = {
                "utf8": "✓",
                "authenticity_token": self._auth_token,
                "user[email]": self._email,
                "user[password]": self._password,
                "user[remember_me]": "0",
                "commit": "Log in"
            }
            
            headers = DEFAULT_HEADERS.copy()
            
            async with self._session.post(LOGIN_URL, data=login_data, headers=headers) as response:
                if response.status != 200:
                    _LOGGER.debug("Login failed - server returned %s", response.status)
                    self._error_code = (
                        ERROR_INVALID_CREDENTIALS
                        if response.status in LOGIN_REJECTED_STATUSES
                        else ERROR_CANNOT_CONNECT
                    )
                    return False
                
                # Get the XSRF token using the new method
                xsrf_token = await self._async_get_xsrf_token(response)
                if not xsrf_token:
                    _LOGGER.warning("Login failed - security token not received")
                    self._error_code = ERROR_XSRF_TOKEN_MISSING
                    return False
                
                self._xsrf_token = xsrf_token
                
                # Check if login was successful by looking for device elements
                text = await response.text()
                soup = BeautifulSoup(text, 'html.parser')
                
                # Check for error messages
                error_messages = soup.find_all('div', class_='alert-danger')
                if error_messages:
                    for error in error_messages:
                        _LOGGER.warning("Login failed - %s", error.text.strip())
                    self._error_code = ERROR_INVALID_CREDENTIALS
                    return False
                
                _LOGGER.debug("Login successful. Retrieving user ID...")

                # Find the user ID - be careful with the href attribute
                try:
                    user_link = soup.find('a', href=lambda href: href and "/users/" in href)
                    if user_link and hasattr(user_link, 'attrs') and 'href' in user_link.attrs:
                        href = user_link.attrs['href']
                        if href and "/users/" in href:
                            user_id = href.split('/')[-1]
                            self._user_id = user_id
                            _LOGGER.debug("Found user ID: %s. Retrieving devices...", user_id)
                        else:
                            _LOGGER.debug("User ID not found in href attribute")
                    else:
                        _LOGGER.debug("User ID link not found on the page after login")
                except Exception as user_id_err:
                    _LOGGER.debug("Error extracting user ID: %s", user_id_err)

                if not self._user_id:
                    _LOGGER.warning(
                        "Could not find the user ID after login; real-time updates via "
                        "websocket will not be available"
                    )

                # Find all <tr> elements with an id attribute starting with 'device_'
                device_elements = soup.find_all('tr', {'id': lambda x: x and x.startswith('device_')})
                if not device_elements:
                    _LOGGER.warning("No Leakomatic devices found in account")
                    self._error_code = ERROR_NO_DEVICES_FOUND
                    return False
                
                # Store all device IDs
                self._device_ids = [element['id'].replace('device_', '') for element in device_elements]
                _LOGGER.debug("Found %d Leakomatic devices with IDs: %s", len(self._device_ids), self._device_ids)
                return True
                
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            _LOGGER.debug("Login failed, cannot connect: %s", err)
            self._error_code = ERROR_CANNOT_CONNECT
            return False
        except Exception as err:
            _LOGGER.error("Login error: %s", err)
            return False

    async def async_get_device_data(self, device_id: str) -> Optional[dict[str, Any]]:
        """Get one device's data from the Leakomatic API, with a 15-minute cache.

        Args:
            device_id: The Leakomatic device ID.

        Returns:
            The device data, or None if it could not be fetched.
        """
        now = datetime.now(tz=timezone.utc)
            
        # Check cache for this specific device
        if (
            device_id in self._device_data_cache and
            device_id in self._device_data_cache_time and
            (now - self._device_data_cache_time[device_id]) < timedelta(minutes=15)
        ):
            return self._device_data_cache[device_id]
            
        try:
            _LOGGER.debug("Fetching data for device with ID: %s", device_id)
            device_data = await self._async_session_request(
                "GET", f"{STATUS_URL}/{device_id}.json", expect_json=True
            )
            self._device_data_cache[device_id] = device_data
            self._device_data_cache_time[device_id] = now
            return device_data

        except Exception as err:
            return self._handle_error(f"Failed to fetch device data: {err}", return_value=None, level="debug")

    async def async_close(self) -> None:
        """Close the client session."""
        if self._session:
            await self._session.close()
            self._session = None
            _LOGGER.debug("Closed connection to Leakomatic API")

    async def async_get_websocket_token(self) -> Optional[str]:
        """Get the websocket token from the device page."""
        if not self.device_ids:
            return self._handle_error("Cannot fetch websocket token - no devices configured", return_value=None, level="debug")
            
        try:
            _LOGGER.debug("Fetching websocket token...")
            # The device page (HTML, not JSON) contains the websocket token
            text = await self._async_session_request(
                "GET", f"{STATUS_URL}/{self.device_ids[0]}", expect_json=False
            )

            match = re.search(r'token=([a-zA-Z0-9_.-]+)', text)
            if not match:
                return self._handle_error(
                    "Websocket token not found in the response",
                    return_value=None,
                    level="debug"
                )

            _LOGGER.debug("Websocket token retrieved successfully")
            return match.group(1)

        except Exception as err:
            return self._handle_error(f"Failed to fetch websocket token: {err}", return_value=None, level="debug")

    async def connect_to_websocket(self, message_callback: Callable[[dict], None]) -> None:
        """Connect to the websocket server and listen for messages with persistent reconnection.

        Runs until stopped or cancelled. Logging in and getting a websocket
        token are part of every connection attempt, so a failure there is
        retried with the same backoff as a failed connection.

        Args:
            message_callback: Callback function to handle messages
        """
        self._ws_callbacks.append(message_callback)
        await self._persistent_websocket_connection()

    async def stop_websocket(self) -> None:
        """Stop the websocket connection and forget all callbacks.

        The connection loop checks the running flag between messages; the
        integration also cancels the task itself when the entry unloads.
        Clearing the callbacks makes sure nothing is delivered to entities
        that are being removed.
        """
        was_connected = self._ws_connected
        self._ws_running = False
        self._ws_connected = False

        # Notify connectivity callbacks if we were connected
        if was_connected:
            self._notify_connectivity_callbacks(False, self._reconnection_phase)

        self._ws_callbacks.clear()
        self._connectivity_callbacks.clear()
        _LOGGER.debug("Websocket connection stopped")

    @staticmethod
    def _is_logged_out(response: aiohttp.ClientResponse, expect_json: bool) -> bool:
        """Return True if the response shows that the login session has expired.

        Leakomatic is a Rails app: an expired session gives 401 for JSON
        requests, or a redirect to the login page (followed by aiohttp, so the
        final URL is the login page). HTML where JSON was expected is also a
        login page.
        """
        if response.status == 401:
            return True
        if response.url.path.rstrip("/") in LOGIN_PATHS:
            return True
        return expect_json and response.content_type == "text/html"

    async def _async_session_request(
        self,
        method: str,
        url: str,
        *,
        expect_json: bool,
        headers: Optional[Dict[str, str]] = None,
        json_data: Optional[dict] = None,
    ) -> Any:
        """Make a request with the login session, logging in again once if it has expired.

        Args:
            method: HTTP method.
            url: The URL to call.
            expect_json: Parse the response as JSON (otherwise return the text).
            headers: Headers for the request; the XSRF token is added.
            json_data: JSON body to send.

        Returns:
            The parsed JSON or the response text.

        Raises:
            LeakomaticRequestError: The request failed, or the session could not
                be renewed. Only one new login is tried per request, so wrong
                credentials never turn into a stream of login attempts.
        """
        if not await self._ensure_authenticated():
            raise LeakomaticRequestError(f"not logged in ({self._error_code})")

        for attempt in range(2):
            async with self._get_session().request(
                method, url, json=json_data, headers=self._request_headers(headers)
            ) as response:
                if self._is_logged_out(response, expect_json):
                    if attempt == 0:
                        _LOGGER.debug("Leakomatic session has expired, logging in again")
                        self._xsrf_token = None
                        if not await self.async_authenticate():
                            raise LeakomaticRequestError(
                                f"session expired and logging in again failed ({self._error_code})"
                            )
                        continue
                    raise LeakomaticRequestError("still logged out after logging in again")

                if response.status != 200:
                    raise LeakomaticRequestError(f"server returned {response.status}")

                await self._update_session_from_response(response)
                if expect_json:
                    return await response.json()
                return await response.text()

        raise LeakomaticRequestError("request was not completed")

    async def _ensure_authenticated(self) -> bool:
        """Ensure the client is authenticated.
        
        This method checks if the client has a valid XSRF token. If not, it attempts
        to authenticate with the Leakomatic API.
        
        Returns:
            bool: True if the client is authenticated, False otherwise.
        """
        if not self._xsrf_token:
            _LOGGER.debug("No XSRF token available, reconnecting to Leakomatic API")
            auth_success = await self.async_authenticate()
            if not auth_success:
                _LOGGER.debug("Failed to log in to Leakomatic API (%s)", self._error_code)
                return False
        return True

    def _extract_message_type(self, parsed_response: dict) -> str:
        """Extract the message type from a parsed WebSocket response.
        
        Args:
            parsed_response: The parsed JSON response from the WebSocket.
        
        Returns:
            str: The extracted message type, or an empty string if no type is found.
        """
        # Special messages that use the top-level 'type' key
        msg_type = parsed_response.get("type")
        if msg_type in (
            MessageType.PING.value,
            MessageType.WELCOME.value,
            MessageType.CONFIRM_SUBSCRIPTION.value,
            MessageType.REJECT_SUBSCRIPTION.value,
            MessageType.DISCONNECT.value,
        ):
            return msg_type
            
        # All other operational messages use 'message.operation'
        operation = parsed_response.get("message", {}).get("operation")
        if operation in [msg_type.value for msg_type in MessageType]:
            return operation
            
        # If we have a message but no operation, it might be a data update
        if "message" in parsed_response and "data" in parsed_response["message"]:
            return "data_update"
            
        return ""

    def _handle_error(self, error_msg: str, error_code: Optional[str] = None, return_value: Any = None, level: str = "error") -> Any:
        """Handle errors consistently across methods.
        
        Args:
            error_msg: The error message to log.
            error_code: Optional error code to set.
            return_value: The value to return on error.
            level: The log level to use ("error", "warning" or "debug").
        
        Returns:
            The specified return value.
        """
        # Remove any trailing periods from error messages
        error_msg = error_msg.rstrip('.')
        
        # Log the error without the component name (Home Assistant adds this automatically)
        if level == "error":
            _LOGGER.error(error_msg)
        elif level == "debug":
            _LOGGER.debug(error_msg)
        else:
            _LOGGER.warning(error_msg)
        
        if error_code:
            self._error_code = error_code
            
        return return_value 

    async def _async_make_request(self, endpoint: str, data: dict, operation: str, device_id: str) -> bool:
        """Make an HTTP request to the Leakomatic API.
        
        Args:
            endpoint: The API endpoint to call (e.g. 'change_mode.json' or 'reset_alarms.json')
            data: The data to send in the request
            operation: A description of the operation being performed (for logging)
            device_id: Optional device ID to make the request for. If not provided, uses the first device.
            
        Returns:
            bool: True if the request was successful, False otherwise
        """

        try:
            headers = {
                "Content-Type": "application/json;charset=UTF-8",
                "User-Agent": "Mozilla/5.0",
                "Connection": "close"
            }
            url = f"{STATUS_URL}/{device_id}/{endpoint}"
            _LOGGER.debug("Making %s request to %s for device %s", operation, url, device_id)

            # A redirect to the login page (expired session) is not a success:
            # the helper logs in again once and retries, or raises.
            await self._async_session_request(
                "POST", url, expect_json=False, headers=headers, json_data=data
            )
            _LOGGER.info("Successfully %s for device %s", operation, device_id)
            return True

        except LeakomaticRequestError as err:
            return self._handle_error(f"Failed to {operation}: {err}", return_value=False, level="warning")
        except Exception as err:
            return self._handle_error(f"Failed to {operation}: {err}", return_value=False, level="error")

    async def async_change_mode(self, mode: str, device_id: str) -> bool:
        """Change the mode of one Leakomatic device.

        Args:
            mode: The new mode: "home", "away" or "pause".
            device_id: The Leakomatic device ID.

        Returns:
            bool: True if the mode was changed, False otherwise.
        """
        try:
            # Convert the string mode to a numeric value using the DeviceMode enum
            numeric_mode = DeviceMode.from_string(mode)

            # Prepare the data for the request
            data = {
                "mode": numeric_mode
            }
            
            result = await self._async_make_request(
                endpoint="change_mode.json",
                data=data,
                operation=f"change mode to {mode}",
                device_id=device_id
            )
            
            return result
                
        except ValueError as err:
            return self._handle_error(str(err), return_value=False, level="warning")

    async def async_reset_alarms(self, device_id: str) -> bool:
        """Reset all alarms on one Leakomatic device.

        Args:
            device_id: The Leakomatic device ID.

        Returns:
            bool: True if the alarms were reset, False otherwise.
        """

        # Prepare the data for the request - array with alarm_ids
        data = {"alarm_ids": [0]}
        
        return await self._async_make_request(
            endpoint="reset_alarms.json",
            data=data,
            operation="reset alarms",
            device_id=device_id
        )

    async def _async_prepare_websocket(self, ws_token: str | None) -> str | None:
        """Make sure there is a user ID and a websocket token before connecting.

        Args:
            ws_token: The token from the previous attempt, if any.

        Returns:
            The token to connect with, or None if this attempt cannot connect
            (the caller then backs off and tries again).
        """
        if not self._user_id:
            _LOGGER.debug("No user ID, logging in before connecting to the websocket")
            if not await self.async_authenticate() or not self._user_id:
                return None

        if ws_token is None or self._should_refresh_token():
            _LOGGER.debug("Fetching WebSocket token")
            new_token = await self.async_get_websocket_token()
            if new_token:
                self._ws_token_expiry = datetime.now(tz=timezone.utc) + timedelta(hours=24)
                return new_token
            if ws_token is None:
                _LOGGER.debug("Could not get a WebSocket token")
                return None
            _LOGGER.debug("Failed to refresh WebSocket token, using existing token")

        return ws_token

    async def _persistent_websocket_connection(self, initial_ws_token: str | None = None) -> None:
        """Maintain a persistent WebSocket connection with multi-phase retry strategy."""
        ws_token = initial_ws_token
        quick_retry_count = 0
        medium_retry_count = 0
        retry_delay = INITIAL_RETRY_DELAY

        while self._ws_running:
            try:
                _LOGGER.debug("Attempting WebSocket connection (Phase %d)", self._reconnection_phase)

                # Log in and get or refresh the token (every 24 hours) first.
                # Without them this attempt counts as a failed connection.
                ws_token = await self._async_prepare_websocket(ws_token)

                # Attempt connection. _attempt_websocket_connection blocks while
                # the socket is alive and returns True if a live connection
                # existed and then dropped/stalled, False if it could never be
                # established. Connection-established bookkeeping (phase reset,
                # connectivity callback) happens inside that method once the
                # subscribe succeeds.
                had_connection = (
                    await self._attempt_websocket_connection(ws_token)
                    if ws_token is not None
                    else False
                )

                if had_connection:
                    # A real connection was lost (not a connection failure):
                    # reset all backoff state and reconnect promptly.
                    quick_retry_count = 0
                    medium_retry_count = 0
                    retry_delay = INITIAL_RETRY_DELAY
                    self._reconnection_phase = 1
                    self._ws_connected = False
                    _LOGGER.info("WebSocket connection closed, reconnecting")
                    self._notify_connectivity_callbacks(False, self._reconnection_phase)
                    # Small pause to avoid a tight flap loop on rapid drops.
                    await asyncio.sleep(INITIAL_RETRY_DELAY)

                else:
                    # Handle reconnection based on current phase
                    if self._reconnection_phase == 1:
                        # Phase 1: Quick retries
                        quick_retry_count += 1
                        if quick_retry_count >= MAX_QUICK_RETRIES:
                            _LOGGER.warning("WebSocket reconnection failed %d times, retrying every %d hours (phase 2)", MAX_QUICK_RETRIES, MEDIUM_RETRY_INTERVAL // 3600)
                            self._reconnection_phase = 2
                            medium_retry_count = 0
                            # Notify connectivity callbacks of phase change
                            self._notify_connectivity_callbacks(False, self._reconnection_phase)
                        else:
                            # Calculate next retry delay with exponential backoff and jitter
                            retry_delay = min(retry_delay * RETRY_BACKOFF_FACTOR, MAX_RETRY_DELAY)
                            jitter = retry_delay * 0.2
                            actual_delay = retry_delay + random.uniform(-jitter, jitter)
                            
                            _LOGGER.info(
                                "WebSocket connection failed (Phase 1, attempt %d/%d). Retrying in %.1f seconds.",
                                quick_retry_count, MAX_QUICK_RETRIES, actual_delay
                            )
                            await asyncio.sleep(actual_delay)
                            
                    elif self._reconnection_phase == 2:
                        # Phase 2: Medium-term retries
                        medium_retry_count += 1
                        if medium_retry_count >= MAX_MEDIUM_RETRIES:
                            _LOGGER.warning("WebSocket reconnection still failing, retrying every %d hours (phase 3)", LONG_RETRY_INTERVAL // 3600)
                            self._reconnection_phase = 3
                            # Notify connectivity callbacks of phase change
                            self._notify_connectivity_callbacks(False, self._reconnection_phase)
                        else:
                            _LOGGER.info(
                                "WebSocket connection failed (Phase 2, attempt %d/%d). Retrying in %d hours.",
                                medium_retry_count, MAX_MEDIUM_RETRIES, MEDIUM_RETRY_INTERVAL // 3600
                            )
                            await asyncio.sleep(MEDIUM_RETRY_INTERVAL)
                            
                    else:
                        # Phase 3: Long-term retries (indefinite)
                        _LOGGER.info(
                            "WebSocket connection failed (Phase 3). Retrying in %d hours.",
                            LONG_RETRY_INTERVAL // 3600
                        )
                        await asyncio.sleep(LONG_RETRY_INTERVAL)

            except Exception as err:
                _LOGGER.error("Unexpected error in WebSocket connection loop: %s", err)
                await asyncio.sleep(60)  # Wait 1 minute before retrying

    async def _attempt_websocket_connection(self, ws_token: str) -> bool:
        """Establish and hold a WebSocket connection until it drops.

        Returns:
            bool: True if a connection was established and later dropped or went
                  stale (caller should reset its backoff), False if a connection
                  could never be established (caller should apply phased backoff).
        """
        connected = False
        try:
            # Construct the websocket URL
            ws_url = f"{WEBSOCKET_URL}?token={ws_token}"

            # Use a timeout for the connection to prevent blocking
            async with websockets.connect(
                ws_url,
                subprotocols=['actioncable-v1-json'],
                additional_headers=WEBSOCKET_HEADERS,
                ssl=get_default_context(),
                ping_interval=20,  # Send ping every 20 seconds
                ping_timeout=10,   # Wait 10 seconds for pong response
                close_timeout=5    # Wait 5 seconds for close response
            ) as websocket:
                _LOGGER.debug("Connected to websocket server")

                # Send subscription message
                msg_subscribe = {
                    "command": "subscribe",
                    "identifier": f"{{\"channel\":\"BroadcastChannel\",\"user_id\":{self._user_id}}}"
                }
                await websocket.send(json.dumps(msg_subscribe))
                _LOGGER.debug("Sent subscription message")
                self._last_ws_message = datetime.now(tz=timezone.utc)

                # Listen for messages
                while self._ws_running:
                    received = False
                    try:
                        # Use a timeout for receiving messages to prevent blocking
                        response = await asyncio.wait_for(websocket.recv(), timeout=30)
                        received = True
                        parsed_response = json.loads(response)
                        
                        # Update last message timestamp
                        self._last_ws_message = datetime.now(tz=timezone.utc)

                        # Extract message type
                        msg_type = self._extract_message_type(parsed_response)

                        # Handle different message types
                        if msg_type == MessageType.WELCOME.value:
                            _LOGGER.debug("Received welcome message")
                        elif msg_type == MessageType.PING.value:
                            # Skip logging for ping messages
                            pass
                        elif msg_type == MessageType.CONFIRM_SUBSCRIPTION.value:
                            # The connection counts as established only once the
                            # server has accepted the subscription. Record it and
                            # reset the backoff state so a later drop is treated
                            # as a successful reconnection rather than a
                            # connection failure.
                            _LOGGER.debug("Subscription confirmed")
                            connected = True
                            self._ws_connected = True
                            self._reconnection_phase = 1
                            self._notify_connectivity_callbacks(True, self._reconnection_phase)
                            _LOGGER.info("WebSocket connection established successfully")
                        elif msg_type == MessageType.REJECT_SUBSCRIPTION.value:
                            # The server refused the subscription: no data will
                            # arrive on this socket. Get a new token next time.
                            _LOGGER.debug("Subscription rejected by the server")
                            self._ws_token_expiry = None
                            return connected
                        elif msg_type == MessageType.DISCONNECT.value:
                            # ActionCable's disconnect: reconnect=false means the
                            # server will not accept this token again.
                            reason = parsed_response.get("reason")
                            if parsed_response.get("reconnect") is False:
                                _LOGGER.debug("Server disconnected (%s), fetching a new token", reason)
                                self._ws_token_expiry = None
                            else:
                                _LOGGER.debug("Server disconnected (%s)", reason)
                            return connected
                        else:
                            # For all other message types, call all callbacks
                            if msg_type and self._is_duplicate(response):
                                _LOGGER.debug("Dropped duplicate %s message", msg_type)
                            elif msg_type:
                                device_identifier = parsed_response.get('message', {}).get('device', 'unknown')
                                _LOGGER.debug("Device %s received message %s", device_identifier, msg_type)
                                _LOGGER.debug("Message payload: %s", parsed_response)
                                # Call all registered callbacks
                                for callback in self._ws_callbacks:
                                    try:
                                        callback(parsed_response)
                                    except Exception as e:
                                        _LOGGER.error("Error in WebSocket callback: %s", str(e))
                            else:
                                _LOGGER.warning("Unknown message type in response")

                    except asyncio.TimeoutError:
                        # No message (not even an ActionCable ping) within the
                        # window. If the socket has been silent for too long it
                        # is stale/stuck - break out to force a reconnect.
                        if self._last_ws_message and (
                            datetime.now(tz=timezone.utc) - self._last_ws_message
                            > timedelta(seconds=STALE_CONNECTION_TIMEOUT)
                        ):
                            _LOGGER.warning(
                                "No WebSocket messages for %ds, connection stale - reconnecting",
                                STALE_CONNECTION_TIMEOUT,
                            )
                            return connected
                        # Otherwise this is just a quiet period - keep waiting.
                        continue
                    except websockets.ConnectionClosed:
                        _LOGGER.debug("Websocket connection closed by server")
                        return connected
                    except Exception as err:
                        if not received:
                            # recv() itself failed: the socket is in an unknown
                            # state and would fail again at once. Leave, and let
                            # the reconnection loop take over with its backoff.
                            _LOGGER.warning("Error receiving from the websocket, reconnecting: %s", err)
                            return connected
                        # A message that could not be handled: skip it
                        _LOGGER.error("Error processing websocket message: %s", err)
                        continue

            return connected
        except Exception as err:
            _LOGGER.debug("WebSocket connection attempt failed: %s", err)
            return connected

    def _is_duplicate(self, frame: str) -> bool:
        """Return True if the same frame was received within DUPLICATE_MESSAGE_WINDOW."""
        now = time.monotonic()
        self._recent_frames = {
            text: seen for text, seen in self._recent_frames.items()
            if now - seen < DUPLICATE_MESSAGE_WINDOW
        }
        if frame in self._recent_frames:
            return True
        self._recent_frames[frame] = now
        return False

    def _should_refresh_token(self) -> bool:
        """Check if the WebSocket token should be refreshed."""
        if not self._ws_token_expiry:
            return True
        
        # Refresh if token expires within the next hour
        return datetime.now(tz=timezone.utc) + timedelta(hours=1) >= self._ws_token_expiry 