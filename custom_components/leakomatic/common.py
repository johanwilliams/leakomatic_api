"""Common functionality shared between Leakomatic sensor types.

This module contains shared code used by both sensor and binary_sensor platforms.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Optional, TypeVar, Generic

from homeassistant.helpers.entity import DeviceInfo

_LOGGER = logging.getLogger(__name__)

# Type variable for the entity type
T = TypeVar('T')

class MessageHandlerRegistry(Generic[T]):
    """Registry for WebSocket message handlers."""
    
    def __init__(self) -> None:
        """Initialize the registry."""
        self._handlers: Dict[str, Callable[[dict, list[T]], None]] = {}
        self._default_handler: Optional[Callable[[dict, list[T]], None]] = None
        self._registered_types: set[str] = set()  # Track which message types we care about
    
    def register(self, message_type: str, handler: Callable[[dict, list[T]], None]) -> None:
        """Register a handler for a specific message type."""
        self._handlers[message_type] = handler
        self._registered_types.add(message_type)  # Add to set of types we care about
    
    def register_default(self, handler: Callable[[dict, list[T]], None]) -> None:
        """Register a default handler for unhandled message types."""
        self._default_handler = handler
    
    def handle_message(self, message: dict, entities: list[T]) -> None:
        """Handle a WebSocket message using the appropriate handler."""
        # Extract message type using the same logic as legacy code
        msg_type = ""
        
        # First try to get the type from the message's operation
        if 'message' in message and 'operation' in message['message']:
            msg_type = message['message']['operation']
        # Then try the type field
        elif 'type' in message:
            msg_type = message['type']
        
        # Get the appropriate handler
        handler = self._handlers.get(msg_type)
        if handler is None:
            handler = self._default_handler
        
        if handler is not None:
            handler(message, entities)
        elif msg_type in self._registered_types:
            # Only log a warning if this is a message type we care about
            _LOGGER.warning("No handler found for message type: %s", msg_type)

class LeakomaticEntity:
    """Base class for all Leakomatic entities.
    
    This class implements common functionality shared between all Leakomatic entities.
    """

    def __init__(
        self,
        device_info: dict[str, Any],
        device_id: str,
        device_data: dict[str, Any] | None,
        *,
        key: str,
        icon: str,
    ) -> None:
        """Initialize the entity."""
        self._device_info = device_info
        self._device_id = device_id
        self._device_data = device_data or {}
        
        self._attr_has_entity_name = True
        self._attr_unique_id = f"{device_id}_{key}"
        self._attr_icon = icon
        self._attr_entity_registry_enabled_default = True
        self._attr_should_poll = False  # No polling needed with WebSocket
        self._attr_translation_key = key

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device info."""
        return self._device_info

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        return {}

    def handle_update(self, data: dict[str, Any]) -> None:
        """Handle updated data from WebSocket."""
        self._device_data = data
        self.async_write_ha_state()
        _LOGGER.debug("%s value updated", self.name) 