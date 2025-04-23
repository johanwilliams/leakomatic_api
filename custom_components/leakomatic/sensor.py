"""Support for Leakomatic sensors."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Optional

from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from .const import DOMAIN, DEFAULT_NAME, DEFAULT_SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Leakomatic sensor."""
    _LOGGER.debug("Setting up Leakomatic sensor for config entry: %s", config_entry.entry_id)
    
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
    
    # Create a coordinator to fetch data
    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=f"{DEFAULT_NAME} {device_id}",
        update_method=client.async_get_device_data,
        update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
    )
    
    # Add the sensor
    async_add_entities([LeakomaticSensor(coordinator, device_info, device_id)])


class LeakomaticSensor(CoordinatorEntity, SensorEntity):
    """Representation of a Leakomatic sensor."""

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        device_info: dict[str, Any],
        device_id: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._device_info = device_info
        self._device_id = device_id
        self._attr_name = f"{DEFAULT_NAME} Mode"
        self._attr_unique_id = f"{device_id}_mode"
        self._attr_device_class = None  # No specific device class for mode
        self._attr_native_unit_of_measurement = None  # No unit for mode
        self._attr_state_class = None  # No state class for mode
        self._attr_icon = "mdi:home"  # Icon for mode
        self._attr_entity_registry_enabled_default = True
        self._attr_should_poll = True
        self._attr_translation_key = "mode"  # This tells Home Assistant to use the translation system

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device info."""
        # Update sw_version if coordinator data is available
        if self.coordinator.data and "sw_version" in self.coordinator.data:
            self._device_info["sw_version"] = self.coordinator.data["sw_version"]
        
        return self._device_info

    @property
    def native_value(self) -> StateType:
        """Return the state of the sensor."""
        if not self.coordinator.data:
            _LOGGER.debug("No coordinator data available")
            return None
        
        # Get the mode from the device data
        mode = self.coordinator.data.get("mode")
        _LOGGER.debug("Mode value from device data: %s", mode)
        
        # Return the numeric value directly
        if mode in (0, 1, 2):
            return mode
        else:
            _LOGGER.debug("Unknown mode value: %s", mode)
            return "unknown"  # Return "unknown" as a string to match the translation key

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        if not self.coordinator.data:
            return {}
        
        # Extract relevant attributes from the device data
        attributes = {}
        
        # Add alarm status
        if "alarm" in self.coordinator.data:
            attributes["alarm"] = self.coordinator.data["alarm"]
        
        # Add device name
        if "name" in self.coordinator.data:
            attributes["name"] = self.coordinator.data["name"]
        
        # Add device model
        if "model" in self.coordinator.data:
            attributes["model"] = self.coordinator.data["model"]
        
        # Add software version
        if "sw_version" in self.coordinator.data:
            attributes["sw_version"] = self.coordinator.data["sw_version"]
        
        # Add last seen time
        if "last_seen_at" in self.coordinator.data:
            attributes["last_seen_at"] = self.coordinator.data["last_seen_at"]
        
        return attributes 