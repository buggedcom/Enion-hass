"""Integration tests for config_flow.py using the HA test framework.

_validate_credentials is patched at the module level so no real HTTP
calls are ever made.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.data_entry_flow import FlowResultType

from custom_components.enion.api import EnionAuthError, EnionApiError
from custom_components.enion.const import DOMAIN
from tests.conftest import ME_RESPONSE

PATCH_VALIDATE = "custom_components.enion.config_flow._validate_credentials"


@pytest.fixture(autouse=True)
def mock_coordinator_setup():
    """Prevent real network calls when HA automatically sets up a new config entry.

    Creating a config entry via the flow causes HA to call async_setup_entry,
    which in turn calls coordinator.async_setup() (login + WebSocket connect).
    On CI the sandbox blocks outbound connections, leaving a stray aiohttp
    thread that trips pytest-homeassistant-custom-component's teardown check.
    Patching at the coordinator level keeps the config-flow tests focused on
    flow behaviour only.
    """
    with (
        patch(
            "custom_components.enion.EnionCoordinator.async_setup",
            new_callable=AsyncMock,
        ),
        patch(
            "custom_components.enion.EnionCoordinator.async_config_entry_first_refresh",
            new_callable=AsyncMock,
        ),
        patch(
            "custom_components.enion.EnionClient",
            return_value=MagicMock(),
        ),
        patch(
            "custom_components.enion.async_get_clientsession",
            return_value=MagicMock(),
        ),
    ):
        yield

USER_INPUT = {
    CONF_EMAIL: "test@example.com",
    CONF_PASSWORD: "correct_password",
}


# ---------------------------------------------------------------------------
# Initial setup flow
# ---------------------------------------------------------------------------


async def test_user_step_shows_form(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {}


async def test_user_step_success_creates_entry(hass):
    with patch(PATCH_VALIDATE, return_value=ME_RESPONSE):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
            data=USER_INPUT,
        )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "test@example.com"
    assert result["data"][CONF_EMAIL] == "test@example.com"
    assert result["data"][CONF_PASSWORD] == "correct_password"


async def test_user_step_invalid_auth_shows_error(hass):
    with patch(PATCH_VALIDATE, side_effect=EnionAuthError("bad credentials")):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
            data=USER_INPUT,
        )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"]["base"] == "invalid_auth"


async def test_user_step_api_error_shows_cannot_connect(hass):
    with patch(PATCH_VALIDATE, side_effect=EnionApiError("timeout")):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
            data=USER_INPUT,
        )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"]["base"] == "cannot_connect"


async def test_user_step_unexpected_error_shows_unknown(hass):
    with patch(PATCH_VALIDATE, side_effect=RuntimeError("unexpected")):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
            data=USER_INPUT,
        )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"]["base"] == "unknown"


async def test_duplicate_entry_aborts(hass):
    # Create the first entry
    with patch(PATCH_VALIDATE, return_value=ME_RESPONSE):
        await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
            data=USER_INPUT,
        )

    # Attempt a second entry with the same email
    with patch(PATCH_VALIDATE, return_value=ME_RESPONSE):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
            data=USER_INPUT,
        )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_title_uses_user_email_from_me_response(hass):
    me = {**ME_RESPONSE, "user": {**ME_RESPONSE["user"], "email": "actual@address.fi"}}
    with patch(PATCH_VALIDATE, return_value=me):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
            data={**USER_INPUT, CONF_EMAIL: "actual@address.fi"},
        )

    assert result["title"] == "actual@address.fi"


# ---------------------------------------------------------------------------
# Re-auth flow
# ---------------------------------------------------------------------------


async def _create_entry(hass):
    """Helper: create a config entry and return it."""
    with patch(PATCH_VALIDATE, return_value=ME_RESPONSE):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
            data=USER_INPUT,
        )
    return hass.config_entries.async_get_entry(result["result"].entry_id)


async def test_reauth_step_shows_form(hass):
    entry = await _create_entry(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_REAUTH, "entry_id": entry.entry_id},
        data=entry.data,
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"


async def test_reauth_success_updates_entry_and_reloads(hass):
    entry = await _create_entry(hass)
    new_input = {CONF_EMAIL: "test@example.com", CONF_PASSWORD: "new_password"}

    with patch(PATCH_VALIDATE, return_value=ME_RESPONSE), \
         patch.object(hass.config_entries, "async_reload", new_callable=AsyncMock):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_REAUTH, "entry_id": entry.entry_id},
            data=entry.data,
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input=new_input,
        )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_PASSWORD] == "new_password"


async def test_reauth_invalid_auth_shows_error(hass):
    entry = await _create_entry(hass)

    with patch(PATCH_VALIDATE, side_effect=EnionAuthError("bad")):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_REAUTH, "entry_id": entry.entry_id},
            data=entry.data,
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={CONF_EMAIL: "test@example.com", CONF_PASSWORD: "wrong"},
        )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"]["base"] == "invalid_auth"


async def test_reauth_cannot_connect_shows_error(hass):
    entry = await _create_entry(hass)

    with patch(PATCH_VALIDATE, side_effect=EnionApiError("down")):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_REAUTH, "entry_id": entry.entry_id},
            data=entry.data,
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={CONF_EMAIL: "test@example.com", CONF_PASSWORD: "pw"},
        )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"]["base"] == "cannot_connect"
