"""The Leakomatic integration."""
import logging
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntry, DeviceRegistry, async_get as async_get_device_registry
from homeassistant.helpers.entity_registry import EntityRegistry

from .const import DOMAIN, LOGGER_NAME, DEFAULT_NAME
from .leakomatic_client import LeakomaticClient

# Set up logger
_LOGGER = logging.getLogger(LOGGER_NAME)

PLATFORMS = ["sensor"]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Leakomatic from a config entry."""
    _LOGGER.debug("Setting up Leakomatic integration with config entry: %s", entry.entry_id)
    
    # Initialize the client
    client = LeakomaticClient(entry.data["email"], entry.data["password"])
    
    # Authenticate to get the device ID
    auth_success = await client.async_authenticate()
    if not auth_success:
        _LOGGER.error("Failed to authenticate with Leakomatic API")
        return False
    
    # Get the device ID
    device_id = client.device_id
    if not device_id:
        _LOGGER.error("No device ID found after authentication")
        return False
    
    _LOGGER.debug("Found device ID: %s", device_id)
    
    # Fetch device data to get the sw_version
    device_data = await client.async_get_device_data()        
    
    # If device data is available and contains sw_version, use it
    sw_version = "Unknown"  # Default value
    if device_data and "sw_version" in device_data:
        sw_version = device_data["sw_version"]
        _LOGGER.debug("Found sw_version: %s", sw_version)
    else:
        _LOGGER.warning("Could not find sw_version in device data, using default")

    # If device data is available and contains model, use it
    model = "Unknown"
    if device_data and "model_name" in device_data:
        model = device_data["model_name"]
        _LOGGER.debug("Found model: %s", model)
    else:
        _LOGGER.warning("Could not find model in device data, using default")
    
    # Create a device in Home Assistant
    device_registry = async_get_device_registry(hass)
    device_entry = device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, device_id)},
        name=f"{DEFAULT_NAME} {device_id}",
        manufacturer="Leakomatic",
        model=model,
        sw_version=sw_version,
    )
    
    # Update the device's sw_version if it changed
    if device_entry.sw_version != sw_version:
        device_registry.async_update_device(
            device_entry.id,
            sw_version=sw_version,
        )
        _LOGGER.debug("Updated device sw_version to: %s", sw_version)
    
    _LOGGER.debug("Created device in Home Assistant: %s", device_entry.id)
    
    # Store the client and device ID in hass.data
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "client": client,
        "device_id": device_id,
        "device_entry": device_entry,
    }
    
    # Set up platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    
    _LOGGER.info("Leakomatic integration setup completed for %s", entry.entry_id)
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.debug("Unloading Leakomatic integration for config entry: %s", entry.entry_id)
    
    # Unload platforms
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        # Close the client's session
        domain_data = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
        client = domain_data.get("client")
        if client:
            await client.async_close()
            
        hass.data[DOMAIN].pop(entry.entry_id, None)
        _LOGGER.info("Leakomatic integration unloaded successfully for %s", entry.entry_id)
    
    return unload_ok 