"""Support for Leakomatic select entities.

This module implements the select platform for the Leakomatic integration.
It provides select entities for:
- Device mode (Home/Away/Pause)
"""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.select import (
    SelectEntity,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.const import EntityCategory

from .const import DOMAIN, MessageType
from .common import LeakomaticEntity, LeakomaticMessageHandler, MessageHandlerRegistry, log_with_entity
from .models import LeakomaticConfigEntry

_LOGGER = logging.getLogger(__name__)

class LeakomaticSelect(LeakomaticEntity, SelectEntity):
    """Base class for all Leakomatic select entities.
    
    This class implements common functionality shared between all Leakomatic select entities.
    """

    def __init__(
        self,
        device_info: dict[str, Any],
        device_id: str,
        device_data: dict[str, Any] | None,
        *,
        key: str,
        icon: str,
        options: list[str],
        entity_category: EntityCategory | None = None,
    ) -> None:
        """Initialize the select entity."""
        super().__init__(
            device_info=device_info,
            device_id=device_id,
            device_data=device_data,
            key=key,
            icon=icon,
        )
        self._attr_options = options
        self._attr_entity_category = entity_category

# Create a global registry instance
message_registry = MessageHandlerRegistry[LeakomaticSelect]()

# Define message handlers
def handle_device_update(message: dict, sensors: list[LeakomaticSelect]) -> None:
    """Handle device_updated messages."""
    LeakomaticMessageHandler.update_matching_entities(message, sensors, ModeSelect, None)

# Register all handlers
message_registry.register(MessageType.DEVICE_UPDATED.value, handle_device_update)

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: LeakomaticConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Leakomatic select entity.
    
    This function:
    1. Gets the device information from the config entry
    2. Creates and adds the select entities for each device
    
    Args:
        hass: The Home Assistant instance
        config_entry: The config entry to set up select entities for
        async_add_entities: Callback to register new entities
    """
    _LOGGER.debug("Setting up Leakomatic select entities for config entry: %s", config_entry.entry_id)
    data = config_entry.runtime_data
    client = data.client

    # Create select entities for each device
    all_select_entities = []
    for device_id, device_info in data.device_infos.items():
        dev_data = data.device_data[device_id]

        # Create select entities for this device
        device_select_entities = [
            ModeSelect(device_info, device_id, dev_data, client),
        ]
        all_select_entities.extend(device_select_entities)
    
    async_add_entities(all_select_entities)

    # Register callback for WebSocket updates
    @callback
    def handle_ws_message(message: dict) -> None:
        """Handle WebSocket messages."""
        message_registry.handle_message(message, all_select_entities)

    config_entry.async_on_unload(data.async_add_ws_listener(handle_ws_message))


class ModeSelect(LeakomaticSelect):
    """Representation of a Leakomatic Mode select entity.
    
    This select entity allows changing the mode of the Leakomatic device (Home/Away/Pause).
    It is updated through WebSocket updates and can be used to change the mode.
    
    Attributes:
        _device_info: Information about the physical device
        _device_id: The unique identifier of the device
        _attr_name: The name of the select entity
        _attr_unique_id: The unique identifier for this select entity
        _attr_icon: The icon to use for this select entity
        _device_data: The current device data
        _client: The Leakomatic client instance
    """

    def __init__(
        self,
        device_info: dict[str, Any],
        device_id: str,
        device_data: dict[str, Any] | None,
        client: Any,
    ) -> None:
        """Initialize the mode select entity."""
        super().__init__(
            device_info=device_info,
            device_id=device_id,
            device_data=device_data,
            key="mode",
            icon="mdi:home",
            options=["home", "away", "pause"],
            entity_category=EntityCategory.CONFIG,
        )
        self._client = client

    @property
    def current_option(self) -> str | None:
        """Return the current selected option."""
        if not self._device_data:
            return None
        
        # Get the mode from the device data
        mode = self._device_data.get("mode")
        
        # Convert numeric mode to string option
        if mode == 0:
            return "home"
        elif mode == 1:
            return "away"
        elif mode == 2:
            return "pause"
        else:
            return None

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        log_with_entity(_LOGGER, logging.DEBUG, self, "Changing mode to %s", option)
        success = await self._client.async_change_mode(option, self._device_id)
        if not success:
            # The client has logged why. Tell the caller (UI, automation, script).
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="change_mode_failed",
                translation_placeholders={"mode": option},
            )

    @callback
    def handle_update(self, data: dict[str, Any]) -> None:
        """Handle updated data from WebSocket."""
        mode = data.get("mode")
        if mode is not None:
            mode_str = "home" if mode == 0 else "away" if mode == 1 else "pause" if mode == 2 else str(mode)
            log_with_entity(_LOGGER, logging.DEBUG, self, "Changing mode to %s", mode_str)
        self._device_data = data
        self.async_write_ha_state() 