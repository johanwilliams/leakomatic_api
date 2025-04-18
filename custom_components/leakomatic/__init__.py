"""The Leakomatic integration."""
import logging
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, LOGGER_NAME
from .client import LeakomaticClient

# Set up logger
_LOGGER = logging.getLogger(LOGGER_NAME)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Leakomatic from a config entry."""
    _LOGGER.debug("Setting up Leakomatic integration with config entry: %s", entry.entry_id)
    
    # Initialize the client
    client = LeakomaticClient(entry.data["email"], entry.data["password"])
    
    # Store the client in hass.data
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = client
    
    _LOGGER.info("Leakomatic integration setup completed for %s", entry.entry_id)
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.debug("Unloading Leakomatic integration for config entry: %s", entry.entry_id)
    hass.data[DOMAIN].pop(entry.entry_id, None)
    _LOGGER.info("Leakomatic integration unloaded successfully for %s", entry.entry_id)
    return True 