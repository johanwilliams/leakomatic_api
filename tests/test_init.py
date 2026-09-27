"""Tests for setting up and unloading the Leakomatic integration."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .conftest import MockLeakomatic, ws_message


async def test_setup_creates_entities(
    hass: HomeAssistant, config_entry: MockConfigEntry, setup_integration: MockLeakomatic
) -> None:
    """The integration loads and creates the main entities from the REST data."""
    assert config_entry.state is ConfigEntryState.LOADED

    assert hass.states.get("select.leakomatic_mode").state == "home"
    assert hass.states.get("binary_sensor.leakomatic_valve").state == "on"
    assert hass.states.get("sensor.leakomatic_signal_strength").state == "-60"
    # The websocket task was started with the token from the client
    setup_integration.client.connect_to_websocket.assert_awaited_once()


async def test_unload(
    hass: HomeAssistant, config_entry: MockConfigEntry, setup_integration: MockLeakomatic
) -> None:
    """Unloading stops the websocket and unloads the entry."""
    assert await hass.config_entries.async_unload(config_entry.entry_id)
    await hass.async_block_till_done()

    assert config_entry.state is ConfigEntryState.NOT_LOADED
    setup_integration.client.stop_websocket.assert_awaited_once()


async def test_unload_cancels_websocket_task(
    hass: HomeAssistant, config_entry: MockConfigEntry, setup_integration: MockLeakomatic
) -> None:
    """HA-262: the websocket task is cancelled when the entry unloads, not left running."""
    assert not setup_integration.ws_task_cancelled

    assert await hass.config_entries.async_unload(config_entry.entry_id)
    await hass.async_block_till_done()

    assert setup_integration.ws_task_cancelled


async def test_unload_removes_websocket_listeners(
    hass: HomeAssistant, config_entry: MockConfigEntry, setup_integration: MockLeakomatic
) -> None:
    """The platforms' websocket listeners are removed when the entry unloads."""
    data = config_entry.runtime_data
    assert len(data.ws_listeners) == 3  # sensor, binary_sensor, select

    assert await hass.config_entries.async_unload(config_entry.entry_id)
    await hass.async_block_till_done()

    assert data.ws_listeners == []


async def test_reload_twice(
    hass: HomeAssistant, config_entry: MockConfigEntry, setup_integration: MockLeakomatic
) -> None:
    """Reloading twice in a row keeps the same entities, and messages still arrive."""
    for _ in range(2):
        assert await hass.config_entries.async_reload(config_entry.entry_id)
        await hass.async_block_till_done()

    assert config_entry.state is ConfigEntryState.LOADED
    assert len(config_entry.runtime_data.ws_listeners) == 3
    assert hass.states.get("select.leakomatic_mode").state == "home"
    assert len(hass.states.async_entity_ids("select")) == 1

    setup_integration.send(ws_message("device_updated", "SERIAL-A", mode=1))
    assert hass.states.get("select.leakomatic_mode").state == "away"
