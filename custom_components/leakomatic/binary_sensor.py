"""Support for Leakomatic binary sensors.

This module implements the binary sensor platform for the Leakomatic integration.
It provides binary sensors for:
- Flow indicator (water flowing or not)
- Online status (device online or offline)
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Optional
from datetime import datetime, timezone

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorDeviceClass,
    EntityCategory,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import DeviceInfo

from .const import DOMAIN, MessageType
from .common import LeakomaticEntity, MessageHandlerRegistry

_LOGGER = logging.getLogger(__name__)

class LeakomaticBinarySensor(LeakomaticEntity, BinarySensorEntity):
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
        super().__init__(
            device_info=device_info,
            device_id=device_id,
            device_data=device_data,
            key=key,
            icon=icon,
        )
        self._attr_device_class = device_class

# Create a global registry instance
message_registry = MessageHandlerRegistry[LeakomaticBinarySensor]()

# Define message handlers
def handle_flow_update(message: dict, sensors: list[LeakomaticBinarySensor]) -> None:
    """Handle flow_updated messages."""
    data = message.get("message", {}).get("data", {})
    _LOGGER.debug("Received flow update - Flow Mode: %s", data.get("flow_mode"))
    # Update all relevant sensors
    for sensor in sensors:
        if isinstance(sensor, FlowIndicatorBinarySensor):
            sensor.handle_update(data)
        elif isinstance(sensor, OnlineStatusBinarySensor):
            sensor.handle_update({"is_online": True}, update_last_seen=True)

def handle_device_update(message: dict, sensors: list[LeakomaticBinarySensor]) -> None:
    """Handle device_updated messages."""
    data = message.get("message", {}).get("data", {})
    _LOGGER.debug("Received device update - Online: %s, Port State: %s", 
                 data.get("is_online"), 
                 data.get("port_state"))
    # Update all relevant sensors
    for sensor in sensors:
        if isinstance(sensor, OnlineStatusBinarySensor):
            sensor.handle_update(data, update_last_seen=True)
        elif isinstance(sensor, ValveBinarySensor):
            sensor.handle_update(data)

def handle_quick_test_update(message: dict, sensors: list[LeakomaticBinarySensor]) -> None:
    """Handle quick_test_updated messages."""
    data = message.get("message", {}).get("data", {})
    value = data.get("value")
    _LOGGER.debug("Received quick test update - value: %s", value)
    # Update online status for any message
    for sensor in sensors:
        if isinstance(sensor, OnlineStatusBinarySensor):
            sensor.handle_update({"is_online": True}, update_last_seen=True)

def handle_tightness_test_update(message: dict, sensors: list[LeakomaticBinarySensor]) -> None:
    """Handle tightness_test_updated messages."""
    data = message.get("message", {}).get("data", {})
    _LOGGER.debug("Received tightness test update - data: %s", data)
    # Update online status for any message
    for sensor in sensors:
        if isinstance(sensor, OnlineStatusBinarySensor):
            sensor.handle_update({"is_online": True}, update_last_seen=True)

def handle_status_update(message: dict, sensors: list[LeakomaticBinarySensor]) -> None:
    """Handle status_message messages."""
    data = message.get("message", {}).get("data", {})
    _LOGGER.debug("Received status message - Port State: %s", 
                 data.get("port_state"))
    # Update all relevant sensors
    for sensor in sensors:
        if isinstance(sensor, ValveBinarySensor):
            sensor.handle_update(data)
        elif isinstance(sensor, OnlineStatusBinarySensor):
            sensor.handle_update({"is_online": True}, update_last_seen=True)

def handle_ping(message: dict, sensors: list[LeakomaticBinarySensor]) -> None:
    """Handle ping messages.
    
    For ping messages, we don't update the last_seen timestamp since we want to
    rely on the existing last_seen to determine if the device is online (within 5 minutes)
    or offline (more than 5 minutes since last seen).
    """
    _LOGGER.debug("Received ping message")
    # Update online status based on last_seen timestamp
    for sensor in sensors:
        if isinstance(sensor, OnlineStatusBinarySensor):
            # Pass empty data since we only care about the last_seen timestamp
            sensor.handle_update({}, update_last_seen=False)

def handle_device_offline(message: dict, sensors: list[LeakomaticBinarySensor]) -> None:
    """Handle device_offline messages."""
    _LOGGER.debug("Received device_offline message")
    # Set all online status sensors to offline
    for sensor in sensors:
        if isinstance(sensor, OnlineStatusBinarySensor):
            # Don't update last_seen for device_offline messages
            sensor.handle_update({"is_online": False}, update_last_seen=False)

def handle_default(message: dict, sensors: list[LeakomaticBinarySensor]) -> None:
    """Handle any other message type."""
    msg_type = message.get("type", message.get('message', {}).get('operation', 'unknown'))
    _LOGGER.debug("Received unhandled message type %s", msg_type)

# Register all handlers
message_registry.register(MessageType.FLOW_UPDATED.value, handle_flow_update)
message_registry.register(MessageType.DEVICE_UPDATED.value, handle_device_update)
message_registry.register(MessageType.QUICK_TEST_UPDATED.value, handle_quick_test_update)
message_registry.register(MessageType.TIGHTNESS_TEST_UPDATED.value, handle_tightness_test_update)
message_registry.register(MessageType.STATUS_MESSAGE.value, handle_status_update)
message_registry.register(MessageType.PING.value, handle_ping)
message_registry.register(MessageType.DEVICE_OFFLINE.value, handle_device_offline)
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
        OnlineStatusBinarySensor(device_info, device_id, device_data),  # Pass the initial device data
        ValveBinarySensor(device_info, device_id, device_data),
    ]
    
    async_add_entities(binary_sensors)

    # Register callback for WebSocket updates
    @callback
    def handle_ws_message(message: dict) -> None:
        """Handle WebSocket messages."""
        message_registry.handle_message(message, binary_sensors)

    # Store the callback in hass.data for the WebSocket client to use
    if "ws_callbacks" not in domain_data:
        domain_data["ws_callbacks"] = []
    domain_data["ws_callbacks"].append(handle_ws_message)


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
        # Initialize with flow_mode = 0 since the API always sends 1 in initial data
        if device_data is not None:
            device_data = device_data.copy()
            device_data["flow_mode"] = 0
            
        super().__init__(
            device_info=device_info,
            device_id=device_id,
            device_data=device_data,
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

    @callback
    def handle_update(self, data: dict[str, Any]) -> None:
        """Handle updated data from WebSocket."""
        _LOGGER.debug("FlowIndicatorBinarySensor received update: %s", data)
        self._device_data = data
        self.async_write_ha_state()
        _LOGGER.debug("%s value updated: %s", self.name, self.is_on)

class OnlineStatusBinarySensor(LeakomaticBinarySensor):
    """Representation of a Leakomatic Online Status binary sensor.
    
    This sensor indicates whether the device is currently online (True) or offline (False).
    It is updated through WebSocket updates with device_updated operation.
    
    The sensor will be set to online (True) when receiving any message from the device.
    The sensor will be set to offline (False) when the device hasn't been seen for more than 5 minutes.
    
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
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._last_seen: datetime | None = None
        
        # If we have initial device data with last_seen_at, parse it
        if device_data and "last_seen_at" in device_data:
            try:
                # Parse the ISO format timestamp from the device data
                # Remove microseconds for consistent format
                parsed_time = datetime.fromisoformat(device_data["last_seen_at"].replace("Z", "+00:00"))
                self._last_seen = parsed_time.replace(microsecond=0)
            except (ValueError, TypeError) as err:
                _LOGGER.warning("Failed to parse last_seen_at from device data: %s", err)

    @property
    def is_on(self) -> bool | None:
        """Return the state of the binary sensor."""
        if not self._device_data:
            return None
        
        # If we have a last_seen timestamp, use it to determine online status
        if self._last_seen:
            now = datetime.now(timezone.utc).replace(microsecond=0)
            minutes_since_last_seen = (now - self._last_seen).total_seconds() / 60
            
            is_online = minutes_since_last_seen < 5  # 5 minutes timeout
            return is_online
        
        # If no last_seen timestamp, use the is_online value directly
        is_online = self._device_data.get("is_online")
        return bool(is_online)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        # Get base attributes from parent class
        attrs = super().extra_state_attributes or {}
        
        # Add our custom last_seen attribute
        if self._last_seen:
            attrs["last_seen"] = self._last_seen.isoformat()
        
        return attrs

    @callback
    def handle_update(self, data: dict[str, Any], update_last_seen: bool = True) -> None:
        """Handle updated data from WebSocket.
        
        Args:
            data: The data to update the sensor with
            update_last_seen: Whether to update the last_seen timestamp
        """
        # Update last_seen based on the data or current time
        if update_last_seen:
            if "last_seen_at" in data:
                try:
                    # Parse the ISO format timestamp from the device data
                    # Remove microseconds for consistent format
                    parsed_time = datetime.fromisoformat(data["last_seen_at"].replace("Z", "+00:00"))
                    self._last_seen = parsed_time.replace(microsecond=0)
                except (ValueError, TypeError) as err:
                    _LOGGER.warning("Failed to parse last_seen_at from device data: %s", err)
                    # Fall back to current time if parsing fails
                    self._last_seen = datetime.now(timezone.utc).replace(microsecond=0)
            else:
                # If no last_seen_at in data, use current time
                self._last_seen = datetime.now(timezone.utc).replace(microsecond=0)
            
        self._device_data = data
        self.async_write_ha_state()

