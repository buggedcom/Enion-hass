"""Config flow for Enion integration."""
from __future__ import annotations

import logging
from typing import Any

import aiohttp
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import EnionAuthError, EnionApiError, EnionClient
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_EMAIL): TextSelector(
            TextSelectorConfig(type=TextSelectorType.EMAIL, autocomplete="email")
        ),
        vol.Required(CONF_PASSWORD): TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD, autocomplete="current-password")
        ),
    }
)


async def _validate_credentials(
    hass, email: str, password: str
) -> dict[str, Any]:
    """Attempt login and return the /auth/me payload, or raise on failure."""
    _LOGGER.debug("Starting credential validation for email: %s", email)
    session = async_get_clientsession(hass)
    client = EnionClient(session)
    await client.login(email, password)
    me = await client.fetch_me()
    _LOGGER.debug("Credential validation successful for email: %s", email)
    return me


class EnionConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the initial setup flow for Enion."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            email = user_input[CONF_EMAIL]
            password = user_input[CONF_PASSWORD]

            _LOGGER.debug("User submitted login attempt for email: %s", email)
            try:
                me = await _validate_credentials(self.hass, email, password)
            except EnionAuthError as exc:
                _LOGGER.warning("Authentication failed for email %s: %s", email, exc)
                errors["base"] = "invalid_auth"
            except (EnionApiError, aiohttp.ClientError) as exc:
                _LOGGER.warning("Connection error during login for email %s: %s", email, exc)
                errors["base"] = "cannot_connect"
            except Exception as exc:  # noqa: BLE001
                _LOGGER.exception("Unexpected error during Enion login for email %s", email)
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(email.lower())
                self._abort_if_unique_id_configured()

                user = me.get("user") or {}
                title = user.get("email") or email
                _LOGGER.info("Successfully configured Enion for user: %s", title)
                return self.async_create_entry(
                    title=title,
                    data={CONF_EMAIL: email, CONF_PASSWORD: password},
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> config_entries.FlowResult:
        """Handle re-authentication when credentials become invalid."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        errors: dict[str, str] = {}
        reauth_entry = self._get_reauth_entry()

        if user_input is not None:
            email = user_input[CONF_EMAIL]
            password = user_input[CONF_PASSWORD]

            try:
                await _validate_credentials(self.hass, email, password)
            except EnionAuthError:
                errors["base"] = "invalid_auth"
            except (EnionApiError, aiohttp.ClientError):
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected error during Enion re-auth")
                errors["base"] = "unknown"
            else:
                self.hass.config_entries.async_update_entry(
                    reauth_entry,
                    data={CONF_EMAIL: email, CONF_PASSWORD: password},
                )
                await self.hass.config_entries.async_reload(reauth_entry.entry_id)
                return self.async_abort(reason="reauth_successful")

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_EMAIL,
                        default=reauth_entry.data.get(CONF_EMAIL, ""),
                    ): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.EMAIL, autocomplete="email")
                    ),
                    vol.Required(CONF_PASSWORD): TextSelector(
                        TextSelectorConfig(
                            type=TextSelectorType.PASSWORD,
                            autocomplete="current-password",
                        )
                    ),
                }
            ),
            errors=errors,
        )
