"""The entities as Home Assistant sees them: units, classes and states."""
from __future__ import annotations

import pytest
from homeassistant.core import HomeAssistant

from .conftest import MockLeakomatic, make_device_data

UNITS = {
    "sensor.leakomatic_last_flow_duration": "s",
    "sensor.leakomatic_longest_tightness_period": "s",
    "sensor.leakomatic_signal_strength": "dBm",
    "sensor.leakomatic_temperature": "°C",
    "sensor.leakomatic_pressure": "bar",
    "sensor.leakomatic_total_volume": "m³",
}


@pytest.mark.usefixtures("entity_registry_enabled_by_default")
async def test_units(hass: HomeAssistant, setup_integration: MockLeakomatic) -> None:
    """HA-204: the unit constants give the same units as the old strings."""
    for entity_id, unit in UNITS.items():
        assert hass.states.get(entity_id).attributes["unit_of_measurement"] == unit, entity_id


async def test_disabled_by_default(hass: HomeAssistant, setup_integration: MockLeakomatic) -> None:
    """Sensors that need accessories (analog sensor, water meter) are disabled by default."""
    from homeassistant.helpers import entity_registry as er

    registry = er.async_get(hass)
    disabled = {
        entry.unique_id.split("_", 1)[1]
        for entry in registry.entities.values()
        if entry.platform == "leakomatic" and entry.disabled_by is not None
    }
    assert disabled == {"temperature", "pressure", "total_volume"}


@pytest.mark.usefixtures("entity_registry_enabled_by_default")
@pytest.mark.parametrize(
    "devices",
    [{"1001": make_device_data("1001", "SERIAL-A", last_temperature_value="-", last_pressure_value="-")}],
)
async def test_no_reading_is_unknown_without_warning(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture, setup_integration: MockLeakomatic
) -> None:
    """Leakomatic sends "-" when no analog sensor is connected: unknown, and no "Invalid value" warning."""
    assert hass.states.get("sensor.leakomatic_temperature").state == "unknown"
    assert hass.states.get("sensor.leakomatic_pressure").state == "unknown"
    # The sensors are created during the fixture's setup phase
    messages = [r.getMessage() for r in caplog.get_records("setup") + caplog.records]
    assert not [m for m in messages if "Invalid value" in m]
