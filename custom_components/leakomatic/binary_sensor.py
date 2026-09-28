"""Support for Leakomatic binary sensors.

This module implements the binary sensor platform for the Leakomatic integration.
It provides binary sensors for:
- Flow indicator (water flowing or not)
- Online status (device online or offline)
"""
from __future__ import annotations

import logging
from typing import Any
from datetime import datetime, timedelta, timezone

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorDeviceClass,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util

from .const import DEVICE_OFFLINE_AFTER, MessageType
from .common import LeakomaticEntity, MessageHandlerRegistry, LeakomaticMessageHandler, log_with_entity
from .models import LeakomaticConfigEntry

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
    LeakomaticMessageHandler.handle_flow_update(
        message, 
        sensors, 
        FlowIndicatorBinarySensor, 
        OnlineStatusBinarySensor
    )

def handle_device_update(message: dict, sensors: list[LeakomaticBinarySensor]) -> None:
    """Handle device_updated messages.

    Only marks the device as online. The flow indicator is driven by
    flow_updated alone: device data can carry a stale flow_mode of 1.
    """
    LeakomaticMessageHandler.handle_device_update(
        message,
        sensors,
        None,
        OnlineStatusBinarySensor
    )

def handle_quick_test_update(message: dict, sensors: list[LeakomaticBinarySensor]) -> None:
    """Handle quick_test_updated messages."""
    LeakomaticMessageHandler.handle_quick_test_update(
        message, 
        sensors, 
        None,  # No quick test binary sensor
        OnlineStatusBinarySensor
    )

def handle_tightness_test_update(message: dict, sensors: list[LeakomaticBinarySensor]) -> None:
    """Handle tightness_test_updated messages."""
    LeakomaticMessageHandler.handle_tightness_test_update(
        message, 
        sensors, 
        None,  # No tightness test binary sensor
        OnlineStatusBinarySensor
    )

def handle_status_update(message: dict, sensors: list[LeakomaticBinarySensor]) -> None:
    """Handle status_message messages."""
    LeakomaticMessageHandler.handle_status_update(
        message, 
        sensors, 
        ValveBinarySensor, 
        OnlineStatusBinarySensor
    )

def handle_ping(message: dict, sensors: list[LeakomaticBinarySensor]) -> None:
    """Handle ping messages."""
    LeakomaticMessageHandler.handle_ping(
        message, 
        sensors, 
        OnlineStatusBinarySensor
    )

def handle_device_offline(message: dict, sensors: list[LeakomaticBinarySensor]) -> None:
    """Handle device_offline messages."""
    LeakomaticMessageHandler.handle_device_offline(
        message, 
        sensors, 
        OnlineStatusBinarySensor
    )

def handle_alarm_triggered(message: dict, sensors: list[LeakomaticBinarySensor]) -> None:
    """Handle alarm_triggered messages."""
    LeakomaticMessageHandler.handle_alarm_triggered(
        message, 
        sensors, 
        (),  # No alarm binary sensors
        OnlineStatusBinarySensor
    )

def handle_default(message: dict, sensors: list[LeakomaticBinarySensor]) -> None:
    """Handle any other message type."""
    LeakomaticMessageHandler.handle_default(message, sensors)

