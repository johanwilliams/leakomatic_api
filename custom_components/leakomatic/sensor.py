"""Support for Leakomatic sensors.

This module implements the sensor platform for the Leakomatic integration.
It provides sensors for:
- Device status and metrics
- Alarm conditions
- Quick test index
- Flow duration
- Total volume

The sensors are updated through real-time WebSocket updates.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.const import UnitOfVolume
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.typing import StateType

from .const import DeviceMode, MessageType, TestState, AlarmType, AlarmLevel
from .common import LeakomaticEntity, MessageHandlerRegistry, LeakomaticMessageHandler, log_with_entity
from .models import LeakomaticConfigEntry

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
        (PauseEndSensor, TotalVolumeSensor),  # the mode, total_flow_volume
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
        (FlowDurationSensor, TotalVolumeSensor),
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
        (SignalStrengthSensor, PauseEndSensor),  # PauseEndSensor: mode_stoptime
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

def handle_water_meter_calibration(message: dict, sensors: list[LeakomaticSensor]) -> None:
    """Handle water_meter_calibration_updated messages."""
    LeakomaticMessageHandler.update_matching_entities(message, sensors, TotalVolumeSensor, None)

def _as_int(value: Any) -> int | None:
    """The analog sensor fields can arrive as numbers or strings."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return None

