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
import ssl
import asyncio
import random
from typing import Any, Optional, Callable, Dict
from datetime import datetime, timedelta, timezone

import aiohttp
import websockets
from bs4 import BeautifulSoup
import urllib.parse
import json

from .const import (
    LOGGER_NAME, START_URL, LOGIN_URL, STATUS_URL, WEBSOCKET_URL,
    MessageType, DEFAULT_HEADERS, WEBSOCKET_HEADERS, MAX_QUICK_RETRIES, INITIAL_RETRY_DELAY,
    MAX_RETRY_DELAY, RETRY_BACKOFF_FACTOR, MEDIUM_RETRY_INTERVAL, MAX_MEDIUM_RETRIES,
    LONG_RETRY_INTERVAL, HEALTH_CHECK_INTERVAL,
    ERROR_AUTH_TOKEN_MISSING, ERROR_INVALID_CREDENTIALS, ERROR_XSRF_TOKEN_MISSING, ERROR_NO_DEVICES_FOUND,
    XSRF_TOKEN_HEADER, DeviceMode, XSRF_TOKEN_PATTERN
)

_LOGGER = logging.getLogger(LOGGER_NAME)

# Create SSL context at module level
ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
ssl_context.load_default_certs()
ssl_context.set_default_verify_paths()

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
        self._cookies: Optional[aiohttp.CookieJar] = None
        self._ws_running = True
        self._ws_callbacks: list[Callable[[dict], None]] = []
        self._device_data_cache: dict[str, Any] = {}
        self._device_data_cache_time: dict[str, datetime] = {}
        
        # New attributes for persistent reconnection
        self._ws_connected = True
        self._last_ws_message: Optional[datetime] = None
        self._ws_token_expiry: Optional[datetime] = None
        self._reconnection_phase = 1  # 1=quick, 2=medium, 3=long
        self._connectivity_callbacks: list[Callable[[bool, int], None]] = []

    async def _create_session(self, headers: Optional[Dict[str, str]] = None) -> aiohttp.ClientSession:
        """Create a new session with the saved cookies and headers.
        
        Args:
            headers: Optional headers to include in the session.
                    If not provided, default headers will be used.
                    The XSRF token will be added to the headers if it exists.
        
        Returns:
            An aiohttp ClientSession with the configured cookies and headers.
        """
        if headers is None:
            headers = DEFAULT_HEADERS.copy()
        
        # Always add the XSRF token to the headers if it exists
        if self._xsrf_token:
            headers[XSRF_TOKEN_HEADER] = urllib.parse.unquote(self._xsrf_token)
        else:
            _LOGGER.warning("No XSRF token available for session headers")
        
        return aiohttp.ClientSession(cookies=self._cookies, headers=headers)

    async def _update_session_from_response(self, response: aiohttp.ClientResponse) -> None:
        """Update cookies and XSRF token from a response.
        
        Args:
            response: The aiohttp ClientResponse to extract cookies and XSRF token from.
        """
        self._cookies.update(response.cookies)
        new_xsrf_token = await self._async_get_xsrf_token(response)
        if new_xsrf_token:
            self._xsrf_token = new_xsrf_token
        else:
            _LOGGER.warning("No new XSRF token found in response")

    async def async_authenticate(self) -> bool:
        """Authenticate with the Leakomatic API."""
        try:
            _LOGGER.debug("Initiating authentication process with Leakomatic")
            
            # Create a new session
            self._session = aiohttp.ClientSession()
            
            # Get the auth token from the start page
            self._auth_token = await self._async_get_startpage()
            if not self._auth_token:
                _LOGGER.warning("Authentication failed - could not establish connection with Leakomatic")
                self._error_code = ERROR_AUTH_TOKEN_MISSING
                return False
            
            # Login with the auth token
            login_success = await self._async_login()
            if not login_success:
                _LOGGER.warning("Authentication failed - invalid credentials or connection error")
                return False
            
            _LOGGER.debug("Authentication successful with Leakomatic API")
            return True
            
        except Exception as err:
            _LOGGER.error("Authentication error: %s", err)
            return False
        finally:
            # Close the session after authentication
            if self._session:
                await self._session.close()
                self._session = None

    @property
    def error_code(self) -> Optional[str]:
        """Get the error code if authentication failed."""
        return self._error_code
    
    @property
    def device_ids(self) -> list[str]:
        """Get the list of device IDs."""
        return self._device_ids

    @property
    def device_id(self) -> Optional[str]:
        """Get the first device ID for backward compatibility."""
        return self._device_ids[0] if self._device_ids else None

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
                    _LOGGER.warning("Connection failed - server returned %s", response.status)
                    return None
                
                # Save the cookies from the start page
                self._cookies = response.cookies
                
                text = await response.text()
                soup = BeautifulSoup(text, 'html.parser')
                
                # Find the auth token
                auth_token = soup.find('meta', {'name': 'csrf-token'})
                if not auth_token or not auth_token.get('content'):
                    _LOGGER.warning("Connection failed - authentication token not found")
                    return None
                
                _LOGGER.debug("Authentication token successfully retrieved")
                return auth_token['content']
                
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
                    _LOGGER.warning("Login failed - server returned %s", response.status)
                    self._error_code = ERROR_INVALID_CREDENTIALS
                    return False
                
                # Get the XSRF token using the new method
                xsrf_token = await self._async_get_xsrf_token(response)
                if not xsrf_token:
                    _LOGGER.warning("Login failed - security token not received")
                    self._error_code = ERROR_XSRF_TOKEN_MISSING
                    return False
                
                # Update the cookies with any new ones from the login response
                self._cookies.update(response.cookies)
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
                        _LOGGER.debug("User ID not found, but continuing with device ID: %s", device_id)
                except Exception as user_id_err:
                    _LOGGER.debug("Error extracting user ID: %s", user_id_err)
                    _LOGGER.debug("Continuing with device ID: %s", device_id)

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
                
        except Exception as err:
            _LOGGER.error("Login error: %s", err)
            return False

    async def async_get_device_data(self, device_id: Optional[str] = None) -> Optional[dict[str, Any]]:
        """Get device data from the Leakomatic API, with 15-minute cache.
        
        Args:
            device_id: Optional device ID to get data for. If not provided, returns data for all devices.
            
        Returns:
            Optional[dict]: Device data for the specified device, or None if not found/error.
        """
        now = datetime.now(tz=timezone.utc)
        
        # If no device_id specified and we have multiple devices, return data for all devices
        if device_id is None and len(self._device_ids) > 1:
            result = {}
            for dev_id in self._device_ids:
                data = await self.async_get_device_data(dev_id)
                if data:
                    result[dev_id] = data
            return result if result else None
            
        # Use first device if none specified (backward compatibility)
        device_id = device_id or self.device_id
        if not device_id:
            return self._handle_error("Cannot fetch data - no device configured", return_value=None, level="warning")
            
        # Check cache for this specific device
        if (
            device_id in self._device_data_cache and
            device_id in self._device_data_cache_time and
            (now - self._device_data_cache_time[device_id]) < timedelta(minutes=15)
        ):
            return self._device_data_cache[device_id]
            
        # Ensure we're authenticated
        if not await self._ensure_authenticated():
            return None
            
        try:
            _LOGGER.debug("Fetching data for device with ID: %s", device_id)
            
            # Create a new session with the saved cookies
            async with await self._create_session() as session:
                # Construct the URL for the device status JSON
                url = f"{STATUS_URL}/{device_id}.json"
                
                async with session.get(url) as response:
                    if response.status != 200:
                        return self._handle_error(
                            f"Failed to fetch device data - server returned {response.status}",
                            return_value=None,
                            level="warning"
                        )
                    
                    # Update cookies and XSRF token from the response
                    await self._update_session_from_response(response)
                    
                    # Parse the JSON response
                    device_data = await response.json()
                    self._device_data_cache[device_id] = device_data
                    self._device_data_cache_time[device_id] = now
                    return device_data
                
        except Exception as err:
            return self._handle_error(f"Failed to fetch device data: {err}", return_value=None, level="error")

    async def async_close(self) -> None:
        """Close the client session."""
        if self._session:
            await self._session.close()
            self._session = None
            _LOGGER.debug("Closed connection to Leakomatic API")

    async def async_get_websocket_token(self) -> Optional[str]:
        """Get the websocket token from the device page."""
        if not self.device_ids:
            return self._handle_error("Cannot fetch websocket token - no devices configured", return_value=None, level="warning")
            
        # Ensure we're authenticated
        if not await self._ensure_authenticated():
            return None
            
        try:
            _LOGGER.debug("Fetching websocket token...")
            
            # Create a new session with the saved cookies
            async with await self._create_session() as session:
                # Construct the URL for the device status page (not JSON)
                url = f"{STATUS_URL}/{self.device_ids[0]}"
                
                async with session.get(url) as response:
                    if response.status != 200:
                        return self._handle_error(
                            f"Failed to fetch websocket token - server returned {response.status}",
                            return_value=None,
                            level="warning"
                        )
                    
                    # Update cookies and XSRF token from the response
                    await self._update_session_from_response(response)
                    
                    # Get the response text
                    text = await response.text()
                    
                    # Define a regular expression pattern to match the ws token
                    pattern = re.compile(r'token=([a-zA-Z0-9_.-]+)')
                    
                    # Search for the pattern in the response
                    match = pattern.search(text)
                    
                    if not match:
                        return self._handle_error(
                            "Websocket token not found in the response",
                            return_value=None,
                            level="warning"
                        )
                    
                    ws_token = match.group(1)
                    _LOGGER.debug("Websocket token retrieved successfully")
                    return ws_token
                
        except Exception as err:
            return self._handle_error(f"Failed to fetch websocket token: {err}", return_value=None, level="error")

    async def connect_to_websocket(self, ws_token: str, message_callback: Callable[[dict], None]) -> None:
        """Connect to the websocket server and listen for messages with persistent reconnection.
        
        Args:
            ws_token: The WebSocket token for authentication
            message_callback: Callback function to handle messages
        """
        # Store the callback
        self._ws_callbacks.append(message_callback)
        
        # Ensure we're authenticated
        if not await self._ensure_authenticated():
            _LOGGER.error("Failed to authenticate before WebSocket connection")
            return

        if not self._user_id:
            return self._handle_error("Cannot connect to websocket - no user ID available", return_value=None, level="error")

        # Start the persistent connection loop
        await self._persistent_websocket_connection(ws_token)

    async def stop_websocket(self) -> None:
        """Stop the websocket connection."""
        was_connected = self._ws_connected
        self._ws_running = False
        self._ws_connected = False
        
        # Notify connectivity callbacks if we were connected
        if was_connected:
            self._notify_connectivity_callbacks(False, self._reconnection_phase)
            
        _LOGGER.debug("Websocket connection stopped")

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
                _LOGGER.error("Failed to reconnect to Leakomatic API")
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
        if msg_type in (MessageType.PING.value, MessageType.CONFIRM_SUBSCRIPTION.value, MessageType.WELCOME.value):
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
            level: The log level to use ("error" or "warning").
        
        Returns:
            The specified return value.
        """
        # Remove any trailing periods from error messages
        error_msg = error_msg.rstrip('.')
        
        # Log the error without the component name (Home Assistant adds this automatically)
        if level == "error":
            _LOGGER.error(error_msg)
        else:
            _LOGGER.warning(error_msg)
        
        if error_code:
            self._error_code = error_code
            
        return return_value 

    async def _async_make_request(self, endpoint: str, data: dict, operation: str, device_id: Optional[str] = None) -> bool:
        """Make an HTTP request to the Leakomatic API.
        
        Args:
            endpoint: The API endpoint to call (e.g. 'change_mode.json' or 'reset_alarms.json')
            data: The data to send in the request
            operation: A description of the operation being performed (for logging)
            device_id: Optional device ID to make the request for. If not provided, uses the first device.
            
        Returns:
            bool: True if the request was successful, False otherwise
        """
        # Use first device if none specified (backward compatibility)
        device_id = device_id or self.device_id
        if not device_id:
            return self._handle_error(f"Cannot {operation} - no device configured", return_value=False, level="warning")
            
        # Ensure we're authenticated
        if not await self._ensure_authenticated():
            return False
            
        try:
            # Create headers for JSON content
            headers = {
                "Content-Type": "application/json;charset=UTF-8",
                "User-Agent": "Mozilla/5.0",
                "Connection": "close"
            }
            
            # Create a new session with the saved cookies and specific headers for JSON
            session = await self._create_session(headers=headers)
            try:
                # Construct the URL
                url = f"{STATUS_URL}/{device_id}/{endpoint}"
                
                _LOGGER.debug("Making %s request to %s for device %s", operation, url, device_id)
                
                async with session.post(url, json=data) as response:
                    # Get the response content
                    response_text = await response.text()
                    
                    if response.status != 200:
                        return self._handle_error(
                            f"Failed to {operation} - server returned {response.status}",
                            return_value=False,
                            level="warning"
                        )
                    
                    # Update cookies and XSRF token from the response
                    await self._update_session_from_response(response)
                    
                    # For 200 status code, consider it a success
                    _LOGGER.info("Successfully %s for device %s", operation, device_id)
                    return True
            finally:
                # Always close the session
                await session.close()
                
        except Exception as err:
            return self._handle_error(f"Failed to {operation}: {err}", return_value=False, level="error")

    async def async_change_mode(self, mode: str, device_id: Optional[str] = None) -> bool:
        """Change the mode of the Leakomatic device.
        
        Args:
            mode: The new mode to set. Must be one of: "home", "away", "pause".
            device_id: Optional device ID to change mode for. If not provided, changes mode for all devices.
            
        Returns:
            bool: True if the mode was changed successfully for all specified devices, False otherwise.
        """
        try:
            # Convert the string mode to a numeric value using the DeviceMode enum
            numeric_mode = DeviceMode.from_string(mode)
            
            # If no device_id specified and we have multiple devices, change mode for all devices
            if device_id is None and len(self._device_ids) > 1:
                results = []
                for dev_id in self._device_ids:
                    result = await self.async_change_mode(mode, dev_id)
                    results.append(result)
                return all(results)
            
            # Use first device if none specified (backward compatibility)
            device_id = device_id or self.device_id
            if not device_id:
                return self._handle_error("Cannot change mode - no device configured", return_value=False, level="warning")
                
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

    async def async_reset_alarms(self, device_id: Optional[str] = None) -> bool:
        """Reset all alarms on the Leakomatic device.
        
        Args:
            device_id: Optional device ID to reset alarms for. If not provided, resets alarms for all devices.
            
        Returns:
            bool: True if the alarms were reset successfully for all specified devices, False otherwise.
        """
        # If no device_id specified and we have multiple devices, reset alarms for all devices
        if device_id is None and len(self._device_ids) > 1:
            results = []
            for dev_id in self._device_ids:
                result = await self.async_reset_alarms(dev_id)
                results.append(result)
            return all(results)
            
        # Use first device if none specified (backward compatibility)
        device_id = device_id or self.device_id
        if not device_id:
            return self._handle_error("Cannot reset alarms - no device configured", return_value=False, level="warning")
            
        # Prepare the data for the request - array with alarm_ids
        data = {"alarm_ids": [0]}
        
        return await self._async_make_request(
            endpoint="reset_alarms.json",
            data=data,
            operation="reset alarms",
            device_id=device_id
        )

    async def disconnect(self) -> None:
        """Disconnect from the WebSocket server."""
        was_connected = self._ws_connected
        self._ws_running = False
        self._ws_connected = False
        self._ws_callbacks.clear()
        
        # Notify connectivity callbacks if we were connected
        if was_connected:
            self._notify_connectivity_callbacks(False, self._reconnection_phase)

    async def _persistent_websocket_connection(self, initial_ws_token: str) -> None:
        """Maintain a persistent WebSocket connection with multi-phase retry strategy."""
        ws_token = initial_ws_token
        quick_retry_count = 0
        medium_retry_count = 0
        retry_delay = INITIAL_RETRY_DELAY

        while self._ws_running:
            try:
                _LOGGER.debug("Attempting WebSocket connection (Phase %d)", self._reconnection_phase)
                
                # Refresh token if needed (every 24 hours or after long disconnection)
                if self._should_refresh_token():
                    _LOGGER.debug("Refreshing WebSocket token")
                    new_token = await self.async_get_websocket_token()
                    if new_token:
                        ws_token = new_token
                        self._ws_token_expiry = datetime.now(tz=timezone.utc) + timedelta(hours=24)
                    else:
                        _LOGGER.warning("Failed to refresh WebSocket token, using existing token")

                # Attempt connection
                success = await self._attempt_websocket_connection(ws_token)
                
                if success:
                    # Reset all retry counters on successful connection
                    quick_retry_count = 0
                    medium_retry_count = 0
                    retry_delay = INITIAL_RETRY_DELAY
                    self._reconnection_phase = 1
                    self._ws_connected = True
                    _LOGGER.info("WebSocket connection established successfully")
                    
                    # Notify connectivity callbacks
                    self._notify_connectivity_callbacks(True, self._reconnection_phase)
                    
                    # Start health check task
                    health_check_task = asyncio.create_task(self._health_check_loop())
                    
                    # Wait for connection to close
                    await self._wait_for_connection_close()
                    
                    # Cancel health check
                    health_check_task.cancel()
                    self._ws_connected = False
                    _LOGGER.warning("WebSocket connection closed, starting reconnection")
                    
                    # Notify connectivity callbacks
                    self._notify_connectivity_callbacks(False, self._reconnection_phase)
                    
                else:
                    # Handle reconnection based on current phase
                    if self._reconnection_phase == 1:
                        # Phase 1: Quick retries
                        quick_retry_count += 1
                        if quick_retry_count >= MAX_QUICK_RETRIES:
                            _LOGGER.info("Phase 1 retries exhausted, moving to Phase 2")
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
                            _LOGGER.info("Phase 2 retries exhausted, moving to Phase 3")
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
        """Attempt to establish a WebSocket connection.
        
        Returns:
            bool: True if connection was successful and maintained, False otherwise
        """
        try:
            # Construct the websocket URL
            ws_url = f"{WEBSOCKET_URL}?token={ws_token}"
            
            # Use a timeout for the connection to prevent blocking
            async with websockets.connect(
                ws_url,
                subprotocols=['actioncable-v1-json'],
                additional_headers=WEBSOCKET_HEADERS,
                ssl=ssl_context,
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

                # Listen for messages
                while self._ws_running:
                    try:
                        # Use a timeout for receiving messages to prevent blocking
                        response = await asyncio.wait_for(websocket.recv(), timeout=30)
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
                            _LOGGER.debug("Subscription confirmed")
                        else:
                            # For all other message types, call all callbacks
                            if msg_type:
                                device_identifier = parsed_response.get('message', {}).get('device', 'unknown')
                                _LOGGER.debug("Device %s received message %s", device_identifier, msg_type)
                                # Call all registered callbacks
                                for callback in self._ws_callbacks:
                                    try:
                                        callback(parsed_response)
                                    except Exception as e:
                                        _LOGGER.error("Error in WebSocket callback: %s", str(e))
                            else:
                                _LOGGER.warning("Unknown message type in response")

                    except asyncio.TimeoutError:
                        # This is expected and not an error - just continue the loop
                        continue
                    except websockets.ConnectionClosed:
                        _LOGGER.warning("Websocket connection closed")
                        return False
                    except Exception as err:
                        _LOGGER.error("Error processing websocket message: %s", err)
                        # Continue the loop to try to receive more messages
                        continue

        except Exception as err:
            _LOGGER.debug("WebSocket connection attempt failed: %s", err)
            return False

    async def _wait_for_connection_close(self) -> None:
        """Wait for the WebSocket connection to close naturally."""
        # This method can be used to wait for connection close events
        # For now, we'll just wait indefinitely since the connection loop handles everything
        while self._ws_connected and self._ws_running:
            await asyncio.sleep(1)

    async def _health_check_loop(self) -> None:
        """Periodic health check to detect stuck connections."""
        while self._ws_connected and self._ws_running:
            await asyncio.sleep(HEALTH_CHECK_INTERVAL)
            
            # Check if we've received any messages recently
            if self._last_ws_message:
                time_since_last_message = datetime.now(tz=timezone.utc) - self._last_ws_message
                if time_since_last_message > timedelta(minutes=10):
                    _LOGGER.warning("No WebSocket messages received for %d minutes, connection may be stuck", 
                                   time_since_last_message.seconds // 60)
                    # Force reconnection by breaking out of the connection loop
                    self._ws_connected = False

    def _should_refresh_token(self) -> bool:
        """Check if the WebSocket token should be refreshed."""
        if not self._ws_token_expiry:
            return True
        
        # Refresh if token expires within the next hour
        return datetime.now(tz=timezone.utc) + timedelta(hours=1) >= self._ws_token_expiry 