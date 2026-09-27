"""Runtime data for the Leakomatic integration."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo

from .leakomatic_client import LeakomaticClient

type LeakomaticConfigEntry = ConfigEntry[LeakomaticData]


@dataclass
class LeakomaticData:
    """Data stored in the config entry while it is loaded (entry.runtime_data).

    Attributes:
        client: The client for the Leakomatic cloud.
        device_infos: Device info per Leakomatic device ID, for the devices
            that were set up. The "serial_number" key is what websocket
            messages are matched against.
        device_data: The device data from the REST API at setup, per device ID.
            Entities use it for their initial state.
        ws_listeners: Callbacks that receive every websocket message.
    """

    client: LeakomaticClient
    device_infos: dict[str, DeviceInfo]
    device_data: dict[str, dict[str, Any]]
    ws_listeners: list[Callable[[dict], None]] = field(default_factory=list)

    @callback
    def async_add_ws_listener(self, listener: Callable[[dict], None]) -> Callable[[], None]:
        """Register a websocket message listener. Returns a function that removes it."""
        self.ws_listeners.append(listener)

        @callback
        def remove_listener() -> None:
            if listener in self.ws_listeners:
                self.ws_listeners.remove(listener)

        return remove_listener