def handle_analog_sensor_message(message: dict, sensors: list[LeakomaticSensor]) -> None:
    """Handle analog_sensor_message messages."""
    data = message.get("message", {}).get("data", {})
    sensor_type = _as_int(data.get("sensor_type"))
    connected = _as_int(data.get("connected"))
    value = data.get("value")

    # sensor_type 1 is pressure, 2 is temperature. A sensor that is not
    # connected has no reading: its value becomes unknown.
    target = {1: PressureSensor, 2: TemperatureSensor}.get(sensor_type)
    if target is not None:
        LeakomaticMessageHandler.update_matching_entities(
            message, sensors, target, None,
            update_data={"value": value if connected == 1 else None}
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
message_registry.register(MessageType.WATER_METER_CALIBRATION_UPDATED.value, handle_water_meter_calibration)
message_registry.register(MessageType.ANALOG_SENSOR_MESSAGE.value, handle_analog_sensor_message)
message_registry.register_default(handle_default)

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: LeakomaticConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Leakomatic sensor.
    
    This function:
    1. Gets the device information from the config entry
    2. Creates and adds the sensor entities for each device
    
    Args:
        hass: The Home Assistant instance
        config_entry: The config entry to set up sensors for
        async_add_entities: Callback to register new entities
    """
    _LOGGER.debug("Setting up Leakomatic sensor for config entry: %s", config_entry.entry_id)
    data = config_entry.runtime_data

    # Create sensors for each device
    all_sensors = []
    for device_id, device_info in data.device_infos.items():
        dev_data = data.device_data[device_id]

        # Create sensors for this device
        device_sensors = [
            QuickTestIndexSensor(device_info, device_id, dev_data),
            FlowDurationSensor(device_info, device_id, dev_data),
            SignalStrengthSensor(device_info, device_id, dev_data),
            LongestTightnessPeriodSensor(device_info, device_id, dev_data),
            FlowTestSensor(device_info, device_id, dev_data),
            QuickTestSensor(device_info, device_id, dev_data),
            TightnessTestSensor(device_info, device_id, dev_data),
            TotalVolumeSensor(device_info, device_id, dev_data),
            TemperatureSensor(device_info, device_id, dev_data),
            PressureSensor(device_info, device_id, dev_data),
            PauseEndSensor(device_info, device_id, dev_data),
        ]
        all_sensors.extend(device_sensors)
    
    async_add_entities(all_sensors)
    
    # Register callback for WebSocket updates
    @callback
    def handle_ws_message(message: dict) -> None:
        """Handle WebSocket messages."""
        message_registry.handle_message(message, all_sensors)

    config_entry.async_on_unload(data.async_add_ws_listener(handle_ws_message))


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
                log_with_entity(_LOGGER, logging.WARNING, self, "Invalid value: %s", value)
                return None
        
        return None

    @callback
    def handle_update(self, data: dict[str, Any]) -> None:
        """Handle updated data from WebSocket."""
        self._device_data = data
        self.async_write_ha_state()
        log_with_entity(_LOGGER, logging.DEBUG, self, "Value updated: %s", self.native_value)


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
                log_with_entity(_LOGGER, logging.WARNING, self, "Invalid value: %s", value)
                return self._last_known_duration
        
        return self._last_known_duration

    @callback
    def handle_update(self, data: dict[str, Any]) -> None:
        """Handle updated data from WebSocket."""
        self._device_data = data
        self.async_write_ha_state()
        log_with_entity(_LOGGER, logging.DEBUG, self, "Value updated: %s", self.native_value)


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
                log_with_entity(_LOGGER, logging.WARNING, self, "Invalid value: %s", rssi)
                return None
        
        return None

    @callback
    def handle_update(self, data: dict[str, Any]) -> None:
        """Handle updated data from WebSocket."""
        self._device_data = data
        self.async_write_ha_state()
        log_with_entity(_LOGGER, logging.DEBUG, self, "Value updated: %s", self.native_value)


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
                log_with_entity(_LOGGER, logging.WARNING, self, "Invalid value: %s", value)
                return None
        
        return None

    @callback
    def handle_update(self, data: dict[str, Any]) -> None:
        """Handle updated data from WebSocket."""
        self._device_data = data
        self.async_write_ha_state()
        log_with_entity(_LOGGER, logging.DEBUG, self, "Value updated: %s", self.native_value)


_ALARM_LEVEL_TO_STATE = {
    AlarmLevel.CLEAR.value: TestState.CLEAR.value,
    AlarmLevel.WARNING.value: TestState.WARNING.value,
    AlarmLevel.ALARM.value: TestState.ALARM.value,
}


class AlarmTestSensor(LeakomaticEntity, SensorEntity):
    """Base class for Leakomatic alarm test sensors.
    
    This sensor monitors test status and changes state based on alarm levels:
    - CLEAR: No alarm
    - WARNING: Warning threshold exceeded
    - ALARM: Alarm threshold exceeded

    An alarm level outside these makes the state unknown.
    """

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = [state.value for state in TestState]

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
        self._state: str | None = TestState.CLEAR.value
        self._alarm_type = alarm_type
        self._log_prefix = log_prefix
        
        # Check for current alarm in device data
        if device_data and "current_alarm" in device_data:
            current_alarm = device_data["current_alarm"]
            if current_alarm and current_alarm.get("alarm_type") == int(self._alarm_type):
                self._state = self._state_for_level(current_alarm.get("level", AlarmLevel.CLEAR.value))

    def _state_for_level(self, alarm_level: Any) -> str | None:
        """Return the state for an alarm level, or None (unknown) for an unknown level."""
        state = _ALARM_LEVEL_TO_STATE.get(str(alarm_level))
        if state is None:
            log_with_entity(_LOGGER, logging.WARNING, self, "Unknown alarm level received: %s", alarm_level)
        return state

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
                self._state = self._state_for_level(data.get("alarm_level", ""))
                self._device_data = data
                self.async_write_ha_state()
                # Add state change log message
                log_with_entity(_LOGGER, logging.DEBUG, self, "Value updated: %s", self.native_value)


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
            alarm_type=AlarmType.FLOW_TEST.value,
            log_prefix="FlowTestSensor",
        )
        self._attr_translation_key = "flow_test"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes for flow test thresholds and delays if available."""
        attrs = super().extra_state_attributes or {}
        configurations = self._device_data.get("configurations") if self._device_data else None
        duration_away = None
        duration_home = None
        alarm_delay = None
        if configurations and isinstance(configurations, list):
            latest_config = max(
                configurations,
                key=lambda c: (c.get("time") or "", c.get("id") or 0),
                default=None
            )
            if latest_config:
                if "ft_alarm_away" in latest_config:
                    duration_away = latest_config["ft_alarm_away"]
                if "ft_warning_home" in latest_config:
                    duration_home = latest_config["ft_warning_home"]
                if "ft_alarm_delay" in latest_config:
                    alarm_delay = latest_config["ft_alarm_delay"]
        if duration_away is not None:
            attrs["duration_away"] = duration_away
        if duration_home is not None:
            attrs["duration_home"] = duration_home
        if alarm_delay is not None:
            attrs["alarm_delay"] = alarm_delay
        return attrs


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
            alarm_type=AlarmType.QUICK_TEST.value,
            log_prefix="QuickTestSensor",
        )
        self._attr_translation_key = "quick_test"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes, including alarm delay and index limit if available."""
        attrs = super().extra_state_attributes or {}
        configurations = self._device_data.get("configurations") if self._device_data else None
        alarm_delay = None
        index_limit = None
        if configurations and isinstance(configurations, list):
            # Find the configuration with the latest 'time' (ISO8601 string)
            latest_config = max(
                configurations,
                key=lambda c: (c.get("time") or "", c.get("id") or 0),
                default=None
            )
            if latest_config:
                if "qt_alarm_delay" in latest_config:
                    alarm_delay = latest_config["qt_alarm_delay"]
                if "qt_index_limit" in latest_config:
                    index_limit = latest_config["qt_index_limit"]
        if alarm_delay is not None:
            attrs["alarm_delay"] = alarm_delay
        if index_limit is not None:
            attrs["index_limit"] = index_limit
        return attrs


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
            alarm_type=AlarmType.TIGHTNESS_TEST.value,
            log_prefix="TightnessTestSensor",
        )
        self._attr_translation_key = "tightness_test"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes for tightness test configuration if available."""
        attrs = super().extra_state_attributes or {}
        configurations = self._device_data.get("configurations") if self._device_data else None
        pulse_free_periods = None
        period_duration = None
        alarm_delay = None
        if configurations and isinstance(configurations, list):
            latest_config = max(
                configurations,
                key=lambda c: (c.get("time") or "", c.get("id") or 0),
                default=None
            )
            if latest_config:
                if "tt_count" in latest_config:
                    pulse_free_periods = latest_config["tt_count"]
                if "tt_length" in latest_config:
                    period_duration = latest_config["tt_length"]
                if "tt_alarm_delay" in latest_config:
                    alarm_delay = latest_config["tt_alarm_delay"]
        if pulse_free_periods is not None:
            attrs["pulse_free_periods"] = pulse_free_periods
        if period_duration is not None:
            attrs["period_duration"] = period_duration
        if alarm_delay is not None:
            attrs["alarm_delay"] = alarm_delay
        return attrs


