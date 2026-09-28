"""HA-212: diagnostics with personal data redacted."""
from __future__ import annotations

import json

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.components.diagnostics import (
    get_diagnostics_for_config_entry,
    get_diagnostics_for_device,
)

from .conftest import EMAIL, PASSWORD, USER_ID, MockLeakomatic, make_device_data

# Quoted, so the password "secret" does not match the key name "registration_secret"
SECRET_VALUES = [json.dumps(v) for v in ("SERIAL-A", "10.0.0.42", "Secret street 1", "4711", "reg-secret", "Customer AB", EMAIL, PASSWORD)]

DEVICE = make_device_data(
    "1001",
    "SERIAL-A",
    ip_address="10.0.0.42",
    location="Secret street 1",
    pin_code="4711",
    registration_secret="reg-secret",
    customer_name="Customer AB",
    active_alarms=[{"alarm_id": 7, "alarm_type": 0, "level": 1, "is_active": True, "device_identifier": "SERIAL-A"}],
    alarms=[{"alarm_id": 1, "device_identifier": "SERIAL-A"}] * 3,
    events=[{"content": '{"device_id":"SERIAL-A","ip_address":"10.0.0.42"}'}],
)

pytestmark = pytest.mark.parametrize("devices", [{"1001": DEVICE}])


@pytest.fixture
async def diagnostics_ready(hass: HomeAssistant, setup_integration: MockLeakomatic) -> MockLeakomatic:
    assert await async_setup_component(hass, "diagnostics", {})
    return setup_integration


async def test_config_entry_diagnostics(
    hass: HomeAssistant, hass_client, config_entry: MockConfigEntry, diagnostics_ready: MockLeakomatic
) -> None:
    result = await get_diagnostics_for_config_entry(hass, hass_client, config_entry)

    text = json.dumps(result)
    for secret in [*SECRET_VALUES, json.dumps(USER_ID)]:
        assert secret not in text, secret

    device = result["devices"]["1001"]
    assert device["mode"] == 0
    assert device["active_alarms"][0]["level"] == 1  # the current alarms are kept
    assert "alarms" not in device and "events" not in device  # the history is left out...
    assert (device["alarms_count"], device["events_count"]) == (3, 1)  # ...but counted
    assert result["connection"] == {"logged_in": True, "websocket_connected": True}
    assert result["availability"]["available"] is True


async def test_device_diagnostics(
    hass: HomeAssistant, hass_client, config_entry: MockConfigEntry, diagnostics_ready: MockLeakomatic
) -> None:
    [device] = dr.async_entries_for_config_entry(dr.async_get(hass), config_entry.entry_id)

    result = await get_diagnostics_for_device(hass, hass_client, config_entry, device)

    text = json.dumps(result)
    for secret in SECRET_VALUES:
        assert secret not in text, secret
    assert result["device"]["rssi"] == -60
