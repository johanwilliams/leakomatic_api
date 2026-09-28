"""HA-196: entities become unavailable when the websocket stays disconnected."""
from __future__ import annotations

import logging
from datetime import timedelta

import pytest
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from custom_components.leakomatic.const import UNAVAILABLE_AFTER_DISCONNECT

from .conftest import MockLeakomatic

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