class TotalVolumeSensor(LeakomaticSensor):
    """Representation of a Leakomatic Total Volume sensor.

    The reading of a water meter connected to the device (pulse input), in m³.
    Leakomatic sends it in two forms:
    - total_flow_volume (startup data, device_updated): already in m³
    - total_volume (flow_updated, water_meter_calibration_updated): in litres
    Devices without a water meter report 0. Disabled by default.
    """

    def __init__(
        self,
        device_info: dict[str, Any],
        device_id: str,
        device_data: dict[str, Any] | None,
    ) -> None:
        """Initialize the total volume sensor."""
        super().__init__(
            device_info=device_info,
            device_id=device_id,
            device_data=device_data,
            key="total_volume",
            icon="mdi:counter",
            device_class=SensorDeviceClass.WATER,
            state_class=SensorStateClass.TOTAL_INCREASING,
            native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
        )
        self._attr_entity_registry_enabled_default = False
        self._volume: float | None = None
        if device_data and device_data.get("total_flow_volume") is not None:
            self._volume = self._parse(device_data["total_flow_volume"], 1)

    @property
    def native_value(self) -> StateType:
        """Return the meter reading in m³."""
        return self._volume

    def _parse(self, raw: Any, divisor: float) -> float | None:
        try:
            return round(float(raw) / divisor, 3)
        except (ValueError, TypeError) as err:
            log_with_entity(_LOGGER, logging.WARNING, self, "Error updating total volume: %s", err)
            return None

    @callback
    def handle_update(self, data: dict[str, Any]) -> None:
        """Take total_volume (litres) or total_flow_volume (m³) from a message."""
        if data.get("total_volume") is not None:
            volume = self._parse(data["total_volume"], 1000)
        elif data.get("total_flow_volume") is not None:
            volume = self._parse(data["total_flow_volume"], 1)
        else:
            return
        if volume is None:
            return  # invalid value: logged, keep the last reading
        self._volume = volume
        self.async_write_ha_state()


