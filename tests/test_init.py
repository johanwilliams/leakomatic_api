"""Tests for setting up and unloading the Leakomatic integration."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .conftest import MockLeakomatic


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
