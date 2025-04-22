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
    
    # Create device info dictionary
    device_info = {
        "identifiers": {(DOMAIN, device_id)},
        "name": f"{DEFAULT_NAME} {device_id}",
        "manufacturer": "Leakomatic",
        "model": "Water Leak Sensor",
        "sw_version": "1.0.0",
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
        self._attr_name = f"{DEFAULT_NAME} {device_id}"
        self._attr_unique_id = f"{device_id}_status"
        self._attr_device_class = SensorDeviceClass.MOISTURE
        self._attr_native_unit_of_measurement = "%"
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_icon = "mdi:water"
        self._attr_entity_registry_enabled_default = True
        self._attr_should_poll = True

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device info."""
        return self._device_info

    @property
    def native_value(self) -> StateType:
        """Return the state of the sensor."""
        if not self.coordinator.data:
            return None
        
        # For now, just return a dummy value
        # In a real implementation, you would extract the actual moisture level from the device data
        return 0.0

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        if not self.coordinator.data:
            return {}
        
        # Return the raw device data as attributes
        return self.coordinator.data 