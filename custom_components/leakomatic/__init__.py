"""The Leakomatic integration.

This integration connects Home Assistant to Leakomatic water leak detection devices.
It provides real-time monitoring of device status, including:
- Device mode (Home/Away/Pause)
- Alarm status
- Device information and metrics
- Real-time updates via WebSocket connection
"""
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo, async_get as async_get_device_registry

from .const import DOMAIN, LOGGER_NAME, DEFAULT_NAME, ERROR_INVALID_CREDENTIALS
from .config_flow import account_unique_id
from .leakomatic_client import LeakomaticClient
from .availability import ConnectionAvailability
from .models import LeakomaticConfigEntry, LeakomaticData

# Set up logger
_LOGGER = logging.getLogger(LOGGER_NAME)

PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.SELECT, Platform.BUTTON]

# Title that config entries created before 0.2.0 got automatically
_OLD_TITLE_PREFIX = "Leakomatic Device "


@callback
def _migrate_entry(hass: HomeAssistant, entry: ConfigEntry, client: LeakomaticClient) -> None:
    """Bring an entry created before 0.2.0 up to date, once logged in.

    It gets the account's unique ID, loses the unused device_id, and its
    automatic title ("Leakomatic Device <first device>") becomes the email.
    A title the user has changed is kept.
    """
    updates: dict[str, Any] = {}
    if entry.unique_id is None:
        updates["unique_id"] = account_unique_id(client, entry.data[CONF_EMAIL])
    if "device_id" in entry.data:
        updates["data"] = {k: v for k, v in entry.data.items() if k != "device_id"}
    if entry.title.startswith(_OLD_TITLE_PREFIX):
        updates["title"] = entry.data[CONF_EMAIL]
    if updates:
        _LOGGER.debug("Updating config entry %s: %s", entry.entry_id, sorted(updates))
        hass.config_entries.async_update_entry(entry, **updates)


@callback
def _remove_stale_devices(hass: HomeAssistant, entry: ConfigEntry, device_ids: set[str]) -> None:
    """Remove devices of this entry that are no longer on the Leakomatic account."""
    device_registry = async_get_device_registry(hass)
    for device in dr.async_entries_for_config_entry(device_registry, entry.entry_id):
        leakomatic_ids = {identifier for domain, identifier in device.identifiers if domain == DOMAIN}
        if leakomatic_ids and not leakomatic_ids & device_ids:
            _LOGGER.info("Removing Leakomatic device %s: no longer on the account", device.name)
            device_registry.async_update_device(device.id, remove_config_entry_id=entry.entry_id)


