"""Support for Leakomatic sensors.

This module implements the sensor platform for the Leakomatic integration.
It provides sensors for:
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
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.typing import StateType

from .const import DOMAIN, MessageType, TestState
from .common import LeakomaticEntity, MessageHandlerRegistry, LeakomaticMessageHandler

_LOGGER = logging.getLogger(__name__)

class LeakomaticSensor(LeakomaticEntity, SensorEntity):
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
        super().__init__(
            device_info=device_info,
            device_id=device_id,
            device_data=device_data,
            key=key,
            icon=icon,
        )
        self._attr_device_class = device_class
        self._attr_native_unit_of_measurement = native_unit_of_measurement
        self._attr_state_class = state_class

# Create a global registry instance
message_registry = MessageHandlerRegistry[LeakomaticSensor]()

# Define message handlers
def handle_device_update(message: dict, sensors: list[LeakomaticSensor]) -> None:
    """Handle device_updated messages."""
    LeakomaticMessageHandler.handle_device_update(
        message, 
        sensors, 
        None,  # No flow sensor
        None   # No online sensor
    )

def handle_quick_test_update(message: dict, sensors: list[LeakomaticSensor]) -> None:
    """Handle quick_test_updated messages."""
    LeakomaticMessageHandler.handle_quick_test_update(
        message, 
        sensors, 
        QuickTestIndexSensor,
        None   # No online sensor
    )

def handle_flow_update(message: dict, sensors: list[LeakomaticSensor]) -> None:
    """Handle flow_updated messages."""
    LeakomaticMessageHandler.handle_flow_update(
        message, 
        sensors, 
        FlowDurationSensor,
        None   # No online sensor
    )

def handle_tightness_test_update(message: dict, sensors: list[LeakomaticSensor]) -> None:
    """Handle tightness_test_updated messages."""
    LeakomaticMessageHandler.handle_tightness_test_update(
        message, 
        sensors, 
        LongestTightnessPeriodSensor,
        None   # No online sensor
    )

def handle_status_update(message: dict, sensors: list[LeakomaticSensor]) -> None:
    """Handle status_message messages."""
    LeakomaticMessageHandler.handle_status_update(
        message, 
        sensors, 
        SignalStrengthSensor,
        None   # No online sensor
    )

def handle_alarm_triggered(message: dict, sensors: list[LeakomaticSensor]) -> None:
    """Handle alarm_triggered messages."""
    LeakomaticMessageHandler.handle_alarm_triggered(
        message, 
        sensors, 
        (FlowTestSensor, QuickTestSensor, TightnessTestSensor),
        None   # No online sensor
    )

def handle_default(message: dict, sensors: list[LeakomaticSensor]) -> None:
    """Handle any other message type."""
    LeakomaticMessageHandler.handle_default(message, sensors)

# Register all handlers
message_registry.register(MessageType.DEVICE_UPDATED.value, handle_device_update)
message_registry.register(MessageType.QUICK_TEST_UPDATED.value, handle_quick_test_update)
message_registry.register(MessageType.FLOW_UPDATED.value, handle_flow_update)
message_registry.register(MessageType.TIGHTNESS_TEST_UPDATED.value, handle_tightness_test_update)
message_registry.register(MessageType.STATUS_MESSAGE.value, handle_status_update)
message_registry.register(MessageType.ALARM_TRIGGERED.value, handle_alarm_triggered)
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
        QuickTestIndexSensor(device_info, device_id, device_data),
        FlowDurationSensor(device_info, device_id, device_data),
        SignalStrengthSensor(device_info, device_id, device_data),
        LongestTightnessPeriodSensor(device_info, device_id, device_data),
        FlowTestSensor(device_info, device_id, device_data),
        QuickTestSensor(device_info, device_id, device_data),
        TightnessTestSensor(device_info, device_id, device_data),
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


class QuickTestIndexSensor(LeakomaticSensor):
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
            key="quick_test_index",
            icon="mdi:water",
            state_class=SensorStateClass.MEASUREMENT,
        )

    @property
    def native_value(self) -> StateType:
        """Return the state of the sensor."""
        if not self._device_data:
            return None
        
        # Get the quick test value - try both possible field names
        value = self._device_data.get("value")
        if value is None:
            value = self._device_data.get("current_quick_test")
        
        if value is not None:
            try:
                return round(float(value), 2)  # Round to 2 decimal places
            except (ValueError, TypeError):
                _LOGGER.warning("Invalid quick test value: %s", value)
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
        self._last_known_duration: int | None = None

    @property
    def native_value(self) -> StateType:
        """Return the state of the sensor."""
        if not self._device_data:
            return self._last_known_duration
        
        # Get the flow duration value - try both possible field names
        value = self._device_data.get("flow_duration")
        if value is None:
            value = self._device_data.get("current_flow_duration")
        
        if value is not None:
            try:
                # Ensure the value is an integer number of seconds
                duration = int(float(value))
                if duration > 0:
                    self._last_known_duration = duration
                return self._last_known_duration
            except (ValueError, TypeError):
                _LOGGER.warning("Invalid flow duration value: %s", value)
                return self._last_known_duration
        
        return self._last_known_duration

    @callback
    def handle_update(self, data: dict[str, Any]) -> None:
        """Handle updated data from WebSocket."""
        self._device_data = data
        self.async_write_ha_state()
        _LOGGER.debug("%s value updated: %s", self.name, self.native_value)


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
            return None
        
        # Get the RSSI value
        rssi = self._device_data.get("rssi")
        if rssi is not None:
            try:
                return int(rssi)  # RSSI should be an integer
            except (ValueError, TypeError):
                _LOGGER.warning("Invalid RSSI value: %s", rssi)
                return None
        
        return None

    @callback
    def handle_update(self, data: dict[str, Any]) -> None:
        """Handle updated data from WebSocket."""
        self._device_data = data
        self.async_write_ha_state()
        _LOGGER.debug("%s value updated: %s", self.name, self.native_value)


class LongestTightnessPeriodSensor(LeakomaticSensor):
    """Representation of a Leakomatic Longest Tightness Period sensor.
    
    This sensor represents the longest tightness period of the Leakomatic device.
    It is updated through WebSocket updates.
    The value is in seconds.
    """

    def __init__(
        self,
        device_info: dict[str, Any],
        device_id: str,
        device_data: dict[str, Any] | None,
    ) -> None:
        """Initialize the longest tightness period sensor."""
        super().__init__(
            device_info=device_info,
            device_id=device_id,
            device_data=device_data,
            key="longest_tightness_period",
            icon="mdi:water",
            device_class=SensorDeviceClass.DURATION,
            state_class=SensorStateClass.MEASUREMENT,
            native_unit_of_measurement="s"
        )

    @property
    def native_value(self) -> StateType:
        """Return the state of the sensor."""
        if not self._device_data:
            return None
        
        # Get the tightness period value - try both possible field names
        value = self._device_data.get("value")
        if value is None:
            value = self._device_data.get("current_tightness_test")
        
        if value is not None:
            try:
                # Convert to integer since we're dealing with seconds
                return int(float(value))
            except (ValueError, TypeError):
                _LOGGER.warning("Invalid tightness period value: %s", value)
                return None
        
        return None


class AlarmTestSensor(LeakomaticSensor):
    """Base class for Leakomatic alarm test sensors.
    
    This sensor monitors test status and changes state based on alarm levels:
    - CLEAR: No alarm
    - WARNING: Warning threshold exceeded
    - ALARM: Alarm threshold exceeded
    """

    def __init__(
        self,
        device_info: dict[str, Any],
        device_id: str,
        device_data: dict[str, Any] | None,
        *,
        key: str,
        alarm_type: str,
        log_prefix: str,
    ) -> None:
        """Initialize the alarm test sensor."""
        super().__init__(
            device_info=device_info,
            device_id=device_id,
            device_data=device_data,
            key=key,
            icon="mdi:water-alert",
        )
        self._state = TestState.CLEAR.value
        self._alarm_type = alarm_type
        self._log_prefix = log_prefix
        
        # Check for current alarm in device data
        if device_data and "current_alarm" in device_data:
            current_alarm = device_data["current_alarm"]
            if current_alarm and current_alarm.get("alarm_type") == int(self._alarm_type):
                alarm_level = str(current_alarm.get("level", "0"))
                _LOGGER.debug("%s found current alarm with level %s", self._log_prefix, alarm_level)
                if alarm_level == "1":
                    self._state = TestState.WARNING.value
                elif alarm_level == "2":
                    self._state = TestState.ALARM.value
                elif alarm_level == "0":
                    self._state = TestState.CLEAR.value
                else:
                    _LOGGER.warning("%s unknown alarm level received: %s", self._log_prefix, alarm_level)

    @property
    def native_value(self) -> StateType:
        """Return the state of the sensor."""
        return self._state

    @callback
    def handle_update(self, data: dict[str, Any]) -> None:
        """Handle updated data from WebSocket."""
        # Check if this is an alarm message
        if data.get("operation") == "alarm_triggered":
            # Verify this is the correct alarm type
            if data.get("alarm_type") == self._alarm_type:
                alarm_level = data.get("alarm_level")
                if alarm_level == "1":
                    self._state = TestState.WARNING.value
                elif alarm_level == "2":
                    self._state = TestState.ALARM.value
                elif alarm_level == "0":
                    self._state = TestState.CLEAR.value
                else:
                    _LOGGER.warning("Unknown alarm level received: %s", alarm_level)
                self._device_data = data
                self.async_write_ha_state()


class FlowTestSensor(AlarmTestSensor):
    """Representation of a Leakomatic Flow Test sensor.
    
    This sensor monitors the flow duration and changes state based on configured thresholds:
    - CLEAR: No flow or flow duration below warning threshold
    - WARNING: Flow duration exceeds warning threshold
    - ALARM: Flow duration exceeds alarm threshold
    """

    def __init__(
        self,
        device_info: dict[str, Any],
        device_id: str,
        device_data: dict[str, Any] | None,
    ) -> None:
        """Initialize the flow test sensor."""
        super().__init__(
            device_info=device_info,
            device_id=device_id,
            device_data=device_data,
            key="flow_test",
            alarm_type="0",
            log_prefix="FlowTestSensor",
        )


class QuickTestSensor(AlarmTestSensor):
    """Representation of a Leakomatic Quick Test sensor.
    
    This sensor monitors the quick test status and changes state based on alarm levels:
    - CLEAR: No alarm
    - WARNING: Quick test warning threshold exceeded
    - ALARM: Quick test alarm threshold exceeded
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
            alarm_type="1",
            log_prefix="QuickTestSensor",
        )


class TightnessTestSensor(AlarmTestSensor):
    """Representation of a Leakomatic Tightness Test sensor.
    
    This sensor monitors the tightness test status and changes state based on alarm levels:
    - CLEAR: No alarm
    - WARNING: Tightness test warning threshold exceeded
    - ALARM: Tightness test alarm threshold exceeded
    """

    def __init__(
        self,
        device_info: dict[str, Any],
        device_id: str,
        device_data: dict[str, Any] | None,
    ) -> None:
        """Initialize the tightness test sensor."""
        super().__init__(
            device_info=device_info,
            device_id=device_id,
            device_data=device_data,
            key="tightness_test",
            alarm_type="2",
            log_prefix="TightnessTestSensor",
        )