class TemperatureSensor(LeakomaticSensor):
    """Representation of a Leakomatic Temperature sensor.
    
    This sensor represents the temperature reading from the Leakomatic device.
    It is updated through WebSocket updates with analog_sensor_message operation.
    The temperature is measured in Celsius (°C).
    """

    def __init__(
        self,
        device_info: dict[str, Any],
        device_id: str,
        device_data: dict[str, Any] | None,
    ) -> None:
        """Initialize the temperature sensor."""
        super().__init__(
            device_info=device_info,
            device_id=device_id,
            device_data=device_data,
            key="temperature",
            icon="mdi:thermometer-water",
            device_class=SensorDeviceClass.TEMPERATURE,
            state_class=SensorStateClass.MEASUREMENT,
            native_unit_of_measurement="°C"
        )
        self._attr_entity_registry_enabled_default = False

    @property
    def native_value(self) -> StateType:
        """Return the state of the sensor."""
        if not self._device_data:
            return None
        
        # Get the temperature value - try both possible field names
        value = self._device_data.get("value")
        if value is None:
            value = self._device_data.get("last_temperature_value")
        
        if value is not None:
            try:
                # Round to 1 decimal place
                return round(float(value), 1)
            except (ValueError, TypeError):
                return None
        
        return None

    @callback
    def handle_update(self, data: dict[str, Any]) -> None:
        """Handle updated data from WebSocket."""
        self._device_data = data
        self.async_write_ha_state()
        log_with_entity(_LOGGER, logging.DEBUG, self, "Value updated: %s", self.native_value)


class PressureSensor(LeakomaticSensor):
    """Representation of a Leakomatic Pressure sensor.
    
    This sensor represents the pressure reading from the Leakomatic device.
    It is updated through WebSocket updates with analog_sensor_message operation.
    The pressure is measured in bar.
    """

    def __init__(
        self,
        device_info: dict[str, Any],
        device_id: str,
        device_data: dict[str, Any] | None,
    ) -> None:
        """Initialize the pressure sensor."""
        super().__init__(
            device_info=device_info,
            device_id=device_id,
            device_data=device_data,
            key="pressure",
            icon="mdi:gauge",
            device_class=SensorDeviceClass.PRESSURE,
            state_class=SensorStateClass.MEASUREMENT,
            native_unit_of_measurement="bar"
        )
        self._attr_entity_registry_enabled_default = False

    @property
    def native_value(self) -> StateType:
        """Return the state of the sensor."""
        if not self._device_data:
            return None
        
        # Get the pressure value - try both possible field names
        value = self._device_data.get("value")
        if value is None:
            value = self._device_data.get("last_pressure_value")
        
        if value is not None:
            try:
                # Round to 1 decimal place
                return round(float(value), 1)
            except (ValueError, TypeError):
                return None
        
        return None

    @callback
    def handle_update(self, data: dict[str, Any]) -> None:
        """Handle updated data from WebSocket."""
        self._device_data = data
        self.async_write_ha_state()
        log_with_entity(_LOGGER, logging.DEBUG, self, "Value updated: %s", self.native_value)


class PauseEndSensor(LeakomaticSensor):
    """When the pause mode ends.

    In pause mode the device returns to its previous mode after a configured
    time. mode_stoptime is that moment as a Unix timestamp (0 when there is
    no pause). It comes in status_message and the startup data, the mode in
    device_updated and the startup data, so both are kept here.
    """

    def __init__(
        self,
        device_info: dict[str, Any],
        device_id: str,
        device_data: dict[str, Any] | None,
    ) -> None:
        """Initialize the pause end sensor."""
        super().__init__(
            device_info=device_info,
            device_id=device_id,
            device_data=device_data,
            key="pause_end",
            icon="mdi:timer-pause-outline",
            device_class=SensorDeviceClass.TIMESTAMP,
        )
        data = device_data or {}
        self._mode = data.get("mode")
        self._stoptime = data.get("mode_stoptime")

    @property
    def native_value(self) -> datetime | None:
        """Return when the pause ends, or None when the device is not paused."""
        try:
            mode = int(self._mode)
            stoptime = int(self._stoptime)
        except (TypeError, ValueError):
            return None
        if mode != DeviceMode.PAUSE.value or stoptime <= 0:
            return None
        return datetime.fromtimestamp(stoptime, tz=timezone.utc)

    @callback
    def handle_update(self, data: dict[str, Any]) -> None:
        """Take the mode (device_updated) or the stop time (status_message)."""
        if "mode" in data:
            self._mode = data["mode"]
        if "mode_stoptime" in data:
            self._stoptime = data["mode_stoptime"]
        self.async_write_ha_state()
        log_with_entity(_LOGGER, logging.DEBUG, self, "Value updated: %s", self.native_value)
