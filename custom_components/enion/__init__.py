"""Enion Home Assistant integration."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import EnionAuthError, EnionClient
from .const import DOMAIN
from .coordinator import EnionCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.CALENDAR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Enion from a config entry."""
    _LOGGER.info("Setting up Enion entry: %s", entry.title)
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
        _LOGGER.debug("Running coordinator setup")
        await coordinator.async_setup()
        # Populate coordinator.data so entities have values before the first
        # WebSocket push arrives.  For a push-based coordinator this replaces
        # async_config_entry_first_refresh() which would call _async_update_data
        # and raise ConfigEntryNotReady on any transient error.
        await coordinator.async_config_entry_first_refresh()
    except ConfigEntryAuthFailed:
        _LOGGER.error("Enion credentials are invalid")
        raise
    except ConfigEntryNotReady:
        _LOGGER.warning("Enion connection not ready, will retry")
        raise
    except EnionAuthError as exc:
        # Credentials rejected — surface the re-auth flow via the standard
        # HA mechanism rather than calling async_start_reauth manually.
        _LOGGER.error("Enion authentication error: %s", exc)
        raise ConfigEntryAuthFailed("Enion credentials are invalid") from exc
    except Exception as exc:  # noqa: BLE001
        # Treat all other errors (timeouts, network failures, unexpected API
        # responses) as transient so HA will retry automatically.
        _LOGGER.error("Enion connection error: %s", exc)
        raise ConfigEntryNotReady(f"Could not connect to Enion: {exc}") from exc

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    entry.async_on_unload(lambda: hass.async_create_task(coordinator.async_shutdown()))

    _LOGGER.info("Enion entry setup complete: %s", entry.title)
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
