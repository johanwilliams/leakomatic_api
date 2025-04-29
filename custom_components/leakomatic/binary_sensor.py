"""Support for Leakomatic binary sensors.

This module implements the binary sensor platform for the Leakomatic integration.
It provides binary sensors for:
- Flow indicator (water flowing or not)
"""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorDeviceClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import DeviceInfo

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Leakomatic binary sensor.
    
    This function:
    1. Gets the device information from the config entry
    2. Creates and adds the binary sensor entities
    
    Args:
        hass: The Home Assistant instance
        config_entry: The config entry to set up binary sensors for
        async_add_entities: Callback to register new entities
    """
    _LOGGER.debug("Setting up Leakomatic binary sensor for config entry: %s", config_entry.entry_id)
    
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
    
    # Create binary sensors
    flow_indicator = FlowIndicatorBinarySensor(device_info, device_id, device_data)
    async_add_entities([flow_indicator])

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
        
        if msg_type == "flow_updated":
            data = message.get("message", {}).get("data", {})
            flow_mode = data.get("flow_mode")
            _LOGGER.debug("Received flow update - mode: %s", flow_mode)
            # Update flow indicator sensor
            flow_indicator.handle_update({"flow_mode": flow_mode})

    # Store the callback in hass.data for the WebSocket client to use
    domain_data["ws_callback"] = handle_ws_message


class LeakomaticBinarySensor(BinarySensorEntity):
    """Base class for all Leakomatic binary sensors.
    
    This class implements common functionality shared between all Leakomatic binary sensors.
    """

    def __init__(
        self,
        device_info: dict[str, Any],
        device_id: str,
        device_data: dict[str, Any] | None,
        *,
        key: str,
        icon: str,
        device_class: BinarySensorDeviceClass | None = None,
    ) -> None:
        """Initialize the binary sensor.
        
        Args:
            device_info: Information about the physical device
            device_id: The unique identifier of the device
            device_data: The current device data
            key: Unique key/identifier for the sensor
            icon: MDI icon to use
            device_class: The device class of the sensor
        """
        self._device_info = device_info
        self._device_id = device_id
        self._device_data = device_data or {}
        
        self._attr_has_entity_name = True
        self._attr_unique_id = f"{device_id}_{key}"
        self._attr_device_class = device_class
        self._attr_icon = icon
        self._attr_entity_registry_enabled_default = True
        self._attr_should_poll = False  # No polling needed with WebSocket
        self._attr_translation_key = key

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device info."""
        return self._device_info

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        if not self._device_data:
            return {}
        
        # Extract relevant attributes from the device data
        attributes = {}
        
        # Add common attributes that all sensors might want to expose
        for attr in ["alarm", "name", "model", "sw_version", "last_seen_at"]:
            if attr in self._device_data:
                attributes[attr] = self._device_data[attr]
        
        return attributes

    @callback
    def handle_update(self, data: dict[str, Any]) -> None:
        """Handle updated data from WebSocket."""
        self._device_data = data
        self.async_write_ha_state()
        _LOGGER.debug("%s value updated: %s", self.name, self.is_on)


class FlowIndicatorBinarySensor(LeakomaticBinarySensor):
    """Representation of a Leakomatic Flow Indicator binary sensor.
    
    This sensor indicates whether water is currently flowing (1) or not (0).
    It is updated through WebSocket updates.
    
    Note: There appears to be a bug in the API where flow_mode is always 1
    regardless of actual water flow. Therefore, we initialize the sensor as
    unknown and only update its state through WebSocket flow_updated events.
    
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
        """Initialize the flow indicator binary sensor."""
        super().__init__(
            device_info=device_info,
            device_id=device_id,
            device_data=None,  # Initialize with no data to start as unknown
            key="flow_indicator",
            icon="mdi:water",
            device_class=BinarySensorDeviceClass.RUNNING,
        )

    @property
    def is_on(self) -> bool | None:
        """Return the state of the binary sensor."""
        if not self._device_data:
            _LOGGER.debug("No device data available - assuming unknown state")
            return None
        
        # Get the flow mode from the device data
        flow_mode = self._device_data.get("flow_mode")
        _LOGGER.debug("Reading flow mode value: %s (type: %s)", flow_mode, type(flow_mode).__name__)
        
        # Return True if water is flowing (flow_mode = 1), False otherwise
        return flow_mode == 1 