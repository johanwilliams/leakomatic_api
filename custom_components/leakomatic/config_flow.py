"""Config flow for Leakomatic integration.

This module handles the configuration flow for the Leakomatic integration,
including user authentication and device discovery. It manages the setup
process through the Home Assistant UI.
"""
from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol
import aiohttp

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN, LOGGER_NAME
from .leakomatic_client import LeakomaticClient

_LOGGER = logging.getLogger(LOGGER_NAME)

class LeakomaticConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Leakomatic.
    
    This class guides the user through the setup process, validates their
    credentials, and creates the necessary config entries in Home Assistant.
    """

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step.
        
        This step collects and validates user credentials, tests the connection
        to the Leakomatic API, and creates the config entry if successful.

        Args:
            user_input: Dictionary containing user provided configuration data.
                       None if this is the first time showing the form.

        Returns:
            FlowResult: The result of the config flow step.
        """
        errors = {}

        if user_input is not None:
            try:
                _LOGGER.debug("Attempting to validate Leakomatic credentials")
                
                # Create a client and authenticate
                client = LeakomaticClient(user_input["email"], user_input["password"])
                auth_success = await client.async_authenticate()
                
                if not auth_success:
                    _LOGGER.warning("Authentication failed")
                    # Use the specific error code from the client if available
                    error_code = client.error_code or "invalid_credentials"
                    errors["base"] = error_code
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
                
                # Get the device ID
                device_id = client.device_id
                if not device_id:
                    _LOGGER.warning("No device ID found after authentication")
                    errors["base"] = "no_devices_found"
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
                        _LOGGER.info("Account is already configured")
                        return self.async_abort(reason="already_configured")
                
                # Store the device ID in the config entry data
                user_input["device_id"] = device_id
                
                # Authentication successful, create the config entry
                _LOGGER.info("Successfully configured Leakomatic device: %s", device_id)
                return self.async_create_entry(
                    title=f"Leakomatic Device {device_id}",
                    data=user_input,
                )
            except aiohttp.ClientError:
                _LOGGER.warning("Connection error during setup")
                errors["base"] = "cannot_connect"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.error("Unexpected error during setup")
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

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> FlowResult:
        """Start reauthentication when Leakomatic has rejected the stored password."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Ask for a new password and check it before updating the entry."""
        entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        errors: dict[str, str] = {}

        if user_input is not None:
            client = LeakomaticClient(entry.data["email"], user_input["password"])
            if await client.async_authenticate():
                return self.async_update_reload_and_abort(
                    entry,
                    data={**entry.data, "password": user_input["password"]},
                    reason="reauth_successful",
                )
            errors["base"] = client.error_code or "unknown"

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required("password"): str}),
            description_placeholders={"email": entry.data["email"]},
            errors=errors,
        )