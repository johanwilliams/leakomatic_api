"""Constants for the Leakomatic integration."""
DOMAIN = "leakomatic"

# Default values
DEFAULT_NAME = "Leakomatic"
DEFAULT_SCAN_INTERVAL = 60  # seconds

# Logging
LOGGER_NAME = "custom_components.leakomatic"

# LEAKOMATIC URLs
START_URL = "https://cloud.leakomatic.com/login"
LOGIN_URL = "https://cloud.leakomatic.com:443/login"
STATUS_URL = "https://cloud.leakomatic.com/devices"
WEBSOCKET_URL = "wss://ws-api.leakomatic.com/cable"
