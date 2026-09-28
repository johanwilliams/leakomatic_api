"""Config flow for Leakomatic integration.

This module handles the configuration flow for the Leakomatic integration:
adding a Leakomatic account (all its devices) and asking for a new password
when Leakomatic rejects the stored one.
"""
from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.helpers.selector import TextSelector, TextSelectorConfig, TextSelectorType

from .const import DOMAIN, ERROR_NO_DEVICES_FOUND, LOGGER_NAME
from .leakomatic_client import LeakomaticClient

_LOGGER = logging.getLogger(LOGGER_NAME)

PASSWORD_SELECTOR = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_EMAIL): TextSelector(TextSelectorConfig(type=TextSelectorType.EMAIL)),
        vol.Required(CONF_PASSWORD): PASSWORD_SELECTOR,
    }
)
STEP_REAUTH_DATA_SCHEMA = vol.Schema({vol.Required(CONF_PASSWORD): PASSWORD_SELECTOR})


def account_unique_id(client: LeakomaticClient, email: str) -> str:
    """The config entry's unique ID: the Leakomatic user ID, or the email if it was not found."""
    return client.user_id or email.strip().lower()


class LeakomaticConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Leakomatic.

    One config entry per Leakomatic account; the account's devices are found
    at setup.
    """

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the account's email and password and check them."""
        errors: dict[str, str] = {}

        if user_input is not None:
            client = LeakomaticClient(user_input[CONF_EMAIL], user_input[CONF_PASSWORD])
            if not await client.async_authenticate():
                errors["base"] = client.error_code or "unknown"
            elif not client.device_ids:
                errors["base"] = ERROR_NO_DEVICES_FOUND
            else:
                await self.async_set_unique_id(account_unique_id(client, user_input[CONF_EMAIL]))
                self._abort_if_unique_id_configured()
                _LOGGER.info("Configured Leakomatic account with %d device(s)", len(client.device_ids))
                return self.async_create_entry(
                    title=user_input[CONF_EMAIL],
                    data={CONF_EMAIL: user_input[CONF_EMAIL], CONF_PASSWORD: user_input[CONF_PASSWORD]},
                )

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(STEP_USER_DATA_SCHEMA, user_input),
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        """Start reauthentication when Leakomatic has rejected the stored password."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for a new password and check it before updating the entry."""
        entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        errors: dict[str, str] = {}

        if user_input is not None:
            client = LeakomaticClient(entry.data[CONF_EMAIL], user_input[CONF_PASSWORD])
            if await client.async_authenticate():
                return self.async_update_reload_and_abort(
                    entry,
                    data={**entry.data, CONF_PASSWORD: user_input[CONF_PASSWORD]},
                    reason="reauth_successful",
                )
            errors["base"] = client.error_code or "unknown"

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=STEP_REAUTH_DATA_SCHEMA,
            description_placeholders={"email": entry.data[CONF_EMAIL]},
            errors=errors,
        )
