"""Shared fixtures for the Leakomatic tests.

All device data here is invented. Do not paste real payloads from a live
account into the tests: they contain serial numbers, user IDs and locations.
"""
from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.leakomatic.const import DOMAIN

EMAIL = "user@example.com"
PASSWORD = "secret"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Allow Home Assistant to load the integration from custom_components."""
    yield


def make_device_data(device_id: str, serial: str, name: str = "Leakomatic", **overrides: Any) -> dict[str, Any]:
    """Return REST device data shaped like devices/<id>.json."""
    data: dict[str, Any] = {
        "id": int(device_id),
        "device_identifier": serial,
        "name": name,
        "sw_release": "master",
        "sw_version": "1.0.0",
        "model_name": "Test model",
        "product_id": "TEST-1",
        "location": None,
        "mode": 0,
        "flow_mode": 1,
        "is_online": True,
        "last_seen_at": "2026-01-01T12:00:00.000Z",
        "port_state": 0,
        "current_quick_test": 0.1,
        "current_flow_duration": 10,
        "current_tightness_test": 3600,
        "rssi": -60,
        "current_alarm": None,
        "configurations": [],
        "total_flow_volume": 1000,
    }
    data.update(overrides)
    return data


def ws_message(operation: str, serial: str, **data: Any) -> dict[str, Any]:
    """Return a websocket message in the ActionCable format the server uses."""
    return {
        "identifier": '{"channel":"BroadcastChannel","user_id":1}',
        "message": {"operation": operation, "device": serial, "data": {"device_id": serial, **data}},
    }


def device_updated_message(serial: str, device_id: int, **data: Any) -> dict[str, Any]:
    """A device_updated message as seen live: the serial is only in message["device"]."""
    return {
        "identifier": '{"channel":"BroadcastChannel","user_id":1}',
        "message": {"operation": "device_updated", "device": serial, "data": {"id": device_id, **data}},
    }


class MockLeakomatic:
    """Holds the patched client and the websocket callback it was given."""

    def __init__(self, devices: dict[str, dict[str, Any]]) -> None:
        self.devices = devices
        self.client = MagicMock()
        self.ws_callback: Callable[[dict], None] | None = None
        self.ws_task_cancelled = False

        client = self.client
        client.device_ids = list(devices)
        client.device_id = next(iter(devices))
        client.error_code = None
        client.async_authenticate = AsyncMock(return_value=True)
        client.async_get_device_data = AsyncMock(side_effect=self._device_data)
        client.async_get_websocket_token = AsyncMock(return_value="ws-token")
        client.connect_to_websocket = AsyncMock(side_effect=self._connect)
        client.stop_websocket = AsyncMock()
        client.async_change_mode = AsyncMock(return_value=True)
        client.async_reset_alarms = AsyncMock(return_value=True)

    async def _device_data(self, device_id: str | None = None) -> dict[str, Any]:
        # Mirrors LeakomaticClient: one device -> its data, several -> keyed by ID.
        if device_id is not None:
            return self.devices[device_id]
        if len(self.devices) == 1:
            return next(iter(self.devices.values()))
        return dict(self.devices)

    async def _connect(self, callback: Callable[[dict], None]) -> None:
        # Like the real client, keep running until the task is cancelled.
        self.ws_callback = callback
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.ws_task_cancelled = True
            raise

    def send(self, message: dict[str, Any]) -> None:
        """Deliver a websocket message the way the client would."""
        assert self.ws_callback is not None, "websocket was never started"
        self.ws_callback(message)


@pytest.fixture
def entity_registry_enabled_by_default():
    """Create entities that are disabled by default as enabled (same as in HA core's tests)."""
    with patch(
        "homeassistant.helpers.entity.Entity.entity_registry_enabled_default",
        return_value=True,
        new_callable=PropertyMock,
    ):
        yield


@pytest.fixture
def devices() -> dict[str, dict[str, Any]]:
    """One device, overridable per test."""
    return {"1001": make_device_data("1001", "SERIAL-A")}


@pytest.fixture
def mock_leakomatic(devices: dict[str, dict[str, Any]]):
    """Patch LeakomaticClient where the integration creates it."""
    mock = MockLeakomatic(devices)
    with patch("custom_components.leakomatic.LeakomaticClient", return_value=mock.client):
        yield mock


@pytest.fixture
def config_entry() -> MockConfigEntry:
    """Return a config entry like the one the config flow creates."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Leakomatic Device 1001",
        data={"email": EMAIL, "password": PASSWORD, "device_id": "1001"},
    )


@pytest.fixture
async def setup_integration(hass: HomeAssistant, config_entry: MockConfigEntry, mock_leakomatic: MockLeakomatic) -> MockLeakomatic:
    """Set up the integration and wait until the websocket task has started."""
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    return mock_leakomatic
