"""The entities as Home Assistant sees them: units, classes and states."""
from __future__ import annotations

import pytest
from homeassistant.core import HomeAssistant

from .conftest import MockLeakomatic

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
