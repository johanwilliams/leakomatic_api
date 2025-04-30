"""Support for Leakomatic binary sensors.

This module implements the binary sensor platform for the Leakomatic integration.
It provides binary sensors for:
- Flow indicator (water flowing or not)
- Online status (device online or offline)
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Optional

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
        """Initialize the binary sensor."""
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

# Message handler type definition
MessageHandler = Callable[[dict, list[LeakomaticBinarySensor]], None]

class MessageHandlerRegistry:
    """Registry for WebSocket message handlers."""
    
    def __init__(self) -> None:
        """Initialize the registry."""
        self._handlers: Dict[str, MessageHandler] = {}
        self._default_handler: Optional[MessageHandler] = None
    
    def register(self, message_type: str, handler: MessageHandler) -> None:
        """Register a handler for a specific message type."""
        self._handlers[message_type] = handler
    
    def register_default(self, handler: MessageHandler) -> None:
        """Register a default handler for unhandled message types."""
        self._default_handler = handler
    
    def handle_message(self, message: dict, sensors: list[LeakomaticBinarySensor]) -> None:
        """Handle a WebSocket message using the appropriate handler."""
        # Extract message type using the same logic as legacy code
        msg_type = ""
        attr_type = message.get("type")
        if attr_type is not None:
            msg_type = attr_type
        else:
            attr_operation = message.get('message', {}).get('operation', '')
            if attr_operation is not None:
                msg_type = attr_operation
        
        _LOGGER.debug("Processing WebSocket message with type/operation: %s", msg_type)
        
        # Get the appropriate handler
        handler = self._handlers.get(msg_type, self._default_handler)
        if handler:
            handler(message, sensors)
        else:
            _LOGGER.warning("No handler found for message type: %s", msg_type)

# Create a global registry instance
message_registry = MessageHandlerRegistry()

# Define message handlers
def handle_flow_update(message: dict, sensors: list[LeakomaticBinarySensor]) -> None:
    """Handle flow_updated messages."""
    data = message.get("message", {}).get("data", {})
    flow_mode = data.get("flow_mode")
    _LOGGER.debug("Received flow update - mode: %s", flow_mode)
    # Update flow indicator sensor
    sensors[0].handle_update({"flow_mode": flow_mode})
    # Update online status to True when receiving flow updates
    _LOGGER.debug("Setting online status to True due to flow_updated message")
    sensors[1].handle_update({"is_online": True})

def handle_device_update(message: dict, sensors: list[LeakomaticBinarySensor]) -> None:
    """Handle device_updated messages."""
    data = message.get("message", {}).get("data", {})
    _LOGGER.debug("Received device update - is_online: %s", data.get("is_online"))
    # Update online status sensor
    sensors[1].handle_update(data)

def handle_quick_test_update(message: dict, sensors: list[LeakomaticBinarySensor]) -> None:
    """Handle quick_test_updated messages."""
    _LOGGER.debug("Received quick test update - setting device as online")
    sensors[1].handle_update({"is_online": True})

def handle_tightness_test_update(message: dict, sensors: list[LeakomaticBinarySensor]) -> None:
    """Handle tightness_test_updated messages."""
    _LOGGER.debug("Received tightness test update - setting device as online")
    sensors[1].handle_update({"is_online": True})

def handle_default(message: dict, sensors: list[LeakomaticBinarySensor]) -> None:
    """Handle any other message type."""
    msg_type = message.get("type", message.get('message', {}).get('operation', 'unknown'))
    _LOGGER.debug("Received message type %s - setting device as online", msg_type)
    sensors[1].handle_update({"is_online": True})

# Register all handlers
message_registry.register("flow_updated", handle_flow_update)
message_registry.register("device_updated", handle_device_update)
message_registry.register("quick_test_updated", handle_quick_test_update)
message_registry.register("tightness_test_updated", handle_tightness_test_update)
message_registry.register_default(handle_default)

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
    binary_sensors = [
        FlowIndicatorBinarySensor(device_info, device_id, device_data),
        OnlineStatusBinarySensor(device_info, device_id, None),  # Initialize with None to start as unknown
    ]
    
    async_add_entities(binary_sensors)

    # Register callback for WebSocket updates
    @callback
    def handle_ws_message(message: dict) -> None:
        """Handle WebSocket messages."""
        message_registry.handle_message(message, binary_sensors)

    # Store the callback in hass.data for the WebSocket client to use
    domain_data["ws_callback"] = handle_ws_message


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

class OnlineStatusBinarySensor(LeakomaticBinarySensor):
    """Representation of a Leakomatic Online Status binary sensor.
    
    This sensor indicates whether the device is currently online (True) or offline (False).
    It is updated through WebSocket updates with device_updated operation.
    
    The sensor will be set to online (True) when receiving any of these message types:
    - flow_updated
    - quick_test_updated
    - tightness_test_updated
    
    The sensor will be set to offline (False) when receiving a device_updated message
    with is_online=False.
    
    The default state is unknown (None) until the first update is received.
    """

    def __init__(
        self,
        device_info: dict[str, Any],
        device_id: str,
        device_data: dict[str, Any] | None,
    ) -> None:
        """Initialize the online status binary sensor."""
        super().__init__(
            device_info=device_info,
            device_id=device_id,
            device_data=device_data,
            key="online_status",
            icon="mdi:wifi",
            device_class=BinarySensorDeviceClass.CONNECTIVITY,
        )
        _LOGGER.debug("OnlineStatusBinarySensor initialized with device_data: %s", device_data)

    @property
    def is_on(self) -> bool | None:
        """Return the state of the binary sensor."""
        if not self._device_data:
            _LOGGER.debug("No device data available - assuming unknown state")
            return None
        
        # Get the online status from the device data
        is_online = self._device_data.get("is_online")
        _LOGGER.debug("Reading online status value: %s (type: %s)", is_online, type(is_online).__name__)
        
        # Return True if device is online, False otherwise
        return bool(is_online)
        
    @callback
    def handle_update(self, data: dict[str, Any]) -> None:
        """Handle updated data from WebSocket."""
        _LOGGER.debug("OnlineStatusBinarySensor received update: %s", data)
        self._device_data = data
        self.async_write_ha_state()
        _LOGGER.debug("%s value updated: %s", self.name, self.is_on) 