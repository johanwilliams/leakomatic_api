"""Support for Leakomatic sensors.

This module implements the sensor platform for the Leakomatic integration.
It provides sensors for:
- Device mode (Home/Away/Pause)
- Device status and metrics
- Alarm conditions
- Quick test index
- Flow duration

The sensors are updated through real-time WebSocket updates.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Optional

from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.typing import StateType

from .const import DOMAIN, DEFAULT_NAME

_LOGGER = logging.getLogger(__name__)

class LeakomaticSensor(SensorEntity):
    """Base class for all Leakomatic sensors.
    
    This class implements common functionality shared between all Leakomatic sensors.
    """

    def __init__(
        self,
        device_info: dict[str, Any],
        device_id: str,
        device_data: dict[str, Any] | None,
        *,
        key: str,
        icon: str,
        device_class: SensorDeviceClass | None = None,
        state_class: SensorStateClass | None = None,
        native_unit_of_measurement: str | None = None,
    ) -> None:
        """Initialize the sensor."""
        self._device_info = device_info
        self._device_id = device_id
        self._device_data = device_data or {}
        
        self._attr_has_entity_name = True
        self._attr_unique_id = f"{device_id}_{key}"
        self._attr_device_class = device_class
        self._attr_native_unit_of_measurement = native_unit_of_measurement
        self._attr_state_class = state_class
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
        _LOGGER.debug("%s value updated: %s", self.name, self.native_value)

# Message handler type definition
MessageHandler = Callable[[dict, list[LeakomaticSensor]], None]

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
    
    def handle_message(self, message: dict, sensors: list[LeakomaticSensor]) -> None:
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
def handle_device_update(message: dict, sensors: list[LeakomaticSensor]) -> None:
    """Handle device_updated messages."""
    data = message.get("message", {}).get("data", {})
    _LOGGER.debug("Received device update - Mode: %s, Status: %s", 
                 data.get("mode"), 
                 data.get("status"))
    # Update all sensors with the new data
    for sensor in sensors:
        sensor.handle_update(data)

def handle_default(message: dict, sensors: list[LeakomaticSensor]) -> None:
    """Handle any other message type."""
    msg_type = message.get("type", message.get('message', {}).get('operation', 'unknown'))
    _LOGGER.debug("Received unhandled message type: %s", msg_type)

# Register all handlers
message_registry.register("device_updated", handle_device_update)
message_registry.register_default(handle_default)

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
    
    # Create sensors
    sensors = [
        ModeSensor(device_info, device_id, device_data),
        QuickTestSensor(device_info, device_id, device_data),
        FlowDurationSensor(device_info, device_id, device_data),
        SignalStrengthSensor(device_info, device_id, device_data),
    ]
    
    async_add_entities(sensors)
    
    # Register callback for WebSocket updates
    @callback
    def handle_ws_message(message: dict) -> None:
        """Handle WebSocket messages."""
        message_registry.handle_message(message, sensors)

    # Store the callback in hass.data for the WebSocket client to use
    if "ws_callbacks" not in domain_data:
        domain_data["ws_callbacks"] = []
    domain_data["ws_callbacks"].append(handle_ws_message)


class ModeSensor(LeakomaticSensor):
    """Representation of a Leakomatic Mode sensor.
    
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
        """Initialize the mode sensor."""
        super().__init__(
            device_info=device_info,
            device_id=device_id,
            device_data=device_data,
            key="mode",
            icon="mdi:home",
        )

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


