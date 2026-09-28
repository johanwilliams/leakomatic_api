"""Diagnostics for the Leakomatic integration.

Download from Settings -> Devices & services -> Leakomatic (the whole account)
or from a device page (one device). Personal data is redacted; the alarm and
event history is left out, because its text fields embed serial numbers and
IP addresses that key-based redaction cannot reach.
"""
from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntry

from .const import DOMAIN
from .models import LeakomaticConfigEntry

REDACT = {
    CONF_EMAIL,
    CONF_PASSWORD,
    "unique_id",
    "user_id",
    "customer_id",
    "customer_name",
    "location_id",
    "location",
    "device_identifier",
    "serial_number",
    "device",
    "ip_address",
    "pin_code",
    "registration_secret",
    "internal_comments",
    "internal_reference",
    "customer_notes",
    "title",
}

# History lists that are left out (replaced by their length)
HISTORY_KEYS = ("alarms", "events")


def _device_diagnostics(entry: LeakomaticConfigEntry, device_id: str) -> dict[str, Any]:
    data = entry.runtime_data
    device_data = data.client.cached_device_data(device_id) or data.device_data.get(device_id) or {}
    trimmed = {key: value for key, value in device_data.items() if key not in HISTORY_KEYS}
    for key in HISTORY_KEYS:
        if isinstance(device_data.get(key), list):
            trimmed[f"{key}_count"] = len(device_data[key])
    return async_redact_data(trimmed, REDACT)


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: LeakomaticConfigEntry
) -> dict[str, Any]:
    """Diagnostics for the account: all devices and the connection."""
    data = entry.runtime_data
    return {
        "entry": async_redact_data(
            {"title": entry.title, "unique_id": entry.unique_id, "data": dict(entry.data), "version": entry.version},
            REDACT,
        ),
        "connection": data.client.connection_state(),
        "availability": {
            "available": data.availability.available,
            "available_since": data.availability.available_since.isoformat(),
        },
        "devices": {device_id: _device_diagnostics(entry, device_id) for device_id in data.device_infos},
    }


async def async_get_device_diagnostics(
    hass: HomeAssistant, entry: LeakomaticConfigEntry, device: DeviceEntry
) -> dict[str, Any]:
    """Diagnostics for one device, plus the account's connection."""
    device_id = next(identifier for domain, identifier in device.identifiers if domain == DOMAIN)
    return {
        "connection": entry.runtime_data.client.connection_state(),
        "device": _device_diagnostics(entry, device_id),
    }
