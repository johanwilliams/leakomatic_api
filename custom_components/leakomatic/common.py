"""Common functionality shared between Leakomatic sensor types.

This module contains shared code used by both sensor and binary_sensor platforms.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Optional, TypeVar, Generic, Type, Union

from homeassistant.helpers.entity import DeviceInfo

_LOGGER = logging.getLogger(__name__)

# Type variable for the entity type
T = TypeVar('T')

def log_with_entity(logger: logging.Logger, level: int, entity: Any, message: str, *args: Any) -> None:
    """Log a message with device and entity names.
    
    Args:
        logger: The logger instance to use
        level: The logging level (e.g. logging.INFO, logging.WARNING)
        entity: The entity instance that has device_info and name attributes
        message: The message to log
        *args: Additional arguments to format the message with
    """
    device_name = entity.device_info.get("name", "Unknown Device")
    entity_name = getattr(entity, "name", "Unknown Entity")
    formatted_message = f"{device_name} {entity_name} - {message}"
    logger.log(level, formatted_message, *args)

class LeakomaticMessageHandler:
    """Common message handler for Leakomatic entities.
    
    This class contains the shared message handling logic used by both binary sensors
    and regular sensors. It provides methods to handle different types of messages
    and update the appropriate entities.
    """
    
    @staticmethod
    def _update_matching_entities(
        message: dict,
        entities: list[T],
        sensor_type: Type[T] | tuple[Type[T], ...] | None,
        online_sensor_type: Type[T] | None,
        update_data: dict[str, Any] | None = None,
        update_last_seen: bool = True
    ) -> None:
        """Helper method to update entities that match the device identifier.
        
        Args:
            message: The message containing the update
            entities: List of entities to check
            sensor_type: Type of sensor to update (can be a single type or tuple of types)
            online_sensor_type: Type of online sensor to update
            update_data: Data to pass to handle_update. If None, uses message data
            update_last_seen: Whether to update last_seen for online status
        """
        data = message.get("message", {}).get("data", {})
        message_device_identifier = data.get("device_id")
        
        for entity in entities:
            entity_device_identifier = entity.device_info.get("serial_number")
            
            # Only update if device identifiers match
            if message_device_identifier != entity_device_identifier:
                continue
                
            if sensor_type is not None and isinstance(entity, sensor_type):
                entity.handle_update(update_data or data)
            if online_sensor_type is not None and isinstance(entity, online_sensor_type):
                entity.handle_update({"is_online": True}, update_last_seen=update_last_seen)
    
    @staticmethod
    def handle_flow_update(message: dict, entities: list[T], flow_sensor_type: Type[T] | None, online_sensor_type: Type[T] | None) -> None:
        """Handle flow_updated messages."""
        LeakomaticMessageHandler._update_matching_entities(
            message, entities, flow_sensor_type, online_sensor_type
        )

    @staticmethod
    def handle_device_update(message: dict, entities: list[T], flow_sensor_type: Type[T] | None, online_sensor_type: Type[T] | None) -> None:
        """Handle device_updated messages."""
        LeakomaticMessageHandler._update_matching_entities(
            message, entities, flow_sensor_type, online_sensor_type
        )

    @staticmethod
    def handle_quick_test_update(message: dict, entities: list[T], quick_test_sensor_type: Type[T] | None, online_sensor_type: Type[T] | None) -> None:
        """Handle quick_test_updated messages."""
        data = message.get("message", {}).get("data", {})
        value = data.get("value")
        LeakomaticMessageHandler._update_matching_entities(
            message, entities, quick_test_sensor_type, online_sensor_type,
            update_data={"value": value}
        )

    @staticmethod
    def handle_tightness_test_update(message: dict, entities: list[T], tightness_sensor_type: Type[T] | None, online_sensor_type: Type[T] | None) -> None:
        """Handle tightness_test_updated messages."""
        data = message.get("message", {}).get("data", {})
        value = data.get("value")
        LeakomaticMessageHandler._update_matching_entities(
            message, entities, tightness_sensor_type, online_sensor_type,
            update_data={"value": value}
        )

    @staticmethod
    def handle_status_update(message: dict, entities: list[T], status_sensor_type: Type[T] | None, online_sensor_type: Type[T] | None) -> None:
        """Handle status_message messages."""
        LeakomaticMessageHandler._update_matching_entities(
            message, entities, status_sensor_type, online_sensor_type
        )

    @staticmethod
    def handle_ping(message: dict, entities: list[T], online_sensor_type: Type[T] | None) -> None:
        """Handle ping messages."""
        # Do nothing for ping messages, as they cannot be tied to a specific device and logging would flood the logs
        #TODO: Consider adding logic to reconnect to the websocket if no ping is received for a while

    @staticmethod
    def handle_device_offline(message: dict, entities: list[T], online_sensor_type: Type[T] | None) -> None:
        """Handle device_offline messages."""
        _LOGGER.debug("Received device_offline message")
        LeakomaticMessageHandler._update_matching_entities(
            message, entities, None, online_sensor_type,
            update_data={"is_online": False},
            update_last_seen=False
        )

    @staticmethod
    def handle_alarm_triggered(message: dict, entities: list[T], alarm_sensor_types: tuple[Type[T], ...] | None, online_sensor_type: Type[T] | None) -> None:
        """Handle alarm_triggered messages."""
        LeakomaticMessageHandler._update_matching_entities(
            message, entities, alarm_sensor_types, online_sensor_type
        )

    @staticmethod
    def handle_default(message: dict, entities: list[T]) -> None:
        """Handle any other message type."""
        msg_type = message.get("type", message.get('message', {}).get('operation', 'unknown'))
        _LOGGER.debug("%s: Received unhandled message type: %s", self._device_id, msg_type)

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
            _LOGGER.warning("%s: No handler found for message type: %s", self._device_id, msg_type)

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
        _LOGGER.debug("%s: value updated", self._device_id) 