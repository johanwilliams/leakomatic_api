"""Support for Leakomatic buttons.

This module implements the button platform for the Leakomatic integration.
It provides buttons for:
- Resetting alarms
"""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import EntityCategory

from .common import LeakomaticEntity, log_with_entity
from .const import DOMAIN
from .models import LeakomaticConfigEntry

_LOGGER = logging.getLogger(__name__)

class LeakomaticButton(LeakomaticEntity, ButtonEntity):
    """Base class for all Leakomatic buttons.
    
    This class implements common functionality shared between all Leakomatic buttons.
    """

    def __init__(
        self,
        device_info: dict[str, Any],
        device_id: str,
        *,
        key: str,
        icon: str,
        entity_category: EntityCategory | None = None,
    ) -> None:
        """Initialize the button."""
        super().__init__(
            device_info=device_info,
            device_id=device_id,
            device_data=None,
            key=key,
            icon=icon,
        )
        self._attr_entity_category = entity_category

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: LeakomaticConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Leakomatic button.
    
    This function:
    1. Gets the device information from the config entry
    2. Creates and adds the button entities for each device
    
    Args:
        hass: The Home Assistant instance
        config_entry: The config entry to set up buttons for
        async_add_entities: Callback to register new entities
    """
    _LOGGER.debug("Setting up Leakomatic buttons for config entry: %s", config_entry.entry_id)
    
    data = config_entry.runtime_data
    client = data.client

    # Create buttons for each device
    all_buttons = []
    for device_id, device_info in data.device_infos.items():
        # Create buttons for this device
        device_buttons = [
            ResetAlarmsButton(device_info, device_id, client),
        ]
        all_buttons.extend(device_buttons)
    
    async_add_entities(all_buttons)

class ResetAlarmsButton(LeakomaticButton):
    """Representation of a Leakomatic Reset Alarms button.
    
    This button allows resetting all active alarms on the Leakomatic device.
    """

    def __init__(
        self,
        device_info: dict[str, Any],
        device_id: str,
        client: Any,
    ) -> None:
        """Initialize the reset alarms button."""
        super().__init__(
            device_info=device_info,
            device_id=device_id,
            key="reset_alarms",
            icon="mdi:alarm-off",
            entity_category=EntityCategory.CONFIG,
        )
        self._client = client

    async def async_press(self) -> None:
        """Handle the button press."""
        success = await self._client.async_reset_alarms(self._device_id)
        if not success:
            # The client has logged why. Tell the caller (UI, automation, script).
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="reset_alarms_failed",
            )
        log_with_entity(_LOGGER, logging.INFO, self, "Successfully reset all alarms")