# Register all handlers
message_registry.register(MessageType.FLOW_UPDATED.value, handle_flow_update)
message_registry.register(MessageType.DEVICE_UPDATED.value, handle_device_update)
message_registry.register(MessageType.QUICK_TEST_UPDATED.value, handle_quick_test_update)
message_registry.register(MessageType.TIGHTNESS_TEST_UPDATED.value, handle_tightness_test_update)
message_registry.register(MessageType.STATUS_MESSAGE.value, handle_status_update)
message_registry.register(MessageType.PING.value, handle_ping)
message_registry.register(MessageType.DEVICE_OFFLINE.value, handle_device_offline)
message_registry.register(MessageType.ALARM_TRIGGERED.value, handle_alarm_triggered)
message_registry.register_default(handle_default)

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: LeakomaticConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Leakomatic binary sensor.
    
    This function:
    1. Gets the device information from the config entry
    2. Creates and adds the binary sensor entities for each device
    
    Args:
        hass: The Home Assistant instance
        config_entry: The config entry to set up binary sensors for
        async_add_entities: Callback to register new entities
    """
    _LOGGER.debug("Setting up Leakomatic binary sensor for config entry: %s", config_entry.entry_id)
    data = config_entry.runtime_data
    client = data.client

    # Create binary sensors for each device
    all_binary_sensors = []
    for device_id, device_info in data.device_infos.items():
        dev_data = data.device_data[device_id]

        # Create binary sensors for this device
        device_binary_sensors = [
            FlowIndicatorBinarySensor(device_info, device_id, dev_data),
            OnlineStatusBinarySensor(device_info, device_id, dev_data),
            ValveBinarySensor(device_info, device_id, dev_data),
            WebSocketConnectivityBinarySensor(device_info, device_id, dev_data),
        ]
        all_binary_sensors.extend(device_binary_sensors)
    
    async_add_entities(all_binary_sensors)

    # Register callback for WebSocket updates
    @callback
    def handle_ws_message(message: dict) -> None:
        """Handle WebSocket messages."""
        message_registry.handle_message(message, all_binary_sensors)

    config_entry.async_on_unload(data.async_add_ws_listener(handle_ws_message))

    # Register connectivity callbacks for WebSocket connectivity sensors
    websocket_sensors = [sensor for sensor in all_binary_sensors if isinstance(sensor, WebSocketConnectivityBinarySensor)]
    if websocket_sensors:
        @callback
        def handle_connectivity_update(connected: bool, phase: int) -> None:
            """Handle WebSocket connectivity status updates."""
            for sensor in websocket_sensors:
                sensor.update_connectivity_status(connected, phase)
        
        client.register_connectivity_callback(handle_connectivity_update)


class FlowIndicatorBinarySensor(LeakomaticBinarySensor):
    """Representation of a Leakomatic Flow Indicator binary sensor.
    
    This sensor indicates whether water is currently flowing (1) or not (0).
    It is updated through WebSocket updates.
    
    Note: There appears to be a bug in the API where flow_mode is always 1
    regardless of actual water flow. Therefore, the sensor ignores flow_mode
    in the initial data: it is unknown until the first WebSocket
    flow_updated event.
    
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
        # The API always sends flow_mode 1 in the initial data: leave it out,
        # so the state is unknown until a flow_updated event
        if device_data is not None:
            device_data = {k: v for k, v in device_data.items() if k != "flow_mode"}
            
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
        """Return true if flow is detected, None if unknown."""
        flow_mode = self._device_data.get("flow_mode")
        if flow_mode is None:
            return None
        try:
            return int(flow_mode) == 1
        except (ValueError, TypeError):
            log_with_entity(_LOGGER, logging.WARNING, self, "Invalid value: %s", flow_mode)
            return None

    @callback
    def handle_update(self, data: dict[str, Any]) -> None:
        """Handle updated data from WebSocket."""
        self._device_data = data
        self.async_write_ha_state()
        log_with_entity(_LOGGER, logging.DEBUG, self, "Value updated: %s", self.is_on)

