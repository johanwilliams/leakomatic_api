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


@pytest.mark.usefixtures("entity_registry_enabled_by_default")
async def test_total_volume_from_calibration_message(
    hass: HomeAssistant, setup_integration: MockLeakomatic
) -> None:
    """HA-194: water_meter_calibration_updated updates total volume, and only for its device."""
    assert hass.states.get("sensor.leakomatic_total_volume").state == "1.0"

    setup_integration.send(ws_message("water_meter_calibration_updated", "SERIAL-A", total_flow_volume=2500))
    assert hass.states.get("sensor.leakomatic_total_volume").state == "2.5"

    setup_integration.send(ws_message("water_meter_calibration_updated", "SERIAL-OTHER", total_flow_volume=9999))
    assert hass.states.get("sensor.leakomatic_total_volume").state == "2.5"


@pytest.mark.usefixtures("entity_registry_enabled_by_default")
async def test_invalid_total_volume_is_logged(
    hass: HomeAssistant, setup_integration: MockLeakomatic, caplog: pytest.LogCaptureFixture
) -> None:
    """HA-194: a value that is not a number is logged and the state is kept."""
    setup_integration.send(ws_message("water_meter_calibration_updated", "SERIAL-A", total_flow_volume="n/a"))

    assert hass.states.get("sensor.leakomatic_total_volume").state == "1.0"
    assert "Error updating total volume" in caplog.text


async def test_disabled_entities_are_skipped(
    hass: HomeAssistant, setup_integration: MockLeakomatic, caplog: pytest.LogCaptureFixture
) -> None:
    """Entities disabled by default (e.g. total volume) are never written to."""
    # Total volume is disabled by default, flow duration is not; both get flow_updated.
    setup_integration.send(ws_message("flow_updated", "SERIAL-A", flow_duration=42, total_flow_volume=3000))

    assert hass.states.get("sensor.leakomatic_total_volume") is None
    assert hass.states.get("sensor.leakomatic_flow_duration").state == "42"
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