class ValveBinarySensor(LeakomaticBinarySensor):
    """Representation of a Leakomatic Valve binary sensor.
    
    This sensor indicates whether the valve is currently open or closed.
    It is updated through WebSocket updates with device_updated operation.
    
    The valve state is determined by checking the 8th bit (bit 7) of the port_state:
    - If bit 7 is 1 → valve is closed
    - If bit 7 is 0 → valve is open
    """

    def __init__(
        self,
        device_info: dict[str, Any],
        device_id: str,
        device_data: dict[str, Any] | None,
    ) -> None:
        """Initialize the valve binary sensor."""
        super().__init__(
            device_info=device_info,
            device_id=device_id,
            device_data=device_data,
            key="valve",
            icon="mdi:valve",
            device_class=BinarySensorDeviceClass.OPENING,
        )

    @property
    def is_on(self) -> bool | None:
        """Return the state of the binary sensor."""
        if not self._device_data:
            return None
        
        # Get the port state from the device data
        port_state = self._device_data.get("port_state")
        if port_state is None:
            return None
            
        # Check if the 8th bit (bit 7) is set
        # If bit 7 is 1 → valve is closed (is_on = False)
        # If bit 7 is 0 → valve is open (is_on = True)
        return (port_state & (1 << 7)) == 0

    @callback
    def handle_update(self, data: dict[str, Any]) -> None:
        """Handle updated data from WebSocket."""
        port_state = data.get("port_state")
        if port_state is not None:
            valve_state = "open" if (port_state & (1 << 7)) == 0 else "closed"
            _LOGGER.debug("Valve state changed to %s", valve_state)
        self._device_data = data
        self.async_write_ha_state() 