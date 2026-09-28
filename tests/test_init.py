"""Tests for setting up and unloading the Leakomatic integration."""
from __future__ import annotations

import pytest
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


async def test_unload_closes_the_client(
    hass: HomeAssistant, config_entry: MockConfigEntry, setup_integration: MockLeakomatic
) -> None:
    """HA-205: the client's HTTP session is closed when the entry unloads."""
    assert await hass.config_entries.async_unload(config_entry.entry_id)
    await hass.async_block_till_done()

    setup_integration.client.async_close.assert_awaited_once()


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


# --- HA-199: setup failures are retried, or start reauthentication


async def _setup(hass: HomeAssistant, config_entry: MockConfigEntry) -> None:
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()


async def test_rejected_credentials_start_reauth(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_leakomatic: MockLeakomatic
) -> None:
    mock_leakomatic.client.async_authenticate.return_value = False
    mock_leakomatic.client.error_code = "invalid_credentials"

    await _setup(hass, config_entry)

    assert config_entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress()
    assert [flow["context"]["source"] for flow in flows] == ["reauth"]


@pytest.mark.parametrize("error_code", ["cannot_connect", "auth_token_missing", "xsrf_token_missing", None])
async def test_login_problem_is_retried(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_leakomatic: MockLeakomatic, error_code: str | None
) -> None:
    """Anything but rejected credentials is treated as temporary."""
    mock_leakomatic.client.async_authenticate.return_value = False
    mock_leakomatic.client.error_code = error_code

    await _setup(hass, config_entry)

    assert config_entry.state is ConfigEntryState.SETUP_RETRY
    assert not hass.config_entries.flow.async_progress()
    # HA-205: the failed attempt's client is closed, not left open until shutdown
    mock_leakomatic.client.async_close.assert_awaited_once()


async def test_missing_device_data_is_retried(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_leakomatic: MockLeakomatic
) -> None:
    mock_leakomatic.client.async_get_device_data.side_effect = None
    mock_leakomatic.client.async_get_device_data.return_value = None

    await _setup(hass, config_entry)

    assert config_entry.state is ConfigEntryState.SETUP_RETRY


# --- HA-269: the websocket loop does not depend on a token fetched during setup


async def test_setup_starts_websocket_without_fetching_a_token(
    hass: HomeAssistant, config_entry: MockConfigEntry, setup_integration: MockLeakomatic
) -> None:
    """The loop gets its own token, so a failed fetch at startup cannot leave it unstarted."""
    setup_integration.client.connect_to_websocket.assert_awaited_once()
    setup_integration.client.async_get_websocket_token.assert_not_awaited()


# --- HA-261: a rejected login during operation starts reauthentication


async def test_rejected_login_during_operation_starts_reauth(
    hass: HomeAssistant, config_entry: MockConfigEntry, setup_integration: MockLeakomatic
) -> None:
    (auth_failed,) = setup_integration.client.set_auth_failed_callback.call_args.args
    auth_failed()
    await hass.async_block_till_done()

    flows = hass.config_entries.flow.async_progress()
    assert [flow["context"]["source"] for flow in flows] == ["reauth"]
