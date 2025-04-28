"""Constants for the Leakomatic integration."""
from enum import Enum

DOMAIN = "leakomatic"

# Default values
DEFAULT_NAME = "Leakomatic"

# Logging
LOGGER_NAME = "custom_components.leakomatic"

# LEAKOMATIC URLs
START_URL = "https://cloud.leakomatic.com/login"
LOGIN_URL = "https://cloud.leakomatic.com:443/login"
STATUS_URL = "https://cloud.leakomatic.com/devices"
WEBSOCKET_URL = "wss://ws-api.leakomatic.com/cable"

# Message types from the Leakomatic websocket
class MessageType(Enum):
    """Message types from the Leakomatic websocket.
    
    These types represent the various messages that can be received from the
    Leakomatic WebSocket API, including system messages and device updates.
    """
    WELCOME = "welcome"  # Initial connection welcome message
    PING = "ping"  # Keep-alive ping message
    CONFIRM_SUBSCRIPTION = "confirm_subscription"  # Subscription confirmation
    QUICK_TEST_UPDATED = "quick_test_updated"  # Quick test status update
    TIGHTNESS_TEST_UPDATED = "tightness_test_updated"  # Tightness test status update
    FLOW_UPDATED = "flow_updated"  # Water flow status update
    DEVICE_UPDATED = "device_updated"  # General device status update
    STATUS_MESSAGE = "status_message"  # General status message
    CONFIGURATION_ADDED = "configuration_added"  # Configuration change notification
    ALARM_TRIGGERED = "alarm_triggered"  # Alarm event notification

# Device operating modes
class DeviceMode(Enum):
    """Device operating modes.
    
    These modes represent the different operating states of a Leakomatic device.
    The numeric values (0, 1, 2) are used in the API, while the string values
    (home, away, pause) are used in the Home Assistant UI.
    """
    HOME = 0  # Home mode - normal operation
    AWAY = 1  # Away mode - reduced sensitivity
    PAUSE = 2  # Pause mode - monitoring paused
    
    @classmethod
    def from_string(cls, mode_str: str) -> int:
        """Convert a string mode to its numeric value.
        
        Args:
            mode_str: The string mode (home, away, pause)
            
        Returns:
            int: The numeric value (0, 1, 2)
            
        Raises:
            ValueError: If the mode string is invalid
        """
        try:
            return cls[mode_str.upper()].value
        except KeyError:
            raise ValueError(f"Invalid mode: {mode_str}. Must be one of: home, away, pause")

# HTTP Headers
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Content-Type": "application/x-www-form-urlencoded"
}
XSRF_TOKEN_HEADER = "X-Xsrf-Token"

# WebSocket Headers
WEBSOCKET_HEADERS = {
    "Accept-Encoding": "gzip, deflate, br",
    "Accept-Language": "en-US,en;q=0.9,sv;q=0.8",
    "Cache-Control": "no-cache",
    "Host": "ws-api.leakomatic.com",
    "Origin": "https://cloud.leakomatic.com",
    "Pragma": "no-cache",
    "User-Agent": "Mozilla/5.0"
}

# Reconnection Parameters
MAX_RETRIES = 5
RETRY_DELAY = 60  # seconds

# Error Codes
ERROR_AUTH_TOKEN_MISSING = "auth_token_missing"
ERROR_INVALID_CREDENTIALS = "invalid_credentials"
ERROR_XSRF_TOKEN_MISSING = "xsrf_token_missing"
ERROR_NO_DEVICES_FOUND = "no_devices_found"
