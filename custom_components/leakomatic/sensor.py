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
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from homeassistant.components.sensor import (
    SensorEntity,
    SensorEntityDescription,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.const import (
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    EntityCategory,
    UnitOfPressure,
    UnitOfTemperature,
    UnitOfTime,
    UnitOfVolume,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
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
        # Only what is given: an _attr_ set to None would override an entity description
        if device_class is not None:
            self._attr_device_class = device_class
        if native_unit_of_measurement is not None:
            self._attr_native_unit_of_measurement = native_unit_of_measurement
        if state_class is not None:
            self._attr_state_class = state_class

# Create a global registry instance
message_registry = MessageHandlerRegistry[LeakomaticSensor]()


def _value_sensors(sensors: list[LeakomaticSensor], operation: str) -> list[LeakomaticSensor]:
    """The value sensors that take their value from this message type."""
    return [
        sensor for sensor in sensors
        if isinstance(sensor, LeakomaticValueSensor) and operation in sensor.entity_description.updated_by
    ]


def _update(message: dict, sensors: list[LeakomaticSensor], operation: str, *special: type) -> None:
    """Update the value sensors for this message type and the given special sensor classes."""
    targets = _value_sensors(sensors, operation) + [s for s in sensors if isinstance(s, special)]
    LeakomaticMessageHandler.update_matching_entities(
        message, targets, (LeakomaticValueSensor, *special), None
    )


def handle_device_update(message: dict, sensors: list[LeakomaticSensor]) -> None:
    """device_updated: the mode, total_flow_volume and active_alarms."""
    _update(message, sensors, MessageType.DEVICE_UPDATED.value, PauseEndSensor, TotalVolumeSensor, *ALARM_SENSORS)


def handle_quick_test_update(message: dict, sensors: list[LeakomaticSensor]) -> None:
    """quick_test_updated."""
    _update(message, sensors, MessageType.QUICK_TEST_UPDATED.value)


def handle_flow_update(message: dict, sensors: list[LeakomaticSensor]) -> None:
    """flow_updated: the flow duration, and the water meter reading on models with one."""
    _update(message, sensors, MessageType.FLOW_UPDATED.value, TotalVolumeSensor)


def handle_tightness_test_update(message: dict, sensors: list[LeakomaticSensor]) -> None:
    """tightness_test_updated."""
    _update(message, sensors, MessageType.TIGHTNESS_TEST_UPDATED.value)


def handle_status_update(message: dict, sensors: list[LeakomaticSensor]) -> None:
    """status_message: the signal strength, and mode_stoptime for Pause Ends."""
    _update(message, sensors, MessageType.STATUS_MESSAGE.value, PauseEndSensor)


def handle_alarm_triggered(message: dict, sensors: list[LeakomaticSensor]) -> None:
    """alarm_triggered."""
    _update(message, sensors, MessageType.ALARM_TRIGGERED.value, *ALARM_SENSORS)


def handle_water_meter_calibration(message: dict, sensors: list[LeakomaticSensor]) -> None:
    """water_meter_calibration_updated."""
    _update(message, sensors, MessageType.WATER_METER_CALIBRATION_UPDATED.value, TotalVolumeSensor)


def _as_int(value: Any) -> int | None:
    """The analog sensor fields can arrive as numbers or strings."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def handle_analog_sensor_message(message: dict, sensors: list[LeakomaticSensor]) -> None:
    """analog_sensor_message: a reading from the sensor on the analog input."""
    data = message.get("message", {}).get("data", {})
    sensor_type = _as_int(data.get("sensor_type"))
    connected = _as_int(data.get("connected"))
    targets = [
        sensor for sensor in sensors
        if isinstance(sensor, LeakomaticValueSensor) and sensor.entity_description.analog_type == sensor_type
    ]
    # A sensor that is not connected has no reading: its value becomes unknown.
    if targets:
        LeakomaticMessageHandler.update_matching_entities(
            message, targets, LeakomaticValueSensor, None,
            update_data={"value": data.get("value") if connected == 1 else None},
        )


def handle_configuration_added(message: dict, sensors: list[LeakomaticSensor]) -> None:
    """A new device configuration: the alarm test sensors show its settings."""
    _update(message, sensors, MessageType.CONFIGURATION_ADDED.value, *ALARM_SENSORS)


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
message_registry.register(MessageType.CONFIGURATION_ADDED.value, handle_configuration_added)
message_registry.register_default(handle_default)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: LeakomaticConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Leakomatic sensors: for each device, the value sensors and the special ones."""
    _LOGGER.debug("Setting up Leakomatic sensor for config entry: %s", config_entry.entry_id)
    data = config_entry.runtime_data

    all_sensors: list[LeakomaticSensor] = []
    for device_id, device_info in data.device_infos.items():
        dev_data = data.device_data[device_id]
        all_sensors.extend(
            LeakomaticValueSensor(device_info, device_id, dev_data, description)
            for description in VALUE_SENSORS
        )
        all_sensors.extend(
            sensor_class(device_info, device_id, dev_data)
            for sensor_class in (FlowTestSensor, QuickTestSensor, TightnessTestSensor, TotalVolumeSensor, PauseEndSensor)
        )

    async_add_entities(all_sensors)

    @callback
    def handle_ws_message(message: dict) -> None:
        """Handle WebSocket messages."""
        message_registry.handle_message(message, all_sensors)

    config_entry.async_on_unload(data.async_add_ws_listener(handle_ws_message))


def _round(digits: int) -> Callable[[Any], StateType]:
    return lambda value: round(float(value), digits)


def _whole_seconds(value: Any) -> int:
    return int(float(value))


# What Leakomatic sends when there is no reading (for example "-" as the
# temperature of a device without a temperature sensor): unknown, not invalid
NO_READING = ("-", "")


@dataclass(frozen=True, kw_only=True)
class LeakomaticSensorEntityDescription(SensorEntityDescription):
    """A sensor whose value is one field, converted.

    fields: the field names to read, in order (the websocket message's name
        first, then the startup data's).
    convert: turns the raw value into the state; raising ValueError or
        TypeError makes it invalid (logged, unknown).
    updated_by: the message types that carry the value.
    analog_type: for analog_sensor_message, the sensor_type this sensor shows.
    keep_last_positive: keep the last value above zero (a flow that has just
        started reports 0; the last completed flow is what the sensor shows).
    """

    fields: tuple[str, ...]
    convert: Callable[[Any], StateType]
    updated_by: frozenset[str] = frozenset()
    analog_type: int | None = None
    keep_last_positive: bool = False


VALUE_SENSORS: tuple[LeakomaticSensorEntityDescription, ...] = (
    LeakomaticSensorEntityDescription(
        key="quick_test_index",
        icon="mdi:water",
        state_class=SensorStateClass.MEASUREMENT,
        fields=("value", "current_quick_test"),
        convert=_round(2),
        updated_by=frozenset({MessageType.QUICK_TEST_UPDATED.value}),
    ),
    LeakomaticSensorEntityDescription(
        key="flow_duration",
        icon="mdi:clock-outline",
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        fields=("flow_duration", "current_flow_duration"),
        convert=_whole_seconds,
        updated_by=frozenset({MessageType.FLOW_UPDATED.value}),
        keep_last_positive=True,
    ),
    LeakomaticSensorEntityDescription(
        key="signal_strength",
        icon="mdi:wifi",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        entity_category=EntityCategory.DIAGNOSTIC,
        fields=("rssi",),
        convert=int,
        updated_by=frozenset({MessageType.STATUS_MESSAGE.value}),
    ),
    LeakomaticSensorEntityDescription(
        key="longest_tightness_period",
        icon="mdi:water",
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        fields=("value", "current_tightness_test"),
        convert=_whole_seconds,
        updated_by=frozenset({MessageType.TIGHTNESS_TEST_UPDATED.value}),
    ),
    LeakomaticSensorEntityDescription(
        key="temperature",
        icon="mdi:thermometer-water",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        entity_registry_enabled_default=False,
        fields=("value", "last_temperature_value"),
        convert=_round(1),
        analog_type=2,
    ),
    LeakomaticSensorEntityDescription(
        key="pressure",
        icon="mdi:gauge",
        device_class=SensorDeviceClass.PRESSURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPressure.BAR,
        entity_registry_enabled_default=False,
        fields=("value", "last_pressure_value"),
        convert=_round(1),
        analog_type=1,
    ),
)


class LeakomaticValueSensor(LeakomaticSensor):
    """A sensor described by a LeakomaticSensorEntityDescription."""

    entity_description: LeakomaticSensorEntityDescription

    def __init__(
        self,
        device_info: dict[str, Any],
        device_id: str,
        device_data: dict[str, Any] | None,
        description: LeakomaticSensorEntityDescription,
    ) -> None:
        """Initialize the sensor from its description and the startup data."""
        super().__init__(
            device_info=device_info,
            device_id=device_id,
            device_data=device_data,
            key=description.key,
            icon=description.icon,
        )
        self.entity_description = description
        self._attr_entity_registry_enabled_default = description.entity_registry_enabled_default
        self._value: StateType = None
        self._value = self._read(device_data or {})

    def _read(self, data: dict[str, Any]) -> StateType:
        """The converted value of the first field that is present."""
        description = self.entity_description
        raw = next((data[field] for field in description.fields if data.get(field) is not None), None)
        if raw in NO_READING:
            raw = None
        if raw is None:
            return self._value if description.keep_last_positive else None
        try:
            value = description.convert(raw)
        except (ValueError, TypeError):
            log_with_entity(_LOGGER, logging.WARNING, self, "Invalid value: %s", raw)
            return self._value if description.keep_last_positive else None
        if description.keep_last_positive and not value > 0:
            return self._value
        return value

    @property
    def native_value(self) -> StateType:
        """Return the state of the sensor."""
        return self._value

    @callback
    def handle_update(self, data: dict[str, Any]) -> None:
        """Take the value from a websocket message."""
        self._value = self._read(data)
        self.async_write_ha_state()
        log_with_entity(_LOGGER, logging.DEBUG, self, "Value updated: %s", self.native_value)


# configuration_added sends the durations in seconds; the configurations in
# the device data (and Leakomatic's app) use these units. Divisor per field.
_CONFIGURATION_MESSAGE_DIVISORS = {
    "ft_warning_home": 60,  # minutes
    "ft_alarm_delay": 60,  # minutes
    "qt_alarm_delay": 3600,  # hours
    "tt_length": 60,  # minutes
    "tt_alarm_delay": 86400,  # days
}


def configuration_from_message(data: dict[str, Any]) -> dict[str, Any]:
    """A configuration from configuration_added, in the units of the device data.

    The index limit arrives as a 32-bit float (0.7 as 0.699999988079071) and is
    rounded; the app sets it with one decimal.
    """
    configuration = dict(data)
    for field, divisor in _CONFIGURATION_MESSAGE_DIVISORS.items():
        value = configuration.get(field)
        if isinstance(value, (int, float)):
            converted = value / divisor
            configuration[field] = int(converted) if converted == int(converted) else round(converted, 2)
    if isinstance(configuration.get("qt_index_limit"), float):
        configuration["qt_index_limit"] = round(configuration["qt_index_limit"], 2)
    return configuration


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

    The state comes from the list of active alarms (startup data and every
    device_updated) and from alarm_triggered. The test's settings, shown as
    attributes, come from the latest configuration (startup data and
    configuration_added) and are kept separately from the alarm data.
    """

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = [state.value for state in TestState]
    # Attribute name -> field in the device configuration
    _config_attributes: dict[str, str] = {}

    def __init__(
        self,
        device_info: dict[str, Any],
        device_id: str,
        device_data: dict[str, Any] | None,
        *,
        key: str,
        alarm_type: str,
    ) -> None:
        """Initialize the alarm test sensor."""
        super().__init__(
            device_info=device_info,
            device_id=device_id,
            device_data=device_data,
            key=key,
            icon="mdi:water-alert",
        )
        self._alarm_type = alarm_type
        data = device_data or {}
        self._state: str | None = TestState.CLEAR.value
        if isinstance(data.get("active_alarms"), list):
            self._state = self._state_from_active_alarms(data["active_alarms"])
        elif data.get("current_alarm"):
            current_alarm = data["current_alarm"]
            if str(current_alarm.get("alarm_type")) == self._alarm_type:
                self._state = self._state_for_level(current_alarm.get("level", AlarmLevel.CLEAR.value))

        configurations = data.get("configurations")
        self._configuration: dict[str, Any] = {}
        if isinstance(configurations, list) and configurations:
            self._configuration = max(
                configurations, key=lambda c: (c.get("time") or "", c.get("id") or 0)
            )

    def _state_for_level(self, alarm_level: Any) -> str | None:
        """Return the state for an alarm level, or None (unknown) for an unknown level."""
        state = _ALARM_LEVEL_TO_STATE.get(str(alarm_level))
        if state is None:
            log_with_entity(_LOGGER, logging.WARNING, self, "Unknown alarm level received: %s", alarm_level)
        return state

    def _state_from_active_alarms(self, active_alarms: list[dict[str, Any]]) -> str | None:
        """The state from the active alarms: the highest level of this test's alarms, or clear."""
        levels = [
            alarm.get("level")
            for alarm in active_alarms
            if str(alarm.get("alarm_type")) == self._alarm_type and alarm.get("is_active", True)
        ]
        if not levels:
            return TestState.CLEAR.value
        states = [self._state_for_level(level) for level in levels]
        if None in states:
            return None  # an unknown level: the guard does not know
        order = [TestState.CLEAR.value, TestState.WARNING.value, TestState.ALARM.value]
        return max(states, key=order.index)

    @property
    def native_value(self) -> StateType:
        """Return the state of the sensor."""
        return self._state

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """The test's settings from the latest device configuration."""
        return {
            name: self._configuration[field]
            for name, field in self._config_attributes.items()
            if self._configuration.get(field) is not None
        }

    @callback
    def handle_update(self, data: dict[str, Any]) -> None:
        """Handle alarm_triggered, device_updated and configuration_added."""
        operation = data.get("operation")
        if operation == MessageType.ALARM_TRIGGERED.value:
            if str(data.get("alarm_type")) != self._alarm_type:
                return
            self._state = self._state_for_level(data.get("alarm_level", ""))
        elif operation == MessageType.CONFIGURATION_ADDED.value:
            self._configuration = configuration_from_message(data)
        elif isinstance(data.get("active_alarms"), list):
            # device_updated carries the full list of active alarms
            state = self._state_from_active_alarms(data["active_alarms"])
            if state == self._state:
                return
            self._state = state
        else:
            return
        self.async_write_ha_state()
        log_with_entity(_LOGGER, logging.DEBUG, self, "Value updated: %s", self.native_value)


class FlowTestSensor(AlarmTestSensor):
    """Representation of a Leakomatic Flow Test sensor.

    This sensor monitors the flow duration and changes state based on configured thresholds:
    - CLEAR: No flow or flow duration below warning threshold
    - WARNING: Flow duration exceeds warning threshold
    - ALARM: Flow duration exceeds alarm threshold
    """

    _config_attributes = {
        "duration_away": "ft_alarm_away",
        "duration_home": "ft_warning_home",
        "alarm_delay": "ft_alarm_delay",
    }

    def __init__(
        self,
        device_info: dict[str, Any],
        device_id: str,
        device_data: dict[str, Any] | None,
    ) -> None:
        """Initialize the flow test sensor."""
        super().__init__(
            device_info, device_id, device_data, key="flow_test", alarm_type=AlarmType.FLOW_TEST.value
        )


class QuickTestSensor(AlarmTestSensor):
    """Representation of a Leakomatic Quick Test sensor.

    This sensor monitors the quick test status and changes state based on alarm levels:
    - CLEAR: No alarm
    - WARNING: Quick test warning threshold exceeded
    - ALARM: Quick test alarm threshold exceeded
    """

    _config_attributes = {
        "alarm_delay": "qt_alarm_delay",
        "index_limit": "qt_index_limit",
    }

    def __init__(
        self,
        device_info: dict[str, Any],
        device_id: str,
        device_data: dict[str, Any] | None,
    ) -> None:
        """Initialize the quick test sensor."""
        super().__init__(
            device_info, device_id, device_data, key="quick_test", alarm_type=AlarmType.QUICK_TEST.value
        )


class TightnessTestSensor(AlarmTestSensor):
    """Representation of a Leakomatic Tightness Test sensor.

    This sensor monitors the tightness test status and changes state based on alarm levels:
    - CLEAR: No alarm
    - WARNING: Tightness test warning threshold exceeded
    - ALARM: Tightness test alarm threshold exceeded
    """

    _config_attributes = {
        "pulse_free_periods": "tt_count",
        "period_duration": "tt_length",
        "alarm_delay": "tt_alarm_delay",
    }

    def __init__(
        self,
        device_info: dict[str, Any],
        device_id: str,
        device_data: dict[str, Any] | None,
    ) -> None:
        """Initialize the tightness test sensor."""
        super().__init__(
            device_info, device_id, device_data, key="tightness_test", alarm_type=AlarmType.TIGHTNESS_TEST.value
        )


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


# The alarm test sensors, used by the message handlers above (looked up when they run)
ALARM_SENSORS = (FlowTestSensor, QuickTestSensor, TightnessTestSensor)
