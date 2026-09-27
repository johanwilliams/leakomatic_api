"""Tests for the Leakomatic config flow."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.leakomatic.const import DOMAIN

from .conftest import EMAIL, PASSWORD

USER_INPUT = {"email": EMAIL, "password": PASSWORD}


def _client(auth_ok: bool = True, error_code: str | None = None, device_id: str | None = "1001") -> MagicMock:
    client = MagicMock()
    client.async_authenticate = AsyncMock(return_value=auth_ok)
    client.error_code = error_code
    client.device_id = device_id
    return client


async def _start(hass: HomeAssistant) -> dict:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    return result


async def test_create_entry(hass: HomeAssistant) -> None:
    """Valid credentials create a config entry."""
    result = await _start(hass)
    with (
        patch("custom_components.leakomatic.config_flow.LeakomaticClient", return_value=_client()),
        patch("custom_components.leakomatic.async_setup_entry", return_value=True),
    ):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"]["email"] == EMAIL


async def test_invalid_credentials(hass: HomeAssistant) -> None:
    """A failed login shows the form again with the client's error code."""
    result = await _start(hass)
    with patch(
        "custom_components.leakomatic.config_flow.LeakomaticClient",
        return_value=_client(auth_ok=False, error_code="invalid_credentials"),
    ):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_credentials"}


async def test_already_configured(hass: HomeAssistant) -> None:
    """The same account cannot be added twice."""
    MockConfigEntry(domain=DOMAIN, data={"email": EMAIL, "password": PASSWORD}).add_to_hass(hass)

    result = await _start(hass)
    with patch("custom_components.leakomatic.config_flow.LeakomaticClient", return_value=_client()):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_cannot_connect(hass: HomeAssistant) -> None:
    """A network or server error is reported as such, not as a wrong password."""
    result = await _start(hass)
    with patch(
        "custom_components.leakomatic.config_flow.LeakomaticClient",
        return_value=_client(auth_ok=False, error_code="cannot_connect"),
    ):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)

    assert result["errors"] == {"base": "cannot_connect"}


async def test_reauth_updates_password(hass: HomeAssistant) -> None:
    """HA-199: a new, valid password is stored and the entry reloaded."""
    entry = MockConfigEntry(domain=DOMAIN, data={"email": EMAIL, "password": "old"})
    entry.add_to_hass(hass)

    result = await entry.start_reauth_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"

    with (
        patch("custom_components.leakomatic.config_flow.LeakomaticClient", return_value=_client()) as client_cls,
        patch("custom_components.leakomatic.async_setup_entry", return_value=True),
    ):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"password": "new"})
        await hass.async_block_till_done()

    client_cls.assert_called_once_with(EMAIL, "new")
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data["password"] == "new"


async def test_reauth_wrong_password(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(domain=DOMAIN, data={"email": EMAIL, "password": "old"})
    entry.add_to_hass(hass)

    result = await entry.start_reauth_flow(hass)
    with patch(
        "custom_components.leakomatic.config_flow.LeakomaticClient",
        return_value=_client(auth_ok=False, error_code="invalid_credentials"),
    ):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"password": "still-wrong"})

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_credentials"}
    assert entry.data["password"] == "old"
