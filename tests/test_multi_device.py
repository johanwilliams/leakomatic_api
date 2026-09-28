"""Several devices on one account: one login and one websocket, entities per device."""
from __future__ import annotations

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .conftest import MockLeakomatic, device_updated_message, make_device_data, ws_message

TWO_DEVICES = {
    "1001": make_device_data("1001", "SERIAL-A", name="Huddinge", port_state=0),
    "1002": make_device_data("1002", "SERIAL-B", name="Aland", port_state=128),
}

pytestmark = pytest.mark.parametrize("devices", [TWO_DEVICES])


def _alarm(serial: str, alarm_type: str, level: str) -> dict:
    message = ws_message("alarm_triggered", serial, alarm_type=alarm_type, alarm_level=level)
    message["message"]["data"]["operation"] = "alarm_triggered"
    return message


async def test_one_device_and_entity_set_per_device(
    hass: HomeAssistant, config_entry: MockConfigEntry, setup_integration: MockLeakomatic
) -> None:
    devices = dr.async_entries_for_config_entry(dr.async_get(hass), config_entry.entry_id)
    assert sorted((d.name, d.serial_number) for d in devices) == [("Aland", "SERIAL-B"), ("Huddinge", "SERIAL-A")]

    entities = er.async_entries_for_config_entry(er.async_get(hass), config_entry.entry_id)
    per_device: dict[str, set[str]] = {}
    for entity in entities:
        per_device.setdefault(entity.device_id, set()).add(entity.unique_id.split("_", 1)[1])
    assert len(per_device) == 2
    keys_a, keys_b = per_device.values()
    assert keys_a == keys_b  # the same set of entities for both devices
    assert len({e.unique_id for e in entities}) == len(entities)

    # One login, one websocket for the whole account
    setup_integration.client.async_authenticate.assert_awaited_once()
    setup_integration.client.connect_to_websocket.assert_awaited_once()


async def test_startup_state_per_device(hass: HomeAssistant, setup_integration: MockLeakomatic) -> None:
    assert hass.states.get("binary_sensor.huddinge_valve").state == "on"
    assert hass.states.get("binary_sensor.aland_valve").state == "off"


async def test_messages_reach_only_their_device(hass: HomeAssistant, setup_integration: MockLeakomatic) -> None:
    setup_integration.send(device_updated_message("SERIAL-B", 1002, mode=2))
    setup_integration.send(ws_message("status_message", "SERIAL-A", port_state=128, rssi=-70))
    setup_integration.send(_alarm("SERIAL-B", "0", "2"))
    setup_integration.send(ws_message("flow_updated", "SERIAL-A", flow_mode=1, flow_duration=12))

    assert hass.states.get("select.huddinge_mode").state == "home"
    assert hass.states.get("select.aland_mode").state == "pause"
    assert hass.states.get("binary_sensor.huddinge_valve").state == "off"
    assert hass.states.get("binary_sensor.aland_valve").state == "off"
    assert hass.states.get("sensor.huddinge_signal_strength").state == "-70"
    assert hass.states.get("sensor.aland_signal_strength").state == "-60"
    assert hass.states.get("sensor.huddinge_flow_test").state == "clear"
    assert hass.states.get("sensor.aland_flow_test").state == "alarm"
    assert hass.states.get("binary_sensor.huddinge_flow_indicator").state == "on"
    assert hass.states.get("binary_sensor.aland_flow_indicator").state == "unknown"
    # Online: A and B have both reported (status/flow for A, device_updated/alarm for B)
    assert hass.states.get("binary_sensor.huddinge_online_status").state == "on"
    assert hass.states.get("binary_sensor.aland_online_status").state == "on"

    setup_integration.send(ws_message("device_offline", "SERIAL-B"))
    assert hass.states.get("binary_sensor.huddinge_online_status").state == "on"
    assert hass.states.get("binary_sensor.aland_online_status").state == "off"


async def test_commands_go_to_the_right_device(hass: HomeAssistant, setup_integration: MockLeakomatic) -> None:
    await hass.services.async_call(
        "select", "select_option", {"entity_id": "select.aland_mode", "option": "away"}, blocking=True
    )
    setup_integration.client.async_change_mode.assert_awaited_once_with("away", "1002")

    await hass.services.async_call("button", "press", {"entity_id": "button.huddinge_reset_alarms"}, blocking=True)
    setup_integration.client.async_reset_alarms.assert_awaited_once_with("1001")


async def test_no_change_mode_service(hass: HomeAssistant, setup_integration: MockLeakomatic) -> None:
    """HA-200: the mode is changed with the select entity; the integration registers no services."""
    assert not hass.services.has_service("leakomatic", "change_mode")
    assert hass.services.async_services_for_domain("leakomatic") == {}
