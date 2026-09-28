"""HA-203: every entity's state and attributes, step by step, compared with a saved snapshot.

The snapshot was recorded before the entity refactoring, so a refactoring
that changes anything a user can see fails here. To record it again after
an intended change: LEAKOMATIC_UPDATE_SNAPSHOT=1 python -m pytest tests/test_entity_snapshot.py
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from homeassistant.core import HomeAssistant

from .conftest import MockLeakomatic, device_updated_message, make_device_data, ws_message

SNAPSHOT = Path(__file__).parent / "snapshots" / "entities.json"

CONFIG = {"id": 1, "time": "2026-01-01T00:00:00.000Z", "ft_alarm_away": 5, "ft_warning_home": 20,
          "ft_alarm_delay": 5, "qt_alarm_delay": 1, "qt_index_limit": 1.0, "tt_count": 1,
          "tt_length": 15, "tt_alarm_delay": 1}
DEVICE = make_device_data(
    "1001", "SERIAL-A",
    mode=2, mode_stoptime=1_893_456_000, current_quick_test=0.123, current_flow_duration=42,
    current_tightness_test=3600, rssi=-61, port_state=0, total_flow_volume="1.250",
    last_temperature_value=7.25, last_pressure_value=3.14, configurations=[CONFIG],
    active_alarms=[{"alarm_id": 1, "alarm_type": 1, "level": 1, "is_active": True}],
)


def _alarm(alarm_type: str, level: str) -> dict:
    message = ws_message("alarm_triggered", "SERIAL-A", alarm_type=alarm_type, alarm_level=level)
    message["message"]["data"]["operation"] = "alarm_triggered"
    return message


STEPS = [
    ("startup", None),
    ("quick test", ws_message("quick_test_updated", "SERIAL-A", value=0.456)),
    ("tightness", ws_message("tightness_test_updated", "SERIAL-A", value=1800.9)),
    ("flow start", ws_message("flow_updated", "SERIAL-A", flow_mode=1, flow_duration=0)),
    ("flow end", ws_message("flow_updated", "SERIAL-A", flow_mode=0, flow_duration=17, total_volume=1300)),
    ("status", ws_message("status_message", "SERIAL-A", port_state=128, rssi=-70, mode_stoptime=1_893_459_600)),
    ("temperature", ws_message("analog_sensor_message", "SERIAL-A", sensor_type=2, port=5, value=8.46, connected=1)),
    ("pressure", ws_message("analog_sensor_message", "SERIAL-A", sensor_type=1, port=5, value=4.23, connected=1)),
    ("flow alarm", _alarm("0", "2")),
    ("home", device_updated_message("SERIAL-A", 1001, mode=0, active_alarms=[], total_flow_volume="1.400")),
    ("invalid values", ws_message("quick_test_updated", "SERIAL-A", value="n/a")),
    ("offline", ws_message("device_offline", "SERIAL-A")),
]


def _entities(hass: HomeAssistant) -> dict:
    return {
        state.entity_id: {"state": state.state, "attributes": dict(sorted(state.attributes.items()))}
        for state in sorted(hass.states.async_all(), key=lambda s: s.entity_id)
        if state.entity_id.split(".")[1].startswith("leakomatic_")
    }


@pytest.mark.usefixtures("entity_registry_enabled_by_default")
@pytest.mark.parametrize("devices", [{"1001": DEVICE}])
@pytest.mark.freeze_time("2026-09-28 12:00:00+00:00")
async def test_entities_match_snapshot(hass: HomeAssistant, setup_integration: MockLeakomatic) -> None:
    recorded = {}
    for name, message in STEPS:
        if message is not None:
            setup_integration.send(message)
        await hass.async_block_till_done()
        recorded[name] = _entities(hass)
    recorded = json.loads(json.dumps(recorded, default=str))

    if os.environ.get("LEAKOMATIC_UPDATE_SNAPSHOT"):
        SNAPSHOT.write_text(json.dumps(recorded, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        pytest.skip("snapshot recorded")

    expected = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    for name, _ in STEPS:
        assert recorded[name] == expected[name], name
