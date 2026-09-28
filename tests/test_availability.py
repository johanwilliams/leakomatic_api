"""HA-196: entities become unavailable when the websocket stays disconnected."""
from __future__ import annotations

import logging
from datetime import timedelta

import pytest
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from custom_components.leakomatic.const import DEVICE_OFFLINE_AFTER, UNAVAILABLE_AFTER_DISCONNECT

from .conftest import MockLeakomatic, ws_message

CONNECTIVITY = "binary_sensor.leakomatic_websocket_connectivity"


def _leakomatic_states(hass: HomeAssistant) -> dict[str, str]:
    return {
        state.entity_id: state.state
        for state in hass.states.async_all()
        if state.entity_id.split(".")[1].startswith("leakomatic_")
    }


def _unavailable(hass: HomeAssistant) -> set[str]:
    return {entity_id for entity_id, state in _leakomatic_states(hass).items() if state == STATE_UNAVAILABLE}


async def _pass_time(hass: HomeAssistant, seconds: float) -> None:
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=seconds))
    await hass.async_block_till_done()


async def test_available_at_setup_before_websocket_connects(
    hass: HomeAssistant, setup_integration: MockLeakomatic
) -> None:
    """The REST data at setup is fresh, so entities are available before the websocket connects."""
    assert _leakomatic_states(hass)
    assert _unavailable(hass) == set()


async def test_unavailable_when_websocket_never_connects(
    hass: HomeAssistant, setup_integration: MockLeakomatic, caplog: pytest.LogCaptureFixture
) -> None:
    await _pass_time(hass, UNAVAILABLE_AFTER_DISCONNECT + 1)

    states = _leakomatic_states(hass)
    assert _unavailable(hass) == set(states) - {CONNECTIVITY}
    assert states[CONNECTIVITY] == "off"
    # Logged once, at info level
    lost = [r for r in caplog.records if "marking entities unavailable" in r.getMessage()]
    assert len(lost) == 1
    assert lost[0].levelno == logging.INFO


async def test_short_disconnect_is_not_visible(hass: HomeAssistant, setup_integration: MockLeakomatic) -> None:
    """The nightly disconnect, reconnected within seconds, never makes entities unavailable."""
    setup_integration.set_connected(True)
    setup_integration.set_connected(False)
    await _pass_time(hass, 5)
    setup_integration.set_connected(True)

    await _pass_time(hass, UNAVAILABLE_AFTER_DISCONNECT + 1)

    assert _unavailable(hass) == set()


async def test_long_disconnect_and_recovery(
    hass: HomeAssistant, setup_integration: MockLeakomatic, caplog: pytest.LogCaptureFixture
) -> None:
    setup_integration.set_connected(True)
    setup_integration.set_connected(False)
    await _pass_time(hass, UNAVAILABLE_AFTER_DISCONNECT - 10)
    assert _unavailable(hass) == set()

    await _pass_time(hass, UNAVAILABLE_AFTER_DISCONNECT + 1)
    assert "select.leakomatic_mode" in _unavailable(hass)

    setup_integration.set_connected(True)
    await hass.async_block_till_done()

    assert _unavailable(hass) == set()
    assert hass.states.get("select.leakomatic_mode").state == "home"
    assert "entities are available again" in caplog.text


async def test_unload_stops_the_timer(
    hass: HomeAssistant, config_entry: MockConfigEntry, setup_integration: MockLeakomatic
) -> None:
    """Unloading while the grace period runs leaves no timer behind."""
    availability = config_entry.runtime_data.availability
    assert availability._unsub_timer is not None  # the websocket has not connected yet

    assert await hass.config_entries.async_unload(config_entry.entry_id)
    await hass.async_block_till_done()

    assert availability._unsub_timer is None


# --- HA-198: Online Status turns off when the device has been silent too long

ONLINE = "binary_sensor.leakomatic_online_status"


async def _tick(hass: HomeAssistant, freezer, seconds: float) -> None:
    freezer.tick(timedelta(seconds=seconds))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


def _device_message(mock: MockLeakomatic) -> None:
    mock.send(ws_message("quick_test_updated", "SERIAL-A", current_quick_test=0.1))


async def test_online_turns_off_after_silence(
    hass: HomeAssistant, setup_integration: MockLeakomatic, freezer, caplog: pytest.LogCaptureFixture
) -> None:
    setup_integration.set_connected(True)
    _device_message(setup_integration)
    assert hass.states.get(ONLINE).state == "on"

    # Reports every 5 minutes keep it on
    for _ in range(4):
        await _tick(hass, freezer, 300)
        _device_message(setup_integration)
    assert hass.states.get(ONLINE).state == "on"

    await _tick(hass, freezer, DEVICE_OFFLINE_AFTER - 60)
    assert hass.states.get(ONLINE).state == "on"

    await _tick(hass, freezer, 120)
    assert hass.states.get(ONLINE).state == "off"
    assert "marking it offline" in caplog.text

    _device_message(setup_integration)
    assert hass.states.get(ONLINE).state == "on"


async def test_unknown_turns_off_when_device_never_reports(
    hass: HomeAssistant, setup_integration: MockLeakomatic, freezer
) -> None:
    """After startup the sensor is unknown; with no report at all it turns off after the timeout."""
    setup_integration.set_connected(True)
    assert hass.states.get(ONLINE).state == "unknown"

    await _tick(hass, freezer, DEVICE_OFFLINE_AFTER + 60)

    assert hass.states.get(ONLINE).state == "off"


async def test_connection_outage_does_not_mark_device_offline(
    hass: HomeAssistant, setup_integration: MockLeakomatic, freezer
) -> None:
    """Silence while the websocket was down says nothing about the device."""
    setup_integration.set_connected(True)
    _device_message(setup_integration)

    setup_integration.set_connected(False)
    await _tick(hass, freezer, UNAVAILABLE_AFTER_DISCONNECT + 60)
    await _tick(hass, freezer, DEVICE_OFFLINE_AFTER)
    assert hass.states.get(ONLINE).state == STATE_UNAVAILABLE

    setup_integration.set_connected(True)
    await _tick(hass, freezer, 60)
    assert hass.states.get(ONLINE).state == "on"

    # The timeout counts from when the connection came back
    await _tick(hass, freezer, DEVICE_OFFLINE_AFTER)
    assert hass.states.get(ONLINE).state == "off"
