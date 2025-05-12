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
from typing import Any, Optional, Callable, Dict

import aiohttp
import websockets
from bs4 import BeautifulSoup
import urllib.parse
import json

from .const import (
    LOGGER_NAME, START_URL, LOGIN_URL, STATUS_URL, WEBSOCKET_URL,
    MessageType, DEFAULT_HEADERS, WEBSOCKET_HEADERS, MAX_RETRIES, RETRY_DELAY,
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

    def __init__(self, email: str, password: str) -> None:
        """Initialize the client.
        
        Args:
            email: The email address for authentication
            password: The password for authentication
        """
        self._email = email
        self._password = password
        self._auth_token: Optional[str] = None
        self._device_id: Optional[str] = None
        self._user_id: Optional[str] = None
        self._session: Optional[aiohttp.ClientSession] = None
        self._error_code: Optional[str] = None
        self._xsrf_token: Optional[str] = None
        self._cookies: Optional[aiohttp.CookieJar] = None
        self._ws_running = True
        self._ws_callbacks: list[Callable[[dict], None]] = []

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
            _LOGGER.debug("Adding XSRF token to session headers")
            headers[XSRF_TOKEN_HEADER] = urllib.parse.unquote(self._xsrf_token)
        else:
            _LOGGER.warning("No XSRF token available for session headers")
        
        _LOGGER.debug("Creating new session with cookies")
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
    def device_id(self) -> Optional[str]:
        """Get the device ID."""
        return self._device_id

    async def _async_get_startpage(self) -> Optional[str]:
        """Get the auth token from the start page."""
        try:
            _LOGGER.debug("Requesting authentication token from Leakomatic")
            
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
            _LOGGER.debug("Retrieved XSRF token successfully")
            return xsrf_token_value
        else:
            _LOGGER.warning("Failed to extract XSRF token using regex pattern")
            return None

    async def _async_login(self) -> bool:
        """Login to the Leakomatic API."""
        try:
            _LOGGER.debug("Attempting login with provided credentials")
            
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
                
                # Find all <tr> elements with an id attribute starting with 'device_'
                device_elements = soup.find_all('tr', {'id': lambda x: x and x.startswith('device_')})
                if not device_elements:
                    _LOGGER.warning("No Leakomatic devices found in account")
                    self._error_code = ERROR_NO_DEVICES_FOUND
                    return False
                
                # Get the first device ID (we'll handle multiple devices later)
                device_id = device_elements[0]['id'].replace('device_', '')
                self._device_id = device_id
                
                # Find the user ID - be careful with the href attribute
                try:
                    user_link = soup.find('a', href=lambda href: href and "/users/" in href)
                    if user_link and hasattr(user_link, 'attrs') and 'href' in user_link.attrs:
                        href = user_link.attrs['href']
                        if href and "/users/" in href:
                            user_id = href.split('/')[-1]
                            self._user_id = user_id
                            _LOGGER.debug("Found user ID: %s", user_id)
                        else:
                            _LOGGER.debug("User ID not found in href attribute")
                    else:
                        _LOGGER.debug("User ID not found, but continuing with device ID: %s", device_id)
                except Exception as user_id_err:
                    _LOGGER.debug("Error extracting user ID: %s", user_id_err)
                    _LOGGER.debug("Continuing with device ID: %s", device_id)
                
                _LOGGER.debug("Found Leakomatic device: %s", device_id)
                return True
                
        except Exception as err:
            _LOGGER.error("Login error: %s", err)
            return False

    async def async_get_device_data(self) -> Optional[dict[str, Any]]:
        """Get device data from the Leakomatic API."""
        if not self._device_id:
            return self._handle_error("Cannot fetch data - no device configured", return_value=None, level="warning")
            
        # Ensure we're authenticated
        if not await self._ensure_authenticated():
            return None
            
        try:
            _LOGGER.debug("Fetching data for device %s", self._device_id)
            
            # Create a new session with the saved cookies
            async with await self._create_session() as session:
                # Construct the URL for the device status JSON
                url = f"{STATUS_URL}/{self._device_id}.json"
                
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
                    
                    # Log only key information instead of the full JSON
                    if device_data:
                        _LOGGER.debug("Device data received - Mode: %s, Status: %s",
                                     device_data.get("mode", "unknown"),
                                     "ALARM" if device_data.get("alarm") else "OK")
                    
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
        if not self._device_id:
            return self._handle_error("Cannot fetch websocket token - no device configured", return_value=None, level="warning")
            
        # Ensure we're authenticated
        if not await self._ensure_authenticated():
            return None
            
        try:
            _LOGGER.debug("Fetching websocket token for device %s", self._device_id)
            
            # Create a new session with the saved cookies
            async with await self._create_session() as session:
                # Construct the URL for the device status page (not JSON)
                url = f"{STATUS_URL}/{self._device_id}"
                
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
        """Connect to the websocket server and listen for messages.
        
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

        # Construct the websocket URL
        ws_url = f"{WEBSOCKET_URL}?token={ws_token}"
        _LOGGER.debug("Connecting to websocket server")

        # Reconnection parameters
        retry_count = 0

        while self._ws_running and retry_count < MAX_RETRIES:
            try:
                _LOGGER.debug("Attempting WebSocket connection (attempt %d)", retry_count + 1)
                
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
                                    _LOGGER.debug("Received message of type %s", msg_type)
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
                            _LOGGER.warning("Websocket connection closed, attempting to reconnect")
                            break  # Break out of the inner loop to attempt reconnection
                        except Exception as err:
                            _LOGGER.error("Error processing websocket message: %s", err)
                            # Continue the loop to try to receive more messages
                            continue

            except Exception as err:
                retry_count += 1
                if retry_count < MAX_RETRIES:
                    _LOGGER.info("Waiting %d seconds before reconnection attempt %d", RETRY_DELAY, retry_count + 1)
                    await asyncio.sleep(RETRY_DELAY)
                else:
                    return self._handle_error(
                        f"Maximum reconnection attempts reached ({MAX_RETRIES}). Giving up.",
                        return_value=None,
                        level="error"
                    )

    async def stop_websocket(self) -> None:
        """Stop the websocket connection."""
        self._ws_running = False
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
        else:
            _LOGGER.debug("Using existing XSRF token")
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

    async def _async_make_request(self, endpoint: str, data: dict, operation: str) -> bool:
        """Make an HTTP request to the Leakomatic API.
        
        Args:
            endpoint: The API endpoint to call (e.g. 'change_mode.json' or 'reset_alarms.json')
            data: The data to send in the request
            operation: A description of the operation being performed (for logging)
            
        Returns:
            bool: True if the request was successful, False otherwise
        """
        if not self._device_id:
            return self._handle_error(f"Cannot {operation} - no device configured", return_value=False, level="warning")
            
        # Ensure we're authenticated
        if not await self._ensure_authenticated():
            return False
            
        try:
            _LOGGER.debug("%s for device %s", operation.capitalize(), self._device_id)
            
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
                url = f"{STATUS_URL}/{self._device_id}/{endpoint}"
                
                _LOGGER.debug("Requesting URL %s", url)
                
                async with session.post(url, json=data) as response:
                    _LOGGER.debug("Response status: %d", response.status)
                    
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
                    _LOGGER.info("Successfully %s for device %s", operation, self._device_id)
                    return True
            finally:
                # Always close the session
                await session.close()
                
        except Exception as err:
            return self._handle_error(f"Failed to {operation}: {err}", return_value=False, level="error")

    async def async_change_mode(self, mode: str) -> bool:
        """Change the mode of the Leakomatic device.
        
        Args:
            mode: The new mode to set. Must be one of: "home", "away", "pause".
            
        Returns:
            bool: True if the mode was changed successfully, False otherwise.
        """
        try:
            # Convert the string mode to a numeric value using the DeviceMode enum
            numeric_mode = DeviceMode.from_string(mode)
            _LOGGER.debug("Changing mode to %s (numeric value: %d) for device %s", mode, numeric_mode, self._device_id)
            
            # Prepare the data for the request
            data = {
                "mode": numeric_mode
            }
            
            # Log the request data
            _LOGGER.debug("Mode change request data: %s", data)
            
            result = await self._async_make_request(
                endpoint="change_mode.json",
                data=data,
                operation=f"change mode to {mode}"
            )
            
            # Log the result
            _LOGGER.debug("Mode change result: %s", result)
            
            return result
                
        except ValueError as err:
            return self._handle_error(str(err), return_value=False, level="warning")

    async def async_reset_alarms(self) -> bool:
        """Reset all alarms on the Leakomatic device.
        
        Returns:
            bool: True if the alarms were reset successfully, False otherwise.
        """
        # Prepare the data for the request - array with alarm_ids
        data = {"alarm_ids": [0]}
        
        return await self._async_make_request(
            endpoint="reset_alarms.json",
            data=data,
            operation="reset alarms"
        )

    async def disconnect(self) -> None:
        """Disconnect from the WebSocket server."""
        self._ws_running = False
        self._ws_callbacks.clear()
        if self._ws:
            await self._ws.close()
            self._ws = None 