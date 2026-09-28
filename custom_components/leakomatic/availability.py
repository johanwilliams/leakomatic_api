"""Entity availability based on the websocket connection to Leakomatic."""
from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime

from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.event import async_call_later

from .const import UNAVAILABLE_AFTER_DISCONNECT

_LOGGER = logging.getLogger(__name__)


class ConnectionAvailability:
    """Tracks whether the entities' values can be trusted.

    The values come from websocket messages. While the websocket is down, they
    are stale. Entities are marked unavailable only when the connection has been
    down for UNAVAILABLE_AFTER_DISCONNECT seconds, so the server's scheduled
    disconnect (typically nightly, reconnected within seconds) is not visible.

    At setup the entities have fresh data from the REST API, so they start
    available and the same grace period applies to the first connection.
    """

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the tracker."""
        self._hass = hass
        self.available = True
        self._listeners: list[Callable[[], None]] = []
        self._unsub_timer: CALLBACK_TYPE | None = None

    @callback
    def async_add_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        """Call listener when availability changes. Returns a function that removes it."""
        self._listeners.append(listener)

        @callback
        def remove_listener() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)

        return remove_listener

    @callback
    def async_connectivity_changed(self, connected: bool, phase: int) -> None:
        """Handle a connectivity report from the client."""
        if connected:
            self._cancel_timer()
            if not self.available:
                _LOGGER.info("Connection to Leakomatic restored, entities are available again")
                self._set_available(True)
        elif self.available and self._unsub_timer is None:
            self._unsub_timer = async_call_later(
                self._hass, UNAVAILABLE_AFTER_DISCONNECT, self._async_grace_period_over
            )

    @callback
    def _async_grace_period_over(self, _now: datetime) -> None:
        self._unsub_timer = None
        _LOGGER.info(
            "No connection to Leakomatic for %d minutes, marking entities unavailable",
            UNAVAILABLE_AFTER_DISCONNECT // 60,
        )
        self._set_available(False)

    @callback
    def async_stop(self) -> None:
        """Stop the pending timer (on unload)."""
        self._cancel_timer()

    def _cancel_timer(self) -> None:
        if self._unsub_timer is not None:
            self._unsub_timer()
            self._unsub_timer = None

    def _set_available(self, available: bool) -> None:
        self.available = available
        for listener in list(self._listeners):
            listener()
