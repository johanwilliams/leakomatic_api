"""Support for Leakomatic sensors.

This module implements the sensor platform for the Leakomatic integration.
It provides sensors for:
- Device mode (Home/Away/Pause)
- Device status and metrics
- Alarm conditions

The sensors are updated through real-time WebSocket updates.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.typing import StateType

from .const import DOMAIN, DEFAULT_NAME

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Leakomatic sensor.
    
    This function:
    1. Gets the device information from the config entry
    2. Creates and adds the sensor entities
    
    Args:
        hass: The Home Assistant instance
        config_entry: The config entry to set up sensors for
        async_add_entities: Callback to register new entities
    """
    _LOGGER.debug("Setting up Leakomatic sensor for config entry: %s", config_entry.entry_id)
    
    # Get the client and device ID from hass.data
    domain_data = hass.data.get(DOMAIN, {}).get(config_entry.entry_id, {})
    client = domain_data.get("client")
    device_id = domain_data.get("device_id")
    device_entry = domain_data.get("device_entry")
    
    if not client or not device_id or not device_entry:
        _LOGGER.error("Missing client, device ID, or device entry")
        return
    
    # Create device info dictionary using the device entry's information
    device_info = {
        "identifiers": {(DOMAIN, device_id)},
        "name": device_entry.name,
        "manufacturer": device_entry.manufacturer,
        "model": device_entry.model,
        "sw_version": device_entry.sw_version,
    }
    
    # Get initial device data
    device_data = await client.async_get_device_data()
    
    # Add the sensor
    sensor = LeakomaticSensor(device_info, device_id, device_data)
    async_add_entities([sensor])

    # Register callback for WebSocket updates
    @callback
    def handle_ws_message(message: dict) -> None:
        """Handle WebSocket messages."""
        # Extract message type using the same logic as legacy code
        msg_type = ""
        # Try to extract the "type" (which exists in some messages)
        attr_type = message.get("type")
        if attr_type is not None:
            msg_type = attr_type
        else:
            # We found no type, let's look for "operation" attribute
            attr_operation = message.get('message', {}).get('operation', '')
            if attr_operation is not None:
                msg_type = attr_operation
        
        _LOGGER.debug("Processing WebSocket message with type/operation: %s", msg_type)
        
        if msg_type == "device_updated":
            data = message.get("message", {}).get("data", {})
            _LOGGER.debug("Updating sensor with new device mode: %s (raw message: %s)", 
                         data.get("mode"), message)
            sensor.handle_update(data)

    # Store the callback in hass.data for the WebSocket client to use
    domain_data["ws_callback"] = handle_ws_message


class LeakomaticSensor(SensorEntity):
    """Representation of a Leakomatic sensor.
    
    This sensor represents the mode of the Leakomatic device (Home/Away/Pause).
    It is updated through WebSocket updates.
    
    Attributes:
        _device_info: Information about the physical device
        _device_id: The unique identifier of the device
        _attr_name: The name of the sensor
        _attr_unique_id: The unique identifier for this sensor
        _attr_icon: The icon to use for this sensor
        _device_data: The current device data
    """

    def __init__(
        self,
        device_info: dict[str, Any],
        device_id: str,
        device_data: dict[str, Any] | None,
    ) -> None:
        """Initialize the sensor."""
        self._device_info = device_info
        self._device_id = device_id
        self._device_data = device_data or {}
        self._attr_name = f"{DEFAULT_NAME} Mode"
        self._attr_unique_id = f"{device_id}_mode"
        self._attr_device_class = None  # No specific device class for mode
        self._attr_native_unit_of_measurement = None  # No unit for mode
        self._attr_state_class = None  # No state class for mode
        self._attr_icon = "mdi:home"  # Icon for mode
        self._attr_entity_registry_enabled_default = True
        self._attr_should_poll = False  # No polling needed with WebSocket
        self._attr_translation_key = "mode"  # Key for state translations

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device info."""
        return self._device_info

    @property
    def native_value(self) -> StateType:
        """Return the state of the sensor."""
        if not self._device_data:
            _LOGGER.debug("No device data available")
            return None
        
        # Get the mode from the device data
        mode = self._device_data.get("mode")
        _LOGGER.debug("Reading mode value: %s (type: %s)", mode, type(mode).__name__)
        
        # Return the numeric value as a string - translations will be handled by HA
        if mode in (0, 1, 2):
            return str(mode)
        else:
            _LOGGER.debug("Unknown mode value: %s", mode)
            return "unknown"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        if not self._device_data:
            return {}
        
        # Extract relevant attributes from the device data
        attributes = {}
        
        # Add alarm status
        if "alarm" in self._device_data:
            attributes["alarm"] = self._device_data["alarm"]
        
        # Add device name
        if "name" in self._device_data:
            attributes["name"] = self._device_data["name"]
        
        # Add device model
        if "model" in self._device_data:
            attributes["model"] = self._device_data["model"]
        
        # Add software version
        if "sw_version" in self._device_data:
            attributes["sw_version"] = self._device_data["sw_version"]
        
        # Add last seen time
        if "last_seen_at" in self._device_data:
            attributes["last_seen_at"] = self._device_data["last_seen_at"]
        
        return attributes

    @callback
    def handle_update(self, device_data: dict[str, Any]) -> None:
        """Handle updated data from WebSocket."""
        _LOGGER.debug("Handling update with device data: %s", device_data)
        self._device_data = device_data
        _LOGGER.debug("Mode value before state update: %s", self._device_data.get("mode"))
        self.async_write_ha_state()
        _LOGGER.debug("State update completed. Current mode: %s", self.native_value) 