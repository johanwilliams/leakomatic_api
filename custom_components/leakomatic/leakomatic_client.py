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
            _LOGGER.debug("Authenticating with Leakomatic API")
            
            # Create a new session
            self._session = aiohttp.ClientSession()
            
            # Get the auth token from the start page
            self._auth_token = await self._async_get_startpage()
            if not self._auth_token:
                _LOGGER.warning("Failed to get auth token from start page")
                self._error_code = "auth_token_missing"
                return False
            
            # Login with the auth token
            login_success = await self._async_login()
            if not login_success:
                _LOGGER.warning("Failed to login with provided credentials")
                return False
            
            _LOGGER.info("Successfully authenticated with Leakomatic API")
            return True
            
        except Exception as err:
            _LOGGER.error("Unexpected error during authentication: %s", err)
            return False
        finally:
            # Close the session when we're done
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
            _LOGGER.debug("Getting auth token from start page")
            
            async with self._session.get(START_URL) as response:
                if response.status != 200:
                    _LOGGER.warning("Failed to get login page: %s", response.status)
                    return None
                
                text = await response.text()
                soup = BeautifulSoup(text, 'html.parser')
                
                # Find the auth token
                auth_token = soup.find('meta', {'name': 'csrf-token'})
                if not auth_token or not auth_token.get('content'):
                    _LOGGER.warning("Could not find auth token in login page")
                    return None
                
                _LOGGER.debug("Successfully retrieved auth token")
                return auth_token['content']
                
        except Exception as err:
            _LOGGER.error("Unexpected error getting start page: %s", err)
            return None

    async def _async_login(self) -> bool:
        """Login to the Leakomatic API."""
        try:
            _LOGGER.debug("Attempting to login")
            
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
                    _LOGGER.warning("Login failed with status: %s", response.status)
                    self._error_code = "invalid_credentials"
                    return False
                
                # Get the XSRF token from cookies
                cookies = response.cookies
                xsrf_token = cookies.get('XSRF-TOKEN')
                if not xsrf_token:
                    _LOGGER.warning("Failed to get XSRF token from cookies")
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
                        _LOGGER.warning("Login error: %s", error.text.strip())
                    self._error_code = "invalid_credentials"
                    return False
                
                # Find all <tr> elements with an id attribute starting with 'device_'
                device_elements = soup.find_all('tr', {'id': lambda x: x and x.startswith('device_')})
                if not device_elements:
                    _LOGGER.warning("No devices found after login - authentication may have failed")
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
                
                _LOGGER.debug("Successfully logged in and found device ID: %s", device_id)
                return True
                
        except Exception as err:
            _LOGGER.error("Unexpected error during login: %s", err)
            return False
            
    async def async_get_device_data(self) -> Optional[dict[str, Any]]:
        """Get device data from the Leakomatic API."""
        if not self._device_id:
            _LOGGER.error("No device ID available")
            return None
            
        if not self._session:
            _LOGGER.debug("Creating a new session for device data request")
            self._session = aiohttp.ClientSession()
            
        try:
            _LOGGER.debug("Getting device data for device ID: %s", self._device_id)
            
            # Construct the URL for the device status
            url = f"{STATUS_URL}/{self._device_id}"
            _LOGGER.debug("Requesting URL: %s", url)
            
            async with self._session.get(url) as response:
                if response.status != 200:
                    _LOGGER.warning("Failed to get device data: %s", response.status)
                    return None
                
                # Parse the response
                text = await response.text()
                soup = BeautifulSoup(text, 'html.parser')
                
                # Extract device data
                device_data = {}
                
                # Get device name
                device_name_elem = soup.find('h1')
                if device_name_elem:
                    device_data["name"] = device_name_elem.text.strip()
                
                # Get device status
                status_elem = soup.find('div', class_='status')
                if status_elem:
                    device_data["status"] = status_elem.text.strip()
                
                # Get device model
                model_elem = soup.find('div', class_='model')
                if model_elem:
                    device_data["model"] = model_elem.text.strip()
                
                # Get device location
                location_elem = soup.find('div', class_='location')
                if location_elem:
                    device_data["location"] = location_elem.text.strip()
                
                # Get device battery level
                battery_elem = soup.find('div', class_='battery')
                if battery_elem:
                    battery_text = battery_elem.text.strip()
                    battery_match = re.search(r'(\d+)%', battery_text)
                    if battery_match:
                        device_data["battery"] = int(battery_match.group(1))
                
                # Get device moisture level
                moisture_elem = soup.find('div', class_='moisture')
                if moisture_elem:
                    moisture_text = moisture_elem.text.strip()
                    moisture_match = re.search(r'(\d+(?:\.\d+)?)%', moisture_text)
                    if moisture_match:
                        device_data["moisture"] = float(moisture_match.group(1))
                
                _LOGGER.debug("Device data: %s", device_data)
                return device_data
                
        except Exception as err:
            _LOGGER.error("Unexpected error getting device data: %s", err)
            return None
        finally:
            # Close the session when we're done
            if self._session:
                await self._session.close()
                self._session = None 