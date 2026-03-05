"""Enion Home Assistant integration."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import EnionAuthError, EnionClient
from .const import DOMAIN
from .coordinator import EnionCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Enion from a config entry."""
    session = async_get_clientsession(hass)
    client = EnionClient(session)

    coordinator = EnionCoordinator(
        hass=hass,
        session=session,
        client=client,
        email=entry.data[CONF_EMAIL],
        password=entry.data[CONF_PASSWORD],
    )

    try:
        await coordinator.async_setup()
    except EnionAuthError:
        entry.async_start_reauth(hass)
        return False
    except Exception as exc:  # noqa: BLE001
        _LOGGER.error("Failed to set up Enion: %s", exc)
        return False

    # Trigger the first data fetch so entities have data on startup
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    entry.async_on_unload(lambda: hass.async_create_task(coordinator.async_shutdown()))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        coordinator: EnionCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.async_shutdown()
    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle config entry updates (e.g. re-auth)."""
    await hass.config_entries.async_reload(entry.entry_id)
