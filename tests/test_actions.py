"""HA-271: a failed mode change or alarm reset is reported to the caller."""
from __future__ import annotations

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .conftest import MockLeakomatic

MODE = "select.leakomatic_mode"
RESET = "button.leakomatic_reset_alarms"


async def _select(hass: HomeAssistant, option: str) -> None:
    await hass.services.async_call(
        "select", "select_option", {"entity_id": MODE, "option": option}, blocking=True
    )


async def _press(hass: HomeAssistant) -> None:
    await hass.services.async_call("button", "press", {"entity_id": RESET}, blocking=True)


async def test_select_option_succeeds(hass: HomeAssistant, setup_integration: MockLeakomatic) -> None:
    await _select(hass, "pause")

    setup_integration.client.async_change_mode.assert_awaited_once_with("pause", "1001")


async def test_failed_mode_change_raises(hass: HomeAssistant, setup_integration: MockLeakomatic) -> None:
    setup_integration.client.async_change_mode.return_value = False

    with pytest.raises(HomeAssistantError) as err:
        await _select(hass, "away")

    assert err.value.translation_key == "change_mode_failed"
    assert err.value.translation_placeholders == {"mode": "away"}


async def test_press_succeeds(hass: HomeAssistant, setup_integration: MockLeakomatic) -> None:
    await _press(hass)

    setup_integration.client.async_reset_alarms.assert_awaited_once_with("1001")


async def test_failed_alarm_reset_raises(hass: HomeAssistant, setup_integration: MockLeakomatic) -> None:
    setup_integration.client.async_reset_alarms.return_value = False

    with pytest.raises(HomeAssistantError) as err:
        await _press(hass)

    assert err.value.translation_key == "reset_alarms_failed"
