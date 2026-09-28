"""Tests for how websocket messages reach the entities."""
from __future__ import annotations

import logging

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .conftest import MockLeakomatic, device_updated_message, make_device_data, ws_message


def _errors(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.levelno >= logging.ERROR]


async def test_mode_follows_device_updated(hass: HomeAssistant, setup_integration: MockLeakomatic) -> None:
    """A device_updated message changes the mode select."""
    setup_integration.send(ws_message("device_updated", "SERIAL-A", mode=2))

    assert hass.states.get("select.leakomatic_mode").state == "pause"


async def test_mode_follows_device_updated_without_serial_in_data(
    hass: HomeAssistant, setup_integration: MockLeakomatic
) -> None:
    """Regression from the first HA-195 fix, seen live: device_updated has the serial only in message["device"]."""
    setup_integration.send(device_updated_message("SERIAL-A", 1001, mode=2))

    assert hass.states.get("select.leakomatic_mode").state == "pause"


async def test_device_updated_does_not_drive_flow_indicator(
    hass: HomeAssistant, setup_integration: MockLeakomatic
) -> None:
    """device_updated can carry a stale flow_mode of 1; only flow_updated drives the flow indicator."""
    setup_integration.send(device_updated_message("SERIAL-A", 1001, mode=0, flow_mode=1))
    assert hass.states.get("binary_sensor.leakomatic_flow_indicator").state == "unknown"

    setup_integration.send(ws_message("flow_updated", "SERIAL-A", flow_mode=1))
    assert hass.states.get("binary_sensor.leakomatic_flow_indicator").state == "on"


async def test_unhandled_message_type_is_not_an_error(
    hass: HomeAssistant, setup_integration: MockLeakomatic, caplog: pytest.LogCaptureFixture
) -> None:
    """HA-192: a message type without a handler is logged at debug, not as an error."""
    with caplog.at_level(logging.DEBUG):
        setup_integration.send(ws_message("configuration_added", "SERIAL-A"))

    assert not _errors(caplog)
    assert "Received unhandled message type: configuration_added" in caplog.text