class OnlineStatusBinarySensor(LeakomaticBinarySensor):
    """Representation of a Leakomatic Online Status binary sensor.
    
    This sensor indicates whether the device is currently online (True) or offline (False).
    It is updated through WebSocket updates with device_updated operation.
    
    The sensor will be set to online (True) when receiving any message from the device.
    It is set to offline (False) on a device_offline message, or when nothing
    has been heard from the device for DEVICE_OFFLINE_AFTER seconds while the
    connection to Leakomatic was up (the device reports every 5 minutes).

    The default state is unknown (None) until the first update is received.
    """

    async def async_added_to_hass(self) -> None:
        """Start checking for a silent device."""
        await super().async_added_to_hass()
        self.async_on_remove(
            async_track_time_interval(self.hass, self._async_check_silence, timedelta(minutes=1))
        )

    @callback
    def _async_check_silence(self, _now: datetime) -> None:
        """Turn off when the device has been silent too long."""
        if self.is_on is False or not self.available or self._availability is None:
            return
        # Count the silence only while messages could have arrived
        silent_since = self._availability.available_since
        if self._last_seen is not None and self._last_seen > silent_since:
            silent_since = self._last_seen
        if dt_util.utcnow() - silent_since < timedelta(seconds=DEVICE_OFFLINE_AFTER):
            return
        log_with_entity(
            _LOGGER, logging.INFO, self,
            "Nothing heard from the device for %d minutes, marking it offline",
            DEVICE_OFFLINE_AFTER // 60,
        )
        self._device_data = {"is_online": False}
        self.async_write_ha_state()

    def __init__(
        self,
        device_info: dict[str, Any],
        device_id: str,
        device_data: dict[str, Any] | None,
    ) -> None:
        """Initialize the online status binary sensor."""
        # is_online in the REST data does not reliably tell whether the device
        # is up right now (after a reload it said offline while the device was
        # up). The state is unknown until the first message from the device.
        if device_data is not None:
            device_data = {k: v for k, v in device_data.items() if k != "is_online"}
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
                log_with_entity(_LOGGER, logging.WARNING, self, "Failed to parse last_seen_at from device data: %s", err)

    @property
    def is_on(self) -> bool | None:
        """Return true if device is online, None if unknown."""
        is_online = self._device_data.get("is_online")
        if is_online is None:
            return None
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
                    log_with_entity(_LOGGER, logging.WARNING, self, "Failed to parse last_seen_at from device data: %s", err)
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
        self._previous_state: bool | None = None

    @property
    def is_on(self) -> bool | None:
        """Return true if valve is open, None if unknown."""
        # Get the port state value
        port_state = self._device_data.get("port_state")
        if port_state is not None:
            try:
                port_state_int = int(port_state)
                # Check if bit 7 is 0 (valve is open)
                is_open = (port_state_int & (1 << 7)) == 0
                
                # Only log if the state has changed
                if is_open != self._previous_state:
                    log_with_entity(_LOGGER, logging.DEBUG, self, "Valve updated from %s to %s", 
                                  "open" if self._previous_state else "closed" if self._previous_state is not None else "unknown",
                                  "open" if is_open else "closed")
                    self._previous_state = is_open
                
                return is_open
            except (ValueError, TypeError):
                log_with_entity(_LOGGER, logging.WARNING, self, "Invalid port state value: %s", port_state)
                return None

        return None

    @callback
    def handle_update(self, data: dict[str, Any]) -> None:
        """Handle updated data from WebSocket."""
        self._device_data = data
        self.async_write_ha_state()
        log_with_entity(_LOGGER, logging.DEBUG, self, "Value updated: %s", self.is_on)

class WebSocketConnectivityBinarySensor(LeakomaticBinarySensor):
    """Representation of a Leakomatic WebSocket Connectivity binary sensor.
    
    This sensor indicates whether the WebSocket connection to the Leakomatic API
    is currently active (True) or disconnected (False).
    
    The sensor is updated through direct calls from the client when the WebSocket
    connection status changes.
    
    This is a diagnostic sensor that helps users understand the connection status
    without having to check logs.
    """

    def __init__(
        self,
        device_info: dict[str, Any],
        device_id: str,
        device_data: dict[str, Any] | None,
    ) -> None:
        """Initialize the WebSocket connectivity binary sensor."""
        super().__init__(
            device_info=device_info,
            device_id=device_id,
            device_data=device_data,
            key="websocket_connectivity",
            icon="mdi:webhook",
            device_class=BinarySensorDeviceClass.CONNECTIVITY,
        )
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._websocket_connected = False
        self._reconnection_phase = 1
        self._last_connection_change: datetime | None = None

    @property
    def available(self) -> bool:
        """Always available: this sensor reports the connection itself."""
        return True

    @property
    def is_on(self) -> bool:
        """Return true if WebSocket is connected."""
        return self._websocket_connected

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        # Get base attributes from parent class
        attrs = super().extra_state_attributes or {}
        
        # Add our custom attributes
        attrs["reconnection_phase"] = self._reconnection_phase
        if self._last_connection_change:
            attrs["last_connection_change"] = self._last_connection_change.isoformat()
        
        return attrs

    @callback
    def update_connectivity_status(self, connected: bool, phase: int = 1) -> None:
        """Update the WebSocket connectivity status.
        
        Args:
            connected: Whether the WebSocket is currently connected
            phase: The current reconnection phase (1, 2, or 3)
        """
        if self._websocket_connected != connected or self._reconnection_phase != phase:
            self._websocket_connected = connected
            self._reconnection_phase = phase
            self._last_connection_change = datetime.now(timezone.utc).replace(microsecond=0)
            self.async_write_ha_state()
            
            status_text = "connected" if connected else "disconnected"
            log_with_entity(_LOGGER, logging.INFO, self, 
                           "WebSocket %s (Phase %d)", status_text, phase) 