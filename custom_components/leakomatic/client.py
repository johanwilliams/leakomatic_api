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

    async def async_authenticate(self) -> bool:
        """Authenticate with the Leakomatic API."""
        try:
            _LOGGER.debug("Authenticating with Leakomatic API")
            
            # Create a new session
            self._session = aiohttp.ClientSession()
            
            # Get the auth token from the start page
            self._auth_token = await self._async_get_startpage()
            if not self._auth_token:
                _LOGGER.error("Failed to get auth token from start page")
                return False
            
            # Login with the auth token
            login_success = await self._async_login()
            if not login_success:
                _LOGGER.error("Failed to login with provided credentials")
                return False
            
            _LOGGER.info("Successfully authenticated with Leakomatic API")
            return True
            
        except Exception as err:
            _LOGGER.exception("Error authenticating with Leakomatic API: %s", err)
            return False
        finally:
            # Close the session when we're done
            if self._session:
                await self._session.close()
                self._session = None

    async def _async_get_startpage(self) -> Optional[str]:
        """Get the auth token from the start page."""
        try:
            _LOGGER.debug("Getting auth token from start page")
            
            async with self._session.get(START_URL) as response:
                if response.status != 200:
                    _LOGGER.error("Failed to get login page: %s", response.status)
                    return None
                
                text = await response.text()
                soup = BeautifulSoup(text, 'html.parser')
                
                # Find the auth token
                auth_token = soup.find('meta', {'name': 'csrf-token'})
                if not auth_token or not auth_token.get('content'):
                    _LOGGER.error("Could not find auth token in login page")
                    return None
                
                _LOGGER.debug("Successfully retrieved auth token")
                return auth_token['content']
                
        except Exception as err:
            _LOGGER.error("Error getting start page: %s", err)
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
                    _LOGGER.error("Login failed with status: %s", response.status)
                    return False
                
                # Get the XSRF token from cookies
                cookies = response.cookies
                xsrf_token = cookies.get('XSRF-TOKEN')
                if not xsrf_token:
                    _LOGGER.error("Failed to get XSRF token from cookies")
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
                        _LOGGER.error("Login error: %s", error.text.strip())
                    return False
                
                # Find all <tr> elements with an id attribute starting with 'device_'
                device_elements = soup.find_all('tr', {'id': lambda x: x and x.startswith('device_')})
                if not device_elements:
                    _LOGGER.error("No devices found after login - authentication may have failed")
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
                            _LOGGER.warning("User ID not found in href attribute")
                    else:
                        _LOGGER.warning("User ID not found, but continuing with device ID: %s", device_id)
                except Exception as user_id_err:
                    _LOGGER.warning("Error extracting user ID: %s", user_id_err)
                    _LOGGER.warning("Continuing with device ID: %s", device_id)
                
                _LOGGER.debug("Successfully logged in and found device ID: %s", device_id)
                return True
                
        except Exception as err:
            _LOGGER.error("Error during login: %s", err)
            return False 