async def test_error_in_one_platform_does_not_stop_the_others(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    setup_integration: MockLeakomatic,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """HA-192: if one platform's callback raises, the other platforms still get the message."""

    def broken_callback(message: dict) -> None:
        raise RuntimeError("boom")

    config_entry.runtime_data.ws_listeners.insert(0, broken_callback)

    setup_integration.send(ws_message("device_updated", "SERIAL-A", mode=1))

    assert hass.states.get("select.leakomatic_mode").state == "away"
    assert "Error handling websocket message" in caplog.text


@pytest.mark.parametrize(
    "devices",
    [
        {
            "1001": make_device_data("1001", "SERIAL-A", name="Leakomatic A"),
            "1002": make_device_data("1002", "SERIAL-B", name="Leakomatic B"),
        }
    ],
)
async def test_mode_update_only_changes_matching_device(
    hass: HomeAssistant, setup_integration: MockLeakomatic
) -> None:
    """HA-195: a mode change for one device does not change another device's select."""
    setup_integration.send(ws_message("device_updated", "SERIAL-A", mode=1))

    assert hass.states.get("select.leakomatic_a_mode").state == "away"
    assert hass.states.get("select.leakomatic_b_mode").state == "home"


TOTAL_VOLUME = "sensor.leakomatic_total_volume"


@pytest.mark.usefixtures("entity_registry_enabled_by_default")
async def test_total_volume_units(hass: HomeAssistant, setup_integration: MockLeakomatic) -> None:
    """HA-211: total_flow_volume is in m³; total_volume (flow and calibration messages) is in litres."""
    state = hass.states.get(TOTAL_VOLUME)
    assert state.state == "12.345"  # startup data, m³ as is
    assert state.attributes["device_class"] == "water"
    assert state.attributes["state_class"] == "total_increasing"
    assert state.attributes["unit_of_measurement"] == "m³"

    setup_integration.send(ws_message("flow_updated", "SERIAL-A", flow_mode=0, flow_duration=5, total_volume=12400))
    assert hass.states.get(TOTAL_VOLUME).state == "12.4"

    setup_integration.send(ws_message("water_meter_calibration_updated", "SERIAL-A", total_volume=20000))
    assert hass.states.get(TOTAL_VOLUME).state == "20.0"

    setup_integration.send(device_updated_message("SERIAL-A", 1001, mode=0, total_flow_volume="20.125"))
    assert hass.states.get(TOTAL_VOLUME).state == "20.125"

    # Another device's meter does not touch this one; a flow message without a volume keeps it
    setup_integration.send(ws_message("water_meter_calibration_updated", "SERIAL-OTHER", total_volume=99000))
    setup_integration.send(ws_message("flow_updated", "SERIAL-A", flow_mode=1, flow_duration=0))
    assert hass.states.get(TOTAL_VOLUME).state == "20.125"


@pytest.mark.usefixtures("entity_registry_enabled_by_default")
async def test_invalid_total_volume_is_logged(
    hass: HomeAssistant, setup_integration: MockLeakomatic, caplog: pytest.LogCaptureFixture
) -> None:
    """HA-194: a value that is not a number is logged and the state is kept."""
    setup_integration.send(ws_message("water_meter_calibration_updated", "SERIAL-A", total_volume="n/a"))

    assert hass.states.get(TOTAL_VOLUME).state == "12.345"
    assert "Error updating total volume" in caplog.text


@pytest.mark.usefixtures("entity_registry_enabled_by_default")
async def test_analog_sensors(hass: HomeAssistant, setup_integration: MockLeakomatic) -> None:
    """HA-211: analog_sensor_message; type 1 is pressure, 2 temperature; not connected is unknown."""
    def analog(sensor_type, value, connected):
        return ws_message(
            "analog_sensor_message", "SERIAL-A", sensor_type=sensor_type, port=5, value=value, connected=connected
        )

    setup_integration.send(analog(2, 8.46, 1))
    setup_integration.send(analog(1, 4.23, 1))
    assert hass.states.get("sensor.leakomatic_temperature").state == "8.5"
    assert hass.states.get("sensor.leakomatic_pressure").state == "4.2"

    setup_integration.send(analog("2", 9.0, "0"))  # strings, sensor disconnected
    assert hass.states.get("sensor.leakomatic_temperature").state == "unknown"
    assert hass.states.get("sensor.leakomatic_pressure").state == "4.2"


async def test_disabled_entities_are_skipped(
    hass: HomeAssistant, setup_integration: MockLeakomatic, caplog: pytest.LogCaptureFixture
) -> None:
    """Entities disabled by default (e.g. total volume) are never written to."""
    # Total volume is disabled by default, flow duration is not; both get flow_updated.
    setup_integration.send(ws_message("flow_updated", "SERIAL-A", flow_duration=42, total_volume=3000))

    assert hass.states.get("sensor.leakomatic_total_volume") is None
    assert hass.states.get("sensor.leakomatic_last_flow_duration").state == "42"
    assert not _errors(caplog)


# --- HA-197: missing or invalid data is unknown, not "off"

FLOW = "binary_sensor.leakomatic_flow_indicator"
ONLINE = "binary_sensor.leakomatic_online_status"
VALVE = "binary_sensor.leakomatic_valve"


async def test_flow_and_online_unknown_at_setup(hass: HomeAssistant, setup_integration: MockLeakomatic) -> None:
    """The REST data at setup says nothing reliable about flow or being online."""
    assert hass.states.get(FLOW).state == "unknown"
    online = hass.states.get(ONLINE)
    assert online.state == "unknown"
    assert online.attributes["last_seen"] == "2026-01-01T12:00:00+00:00"


async def test_online_after_first_message(hass: HomeAssistant, setup_integration: MockLeakomatic) -> None:
    setup_integration.send(ws_message("status_message", "SERIAL-A", port_state=0, rssi=-60))
    assert hass.states.get(ONLINE).state == "on"


@pytest.mark.parametrize("devices", [{"1001": make_device_data("1001", "SERIAL-A", port_state=None)}])
async def test_valve_unknown_without_port_state(hass: HomeAssistant, setup_integration: MockLeakomatic) -> None:
    """Without port_state the valve is unknown - never 'closed' by default."""
    assert hass.states.get(VALVE).state == "unknown"


async def test_invalid_values_are_unknown(
    hass: HomeAssistant, setup_integration: MockLeakomatic, caplog: pytest.LogCaptureFixture
) -> None:
    setup_integration.send(ws_message("flow_updated", "SERIAL-A", flow_mode="garbage"))
    setup_integration.send(ws_message("status_message", "SERIAL-A", port_state="garbage", rssi=-60))

    assert hass.states.get(FLOW).state == "unknown"
    assert hass.states.get(VALVE).state == "unknown"
    assert "Invalid value: garbage" in caplog.text
    assert "Invalid port state value: garbage" in caplog.text


async def test_device_offline_marks_device_offline(hass: HomeAssistant, setup_integration: MockLeakomatic) -> None:
    """HA-279: device_offline sets the online sensor to off; the next message sets it on again."""
    setup_integration.send(ws_message("status_message", "SERIAL-A", port_state=0, rssi=-60))
    last_seen = hass.states.get(ONLINE).attributes["last_seen"]

    setup_integration.send(ws_message("device_offline", "SERIAL-A"))
    offline = hass.states.get(ONLINE)
    assert offline.state == "off"
    assert offline.attributes["last_seen"] == last_seen  # not a sign of life

    setup_integration.send(ws_message("status_message", "SERIAL-A", port_state=0, rssi=-60))
    assert hass.states.get(ONLINE).state == "on"


# --- HA-263: the alarm test sensors are ENUM sensors with a closed set of states

FLOW_TEST = "sensor.leakomatic_flow_test"


def _alarm(serial: str, alarm_type: str, alarm_level: str) -> dict:
    """alarm_triggered as the server sends it: operation and strings in data."""
    message = ws_message("alarm_triggered", serial, alarm_type=alarm_type, alarm_level=alarm_level)
    message["message"]["data"]["operation"] = "alarm_triggered"
    return message


async def test_alarm_sensor_is_enum(hass: HomeAssistant, setup_integration: MockLeakomatic) -> None:
    state = hass.states.get(FLOW_TEST)
    assert state.state == "clear"
    assert state.attributes["device_class"] == "enum"
    assert state.attributes["options"] == ["clear", "warning", "alarm"]


async def test_alarm_levels(hass: HomeAssistant, setup_integration: MockLeakomatic) -> None:
    for level, expected in (("1", "warning"), ("2", "alarm"), ("0", "clear")):
        setup_integration.send(_alarm("SERIAL-A", "0", level))
        assert hass.states.get(FLOW_TEST).state == expected

    # Another alarm type does not touch the flow test sensor
    setup_integration.send(_alarm("SERIAL-A", "1", "2"))
    assert hass.states.get(FLOW_TEST).state == "clear"


async def test_unknown_alarm_level_is_unknown(
    hass: HomeAssistant, setup_integration: MockLeakomatic, caplog: pytest.LogCaptureFixture
) -> None:
    """An unknown level must not leave the old state in place: the guard does not know."""
    setup_integration.send(_alarm("SERIAL-A", "0", "7"))

    assert hass.states.get(FLOW_TEST).state == "unknown"
    assert "Unknown alarm level received: 7" in caplog.text


@pytest.mark.parametrize(
    "devices",
    [{"1001": make_device_data("1001", "SERIAL-A", current_alarm={"alarm_type": 0, "level": 1})}],
)
async def test_alarm_state_from_startup_data(hass: HomeAssistant, setup_integration: MockLeakomatic) -> None:
    assert hass.states.get(FLOW_TEST).state == "warning"


# --- HA-283: when the pause mode ends

PAUSE_END = "sensor.leakomatic_pause_ends"
STOPTIME = 1_893_456_000  # 2030-01-01 00:00:00 UTC


def _status(serial: str, **data) -> dict:
    return ws_message("status_message", serial, port_state=0, rssi=-60, **data)


async def test_pause_end_follows_mode_and_stoptime(hass: HomeAssistant, setup_integration: MockLeakomatic) -> None:
    assert hass.states.get(PAUSE_END).state == "unknown"  # home mode at startup

    setup_integration.send(device_updated_message("SERIAL-A", 1001, mode=2))
    setup_integration.send(_status("SERIAL-A", mode_stoptime=STOPTIME))
    state = hass.states.get(PAUSE_END)
    assert state.state == "2030-01-01T00:00:00+00:00"
    assert state.attributes["device_class"] == "timestamp"

    # Back to home: no pause end, even before a status message clears the time
    setup_integration.send(device_updated_message("SERIAL-A", 1001, mode=0))
    assert hass.states.get(PAUSE_END).state == "unknown"


async def test_pause_end_cleared_by_zero_stoptime(hass: HomeAssistant, setup_integration: MockLeakomatic) -> None:
    setup_integration.send(device_updated_message("SERIAL-A", 1001, mode=2))
    setup_integration.send(_status("SERIAL-A", mode_stoptime=str(STOPTIME)))  # sometimes a string
    assert hass.states.get(PAUSE_END).state == "2030-01-01T00:00:00+00:00"

    setup_integration.send(_status("SERIAL-A", mode_stoptime=0))
    assert hass.states.get(PAUSE_END).state == "unknown"


@pytest.mark.parametrize(
    "devices", [{"1001": make_device_data("1001", "SERIAL-A", mode=2, mode_stoptime=STOPTIME)}]
)
async def test_pause_end_from_startup_data(hass: HomeAssistant, setup_integration: MockLeakomatic) -> None:
    assert hass.states.get(PAUSE_END).state == "2030-01-01T00:00:00+00:00"


# --- HA-272: alarm state from active_alarms; the settings survive alarm messages

QUICK = "sensor.leakomatic_quick_test"
TIGHTNESS = "sensor.leakomatic_tightness_test"
CONFIG_OLD = {"id": 1, "time": "2026-01-01T00:00:00.000Z", "ft_alarm_away": 5, "ft_warning_home": 20,
              "ft_alarm_delay": 5, "qt_alarm_delay": 1, "qt_index_limit": 1.0, "tt_count": 1,
              "tt_length": 15, "tt_alarm_delay": 1}
CONFIG_NEW = {**CONFIG_OLD, "id": 2, "time": "2026-02-01T00:00:00.000Z", "ft_alarm_away": 10}


def _active(alarm_type: int, level: int, active: bool = True) -> dict:
    return {"alarm_id": 1, "alarm_type": alarm_type, "level": level, "is_active": active}


@pytest.mark.parametrize(
    "devices", [{"1001": make_device_data("1001", "SERIAL-A", configurations=[CONFIG_NEW, CONFIG_OLD])}]
)
async def test_settings_survive_alarm_messages(hass: HomeAssistant, setup_integration: MockLeakomatic) -> None:
    """The attributes come from the latest configuration and stay after an alarm message."""
    attrs = hass.states.get(FLOW_TEST).attributes
    assert (attrs["duration_away"], attrs["duration_home"], attrs["alarm_delay"]) == (10, 20, 5)

    setup_integration.send(_alarm("SERIAL-A", "0", "1"))
    state = hass.states.get(FLOW_TEST)
    assert state.state == "warning"
    assert state.attributes["duration_away"] == 10

    quick = hass.states.get(QUICK).attributes
    assert (quick["alarm_delay"], quick["index_limit"]) == (1, 1.0)
    tight = hass.states.get(TIGHTNESS).attributes
    assert (tight["pulse_free_periods"], tight["period_duration"], tight["alarm_delay"]) == (1, 15, 1)


@pytest.mark.parametrize("devices", [{"1001": make_device_data("1001", "SERIAL-A", configurations=[CONFIG_OLD])}])
async def test_configuration_added_updates_settings(hass: HomeAssistant, setup_integration: MockLeakomatic) -> None:
    """A setting changed in Leakomatic's app shows without a restart."""
    assert hass.states.get(FLOW_TEST).attributes["duration_away"] == 5

    changed = ws_message("configuration_added", "SERIAL-A", **{**CONFIG_OLD, "id": 3, "ft_alarm_away": 30})
    changed["message"]["data"]["operation"] = "configuration_added"
    setup_integration.send(changed)

    assert hass.states.get(FLOW_TEST).attributes["duration_away"] == 30
    assert hass.states.get(FLOW_TEST).state == "clear"


@pytest.mark.parametrize(
    "devices",
    [{"1001": make_device_data("1001", "SERIAL-A", active_alarms=[_active(0, 1), _active(1, 2), _active(2, 2, False)])}],
)
async def test_several_active_alarms_at_startup(hass: HomeAssistant, setup_integration: MockLeakomatic) -> None:
    """Two tests alarming at the same time both show; an inactive alarm does not count."""
    assert hass.states.get(FLOW_TEST).state == "warning"
    assert hass.states.get(QUICK).state == "alarm"
    assert hass.states.get(TIGHTNESS).state == "clear"


async def test_device_updated_active_alarms(hass: HomeAssistant, setup_integration: MockLeakomatic) -> None:
    """device_updated carries the full list: an alarm appears, and an empty list clears it (reset)."""
    setup_integration.send(device_updated_message("SERIAL-A", 1001, mode=0, active_alarms=[_active(2, 1), _active(2, 2)]))
    assert hass.states.get(TIGHTNESS).state == "alarm"  # the highest level
    assert hass.states.get(FLOW_TEST).state == "clear"

    setup_integration.send(device_updated_message("SERIAL-A", 1001, mode=0, active_alarms=[]))
    assert hass.states.get(TIGHTNESS).state == "clear"
