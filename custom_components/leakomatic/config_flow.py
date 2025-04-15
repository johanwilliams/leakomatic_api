"""Config flow for Leakomatic integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
import aiohttp

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN, LOGGER_NAME
from .client import LeakomaticClient

_LOGGER = logging.getLogger(LOGGER_NAME)

class LeakomaticConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Leakomatic."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            try:
                _LOGGER.debug("Attempting to create config entry with email: %s", user_input["email"])
                
                # Create a client and authenticate
                client = LeakomaticClient(user_input["email"], user_input["password"])
                auth_success = await client.async_authenticate()
                
                if not auth_success:
                    _LOGGER.error("Authentication failed")
                    errors["base"] = "invalid_credentials"
                    return self.async_show_form(
                        step_id="user",
                        data_schema=vol.Schema(
                            {
                                vol.Required("email"): str,
                                vol.Required("password"): str,
                            }
                        ),
                        errors=errors,
                    )
                
                # Check if this email is already configured
                existing_entries = self._async_current_entries()
                for entry in existing_entries:
                    if entry.data.get("email") == user_input["email"]:
                        return self.async_abort(reason="already_configured")
                
                # Authentication successful, create the config entry
                return self.async_create_entry(
                    title=user_input["email"],
                    data=user_input,
                )
            except aiohttp.ClientError:
                _LOGGER.exception("Connection error during config flow setup")
                errors["base"] = "cannot_connect"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception during config flow setup")
                errors["base"] = "unknown"

        _LOGGER.debug("Showing config flow form")
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required("email"): str,
                    vol.Required("password"): str,
                }
            ),
            errors=errors,
        ) 