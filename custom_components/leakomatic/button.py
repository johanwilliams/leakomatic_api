"""Support for Leakomatic buttons.

This module implements the button platform for the Leakomatic integration.
It provides buttons for:
- Resetting alarms
"""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import EntityCategory

from .const import DOMAIN
from .common import LeakomaticEntity, log_with_entity

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
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Leakomatic button.
    
    This function:
    1. Gets the device information from the config entry
    2. Creates and adds the button entities
    
    Args:
        hass: The Home Assistant instance
        config_entry: The config entry to set up buttons for
        async_add_entities: Callback to register new entities
    """
    _LOGGER.debug("Setting up Leakomatic button for config entry: %s", config_entry.entry_id)
    
    # Get the device ID and device entry from hass.data
    domain_data = hass.data.get(DOMAIN, {}).get(config_entry.entry_id, {})
    device_id = domain_data.get("device_id")
    device_entry = domain_data.get("device_entry")
    client = domain_data.get("client")
    
    if not device_id or not device_entry or not client:
        _LOGGER.error("Missing device ID, device entry, or client")
        return
    
    # Create device info dictionary using the device entry's information
    device_info = {
        "identifiers": {(DOMAIN, device_id)},
        "name": device_entry.name,
        "manufacturer": device_entry.manufacturer,
        "model": device_entry.model,
        "sw_version": device_entry.sw_version,
    }
    
    # Create buttons
    buttons = [
        ResetAlarmsButton(device_info, device_id, client),
    ]
    
    async_add_entities(buttons)

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
        success = await self._client.async_reset_alarms()
        if success:
            log_with_entity(_LOGGER, logging.INFO, self, "Successfully reset all alarms")
        else:
            log_with_entity(_LOGGER, logging.ERROR, self, "Failed to reset alarms") 