class QuickTestSensor(LeakomaticSensor):
    """Representation of a Leakomatic Quick Test sensor.
    
    This sensor represents the quick test index of the Leakomatic device.
    It is updated through WebSocket updates.
    """

    def __init__(
        self,
        device_info: dict[str, Any],
        device_id: str,
        device_data: dict[str, Any] | None,
    ) -> None:
        """Initialize the quick test sensor."""
        super().__init__(
            device_info=device_info,
            device_id=device_id,
            device_data=device_data,
            key="quick_test",
            icon="mdi:water",
            state_class=SensorStateClass.MEASUREMENT,
        )

    @property
    def native_value(self) -> StateType:
        """Return the state of the sensor."""
        if not self._device_data:
            _LOGGER.debug("No device data available")
            return None
        
        # Get the quick test value - try both possible field names
        value = self._device_data.get("value")
        if value is not None:
            _LOGGER.debug("Found quick test value in 'value' field: %s (type: %s)", 
                         value, type(value).__name__)
        else:
            value = self._device_data.get("current_quick_test")
            if value is not None:
                _LOGGER.debug("Found quick test value in 'current_quick_test' field: %s (type: %s)", 
                             value, type(value).__name__)
        
        if value is not None:
            try:
                return round(float(value), 2)  # Round to 2 decimal places
            except (ValueError, TypeError):
                _LOGGER.warning("Invalid quick test value: %s (type: %s)", 
                              value, type(value).__name__)
                return None
        
        return None


class FlowDurationSensor(LeakomaticSensor):
    """Representation of a Leakomatic Last Flow Duration sensor.
    
    This sensor represents the duration of the last completed flow in seconds.
    It is updated through WebSocket updates when a flow completes (flow_mode = 0).
    Home Assistant will automatically format the duration in an appropriate unit
    (days, hours, minutes, seconds) based on the value.
    """

    def __init__(
        self,
        device_info: dict[str, Any],
        device_id: str,
        device_data: dict[str, Any] | None,
    ) -> None:
        """Initialize the flow duration sensor."""
        super().__init__(
            device_info=device_info,
            device_id=device_id,
            device_data=device_data,
            key="flow_duration",
            icon="mdi:clock-outline",
            device_class=SensorDeviceClass.DURATION,
            state_class=SensorStateClass.MEASUREMENT,
            native_unit_of_measurement="s"
        )

    @property
    def native_value(self) -> StateType:
        """Return the state of the sensor."""
        if not self._device_data:
            _LOGGER.debug("No device data available")
            return None
        
        # Get the flow duration value - try both possible field names
        value = self._device_data.get("value")
        if value is not None:
            _LOGGER.debug("Found flow duration in 'value' field: %s (type: %s)", 
                         value, type(value).__name__)
        else:
            value = self._device_data.get("current_flow_duration")
            if value is not None:
                _LOGGER.debug("Found flow duration in 'current_flow_duration' field: %s (type: %s)", 
                             value, type(value).__name__)
        
        if value is not None:
            try:
                # Ensure the value is an integer number of seconds
                return int(float(value))
            except (ValueError, TypeError):
                _LOGGER.warning("Invalid flow duration value: %s (type: %s)", 
                              value, type(value).__name__)
                return None
        
        return None


class SignalStrengthSensor(LeakomaticSensor):
    """Representation of a Leakomatic Signal Strength sensor.
    
    This sensor represents the WiFi signal strength (RSSI) of the Leakomatic device.
    It is updated through WebSocket updates with status_message operation.
    """

    def __init__(
        self,
        device_info: dict[str, Any],
        device_id: str,
        device_data: dict[str, Any] | None,
    ) -> None:
        """Initialize the signal strength sensor."""
        super().__init__(
            device_info=device_info,
            device_id=device_id,
            device_data=device_data,
            key="signal_strength",
            icon="mdi:wifi",
            device_class=SensorDeviceClass.SIGNAL_STRENGTH,
            state_class=SensorStateClass.MEASUREMENT,
            native_unit_of_measurement="dBm"
        )
        self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def native_value(self) -> StateType:
        """Return the state of the sensor."""
        if not self._device_data:
            _LOGGER.debug("No device data available")
            return None
        
        # Get the RSSI value
        rssi = self._device_data.get("rssi")
        if rssi is not None:
            try:
                return int(rssi)  # RSSI should be an integer
            except (ValueError, TypeError):
                _LOGGER.warning("Invalid RSSI value: %s (type: %s)", 
                              rssi, type(rssi).__name__)
                return None
        
        return None 