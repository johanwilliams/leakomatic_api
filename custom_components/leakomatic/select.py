"""Support for Leakomatic select entities.

This module implements the select platform for the Leakomatic integration.
It provides select entities for:
- Device mode (Home/Away/Pause)
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Optional

from homeassistant.components.select import (
    SelectEntity,
    SelectEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import EntityCategory

from .const import DOMAIN, MessageType, DeviceMode
from .common import LeakomaticEntity, MessageHandlerRegistry

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
def handle_device_update(message: dict, selects: list[LeakomaticSelect]) -> None:
    """Handle device_updated messages."""
    data = message.get("message", {}).get("data", {})
    _LOGGER.debug("Received device update - Mode: %s", data.get("mode"))
    # Update all relevant select entities
    for select in selects:
        if isinstance(select, ModeSelect):
            select.handle_update(data)

# Register all handlers
message_registry.register(MessageType.DEVICE_UPDATED.value, handle_device_update)

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Leakomatic select entity.
    
    This function:
    1. Gets the device information from the config entry
    2. Creates and adds the select entities
    
    Args:
        hass: The Home Assistant instance
        config_entry: The config entry to set up select entities for
        async_add_entities: Callback to register new entities
    """
    _LOGGER.debug("Setting up Leakomatic select entity for config entry: %s", config_entry.entry_id)
    
    # Get the client and device ID from hass.data
    domain_data = hass.data.get(DOMAIN, {}).get(config_entry.entry_id, {})
    client = domain_data.get("client")
    device_id = domain_data.get("device_id")
    device_entry = domain_data.get("device_entry")
    
    if not client or not device_id or not device_entry:
        _LOGGER.error("Missing client, device ID, or device entry")
        return
    
    # Create device info dictionary using the device entry's information
    device_info = {
        "identifiers": {(DOMAIN, device_id)},
        "name": device_entry.name,
        "manufacturer": device_entry.manufacturer,
        "model": device_entry.model,
        "sw_version": device_entry.sw_version,
    }
    
    # Get initial device data
    device_data = await client.async_get_device_data()
    
    # Create select entities
    select_entities = [
        ModeSelect(device_info, device_id, device_data, client),
    ]
    
    async_add_entities(select_entities)

    # Register callback for WebSocket updates
    @callback
    def handle_ws_message(message: dict) -> None:
        """Handle WebSocket messages."""
        message_registry.handle_message(message, select_entities)

    # Store the callback in hass.data for the WebSocket client to use
    if "ws_callbacks" not in domain_data:
        domain_data["ws_callbacks"] = []
    domain_data["ws_callbacks"].append(handle_ws_message)


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
        _LOGGER.debug("Changing mode to %s", option)
        success = await self._client.async_change_mode(option)
        if not success:
            _LOGGER.error("Failed to change mode to %s", option)

    @callback
    def handle_update(self, data: dict[str, Any]) -> None:
        """Handle updated data from WebSocket."""
        mode = data.get("mode")
        if mode is not None:
            mode_str = "home" if mode == 0 else "away" if mode == 1 else "pause" if mode == 2 else str(mode)
            _LOGGER.debug("Mode changed to %s", mode_str)
        self._device_data = data
        self.async_write_ha_state() 