"""Client for the Leakomatic API."""
from __future__ import annotations

import logging
import re
from typing import Any, Optional

import aiohttp
from bs4 import BeautifulSoup
import urllib.parse

from .const import LOGGER_NAME, START_URL, LOGIN_URL, STATUS_URL, WEBSOCKET_URL

_LOGGER = logging.getLogger(LOGGER_NAME)

class LeakomaticClient:
    """Client for the Leakomatic API."""

    def __init__(self, email: str, password: str) -> None:
        """Initialize the client."""
        self._email = email
        self._password = password
        self._auth_token: Optional[str] = None
        self._device_id: Optional[str] = None
        self._user_id: Optional[str] = None
        self._session: Optional[aiohttp.ClientSession] = None
        self._error_code: Optional[str] = None

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
                self._error_code = "auth_token_missing"
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
        # Don't close the session here, we'll keep it open for subsequent requests
    
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
            
            headers = {
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": "Mozilla/5.0"
            }
            
            async with self._session.post(LOGIN_URL, data=login_data, headers=headers) as response:
                if response.status != 200:
                    _LOGGER.warning("Login failed - server returned %s", response.status)
                    self._error_code = "invalid_credentials"
                    return False
                
                # Get the XSRF token from cookies
                cookies = response.cookies
                xsrf_token = cookies.get('XSRF-TOKEN')
                if not xsrf_token:
                    _LOGGER.warning("Login failed - security token not received")
                    self._error_code = "xsrf_token_missing"
                    return False
                
                # Set the XSRF token in session headers - convert to string first
                xsrf_token_str = str(xsrf_token)
                self._session.headers['X-Xsrf-Token'] = urllib.parse.unquote(xsrf_token_str)
                
                # Check if login was successful by looking for device elements
                text = await response.text()
                soup = BeautifulSoup(text, 'html.parser')
                
                # Check for error messages
                error_messages = soup.find_all('div', class_='alert-danger')
                if error_messages:
                    for error in error_messages:
                        _LOGGER.warning("Login failed - %s", error.text.strip())
                    self._error_code = "invalid_credentials"
                    return False
                
                # Find all <tr> elements with an id attribute starting with 'device_'
                device_elements = soup.find_all('tr', {'id': lambda x: x and x.startswith('device_')})
                if not device_elements:
                    _LOGGER.warning("No Leakomatic devices found in account")
                    self._error_code = "no_devices_found"
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
            _LOGGER.error("Cannot fetch data - no device configured")
            return None
            
        if not self._session:
            _LOGGER.debug("Reconnecting to Leakomatic API")
            self._session = aiohttp.ClientSession()
            
            auth_success = await self.async_authenticate()
            if not auth_success:
                _LOGGER.error("Failed to reconnect to Leakomatic API")
                return None
            
        try:
            _LOGGER.debug("Fetching data for device %s", self._device_id)
            
            # Construct the URL for the device status JSON
            url = f"{STATUS_URL}/{self._device_id}.json"
            _LOGGER.debug("Requesting URL: %s", url)
            
            async with self._session.get(url) as response:
                if response.status != 200:
                    _LOGGER.warning("Failed to fetch device data - server returned %s", response.status)
                    return None
                
                # Parse the JSON response
                device_data = await response.json()
                
                # Log only key information instead of the full JSON
                if device_data:
                    _LOGGER.debug("Device data received - Mode: %s, Status: %s",
                                 device_data.get("mode", "unknown"),
                                 "ALARM" if device_data.get("alarm") else "OK")
                    
                    # Log the raw mode value for debugging
                    _LOGGER.debug("Raw mode value: %s, type: %s", 
                                 device_data.get("mode"), 
                                 type(device_data.get("mode")).__name__)
                
                return device_data
                
        except Exception as err:
            _LOGGER.error("Failed to fetch device data: %s", err)
            return None
        # Don't close the session here, we'll keep it open for subsequent requests

    async def async_close(self) -> None:
        """Close the client session."""
        if self._session:
            await self._session.close()
            self._session = None
            _LOGGER.debug("Closed connection to Leakomatic API")

    async def async_get_websocket_token(self) -> Optional[str]:
        """Get the websocket token from the device page."""
        if not self._device_id:
            _LOGGER.error("Cannot fetch websocket token - no device configured")
            return None
            
        if not self._session:
            _LOGGER.debug("Reconnecting to Leakomatic API")
            self._session = aiohttp.ClientSession()
            
            auth_success = await self.async_authenticate()
            if not auth_success:
                _LOGGER.error("Failed to reconnect to Leakomatic API")
                return None
            
        try:
            _LOGGER.debug("Fetching websocket token for device %s", self._device_id)
            
            # Construct the URL for the device status page (not JSON)
            url = f"{STATUS_URL}/{self._device_id}"
            _LOGGER.debug("Requesting URL: %s", url)
            
            async with self._session.get(url) as response:
                if response.status != 200:
                    _LOGGER.warning("Failed to fetch websocket token - server returned %s", response.status)
                    return None
                
                # Get the response text
                text = await response.text()
                
                # Define a regular expression pattern to match the ws token
                pattern = re.compile(r'token=([a-zA-Z0-9_.-]+)')
                
                # Search for the pattern in the response
                match = pattern.search(text)
                
                if not match:
                    _LOGGER.warning("Websocket token not found in the response")
                    return None
                
                ws_token = match.group(1)
                _LOGGER.debug("Websocket token retrieved successfully")
                return ws_token
                
        except Exception as err:
            _LOGGER.error("Failed to fetch websocket token: %s", err)
            return None 