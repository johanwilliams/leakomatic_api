"""The Leakomatic integration.

This integration connects Home Assistant to Leakomatic water leak detection devices.
It provides real-time monitoring of device status, including:
- Device mode (Home/Away/Pause)
- Alarm status
- Device information and metrics
- Real-time updates via WebSocket connection
"""
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

async def handle_ws_message(message: dict) -> None:
    """Handle websocket messages by logging them.
    
    This function serves as a callback for the WebSocket connection,
    processing incoming messages from the Leakomatic device.
    
    Args:
        message: The message received from the WebSocket connection
    """
    _LOGGER.debug("Received websocket message: %s", message)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Leakomatic from a config entry.
    
    This function:
    1. Authenticates with the Leakomatic API
    2. Retrieves device information
    3. Sets up the WebSocket connection for real-time updates
    4. Creates the device entity in Home Assistant
    5. Sets up the sensor platform
    
    Args:
        hass: The Home Assistant instance
        entry: The config entry to set up
        
    Returns:
        bool: True if setup was successful, False otherwise
    """
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

    # Get the websocket token
    ws_token = await client.async_get_websocket_token()
    if not ws_token:
        _LOGGER.warning("Could not get websocket token, websocket functionality will not be available")
    else:
        _LOGGER.debug("Successfully retrieved websocket token")
        # Start websocket connection
        hass.async_create_task(client.connect_to_websocket(ws_token, handle_ws_message))
        _LOGGER.debug("Started websocket connection task")

    name = f"{DEFAULT_NAME} {device_id}"
    if device_data and "name" in device_data:
        name = device_data["name"]
        _LOGGER.debug("Found name: %s", name)
    else:
        _LOGGER.warning("Could not find name in device data, using default")
    
    # If device data is available and contains sw_version, use it
    sw_version = "Unknown"
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

    location = None
    if device_data and "location" in device_data:
        location = device_data["location"]
        _LOGGER.debug("Found location: %s", location)
    else:
        _LOGGER.warning("Could not find location in device data, using default")
    
    # Create a device in Home Assistant
    device_registry = async_get_device_registry(hass)
    device_entry = device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, device_id)},
        name=name,
        manufacturer="Leakomatic",
        model=model,
        sw_version=sw_version,
        suggested_area=location
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
        "ws_token": ws_token,  # Store the websocket token
    }
    
    # Set up platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    
    _LOGGER.info("Leakomatic integration setup completed for %s", entry.entry_id)
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry.
    
    This function:
    1. Unloads all platforms
    2. Closes the client session
    3. Cleans up the integration data
    
    Args:
        hass: The Home Assistant instance
        entry: The config entry to unload
        
    Returns:
        bool: True if unload was successful, False otherwise
    """
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