async def async_setup_entry(hass: HomeAssistant, entry: LeakomaticConfigEntry) -> bool:
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
        bool: True if setup was successful

    Raises:
        ConfigEntryAuthFailed: The email or password was rejected; starts reauthentication.
        ConfigEntryNotReady: Leakomatic could not be reached or gave no usable data;
            Home Assistant retries the setup by itself.
    """
    client = LeakomaticClient(entry.data[CONF_EMAIL], entry.data[CONF_PASSWORD], hass)
    try:
        return await _async_setup(hass, entry, client)
    except BaseException:
        # Setup failed (Home Assistant retries it with a new client): close
        # this client's HTTP session instead of leaving it open until shutdown.
        await client.async_close()
        raise


async def _async_setup(hass: HomeAssistant, entry: LeakomaticConfigEntry, client: LeakomaticClient) -> bool:
    """Set up the entry with a client; see async_setup_entry."""
    _LOGGER.debug("Setting up Leakomatic integration with config entry: %s", entry.entry_id)


    # Authenticate to get the device IDs. Only rejected credentials start a
    # reauthentication; everything else is treated as temporary and retried.
    if not await client.async_authenticate():
        if client.error_code == ERROR_INVALID_CREDENTIALS:
            raise ConfigEntryAuthFailed("Leakomatic rejected the email or password")
        raise ConfigEntryNotReady(
            f"Could not log in to Leakomatic ({client.error_code or 'unknown error'})"
        )

    _migrate_entry(hass, entry, client)

    # Get the device IDs
    device_ids = client.device_ids
    if not device_ids:
        raise ConfigEntryNotReady("No Leakomatic devices found in the account")
    
    # Fetch every device's data. If one is missing, retry the whole setup
    # rather than leave that device out until the next reload.
    device_data: dict[str, dict[str, Any]] = {}
    for device_id in device_ids:
        data = await client.async_get_device_data(device_id)
        if not data:
            raise ConfigEntryNotReady(f"Could not fetch the data of Leakomatic device {device_id}")
        device_data[device_id] = data

    # Create device entries for each device
    device_registry = async_get_device_registry(hass)

    device_infos: dict[str, DeviceInfo] = {}
    initial_device_data: dict[str, dict[str, Any]] = {}

    for device_id in device_ids:
        # Get data for this specific device
        dev_data = device_data.get(device_id)
        if not dev_data:
            _LOGGER.warning("No data found for device %s", device_id)
            continue

        # Store the device_identifier (serial number) if available
        device_identifier = None
        if "device_identifier" in dev_data:
            device_identifier = dev_data["device_identifier"]
        else:
            _LOGGER.warning("%s: No device identifier found in device data", device_id)
            continue
        
        name = f"{DEFAULT_NAME} {device_id}"
        if "name" in dev_data:
            name = dev_data["name"]
        else:
            _LOGGER.warning("%s: Could not find name in device data, using %s", device_id, name)
        
        # If device data is available and contains sw_version, use it
        sw_version = "Unknown"
        if "sw_version" in dev_data and "sw_release" in dev_data:
            sw_version = f"{dev_data['sw_release']}-{dev_data['sw_version']}"
        else:
            _LOGGER.warning("%s: Could not find software version in device data", device_id)

        model = "Unknown"
        if "model_name" in dev_data:
            model = dev_data["model_name"]
        else:
            _LOGGER.warning("%s: Could not find model in device data", device_id)

        location = None
        if "location" in dev_data:
            location = dev_data["location"]
        else:
            _LOGGER.warning("%s: Could not find location in device data", device_id)

        model_id = None
        if "product_id" in dev_data:
            model_id = dev_data["product_id"]
        else:
            _LOGGER.warning("%s: Could not find product id in device data", device_id)

        _LOGGER.debug("Creating device entry for device %s with name '%s' in suggested area '%s'. Model: %s, Product ID: %s, Software version: %s, Device identifier: %s", device_id, name, location, model, model_id, sw_version, device_identifier)
        
        # Create device entry
        identifiers = {(DOMAIN, str(device_id))}
        device_entry = device_registry.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers=identifiers,
            name=name,
            manufacturer="Leakomatic",
            model=model,
            sw_version=sw_version,
            suggested_area=location,
            serial_number=device_identifier,
            model_id=model_id
        )
        
        # Device info for the entities, built from the device entry. The
        # serial number is what websocket messages are matched against.
        device_infos[device_id] = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            name=device_entry.name,
            manufacturer=device_entry.manufacturer,
            model=device_entry.model,
            sw_version=device_entry.sw_version,
            serial_number=device_identifier,
        )
        initial_device_data[device_id] = dev_data

    if not device_infos:
        raise ConfigEntryNotReady("The device data from Leakomatic did not describe any usable device")

    _remove_stale_devices(hass, entry, set(device_infos))

    entry.runtime_data = LeakomaticData(
        client=client,
        device_infos=device_infos,
        device_data=initial_device_data,
        availability=ConnectionAvailability(hass),
    )

    # Mark the entities unavailable when the websocket stays disconnected.
    client.register_connectivity_callback(entry.runtime_data.availability.async_connectivity_changed)
    entry.async_on_unload(entry.runtime_data.availability.async_stop)

    # If Leakomatic rejects the credentials later (for example when the client
    # logs in again after the session expired), ask the user for a new password.
    client.set_auth_failed_callback(lambda: entry.async_start_reauth(hass))
    entry.async_on_unload(lambda: client.set_auth_failed_callback(None))

    # Set up platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    @callback
    def dispatch_ws_message(message: dict) -> None:
        """Pass a websocket message to every registered listener.

        Each listener is called separately so that an error in one platform
        does not stop the message from reaching the others.
        """
        for listener in list(entry.runtime_data.ws_listeners):
            try:
                listener(message)
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Error handling websocket message")

    # Start the websocket connection after the platforms are set up. The loop
    # gets its own token and retries until it connects, so it is always started.
    # Tie it to the config entry: Home Assistant cancels it when the entry is
    # unloaded, also while it sleeps between retries.
    entry.async_create_background_task(
        hass,
        client.connect_to_websocket(dispatch_ws_message),
        "Leakomatic WebSocket Connection",
    )
    _LOGGER.debug("Started websocket connection task")
    
    _LOGGER.info("Leakomatic integration setup completed")
    return True

async def async_unload_entry(hass: HomeAssistant, entry: LeakomaticConfigEntry) -> bool:
    """Unload a config entry.

    This function:
    1. Stops the websocket connection
    2. Unloads all platforms (their websocket listeners are removed with them)

    Args:
        hass: The Home Assistant instance
        entry: The config entry to unload

    Returns:
        bool: True if unload was successful, False otherwise
    """
    _LOGGER.debug("Unloading Leakomatic integration with config entry: %s", entry.entry_id)

    await entry.runtime_data.client.stop_websocket()

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        await entry.runtime_data.client.async_close()
        _LOGGER.info("Leakomatic integration unloaded successfully for %s", entry.entry_id)

    return unload_ok