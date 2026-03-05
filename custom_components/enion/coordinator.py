"""DataUpdateCoordinator for Enion — manages WS connection and data state."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .api import EnionClient, EnionWebSocket
from .const import (
    DOMAIN,
    PORT_BATTERY,
    PORT_ENERGY,
    PORT_GRID,
    PORT_OPTIMIZER,
    PORT_PRICES,
    PORT_RELAY,
    PORT_WEATHER,
    DATA_DEVICE,
    DATA_PORTS,
    DATA_PRICES,
    DATA_WEATHER,
    DATA_OPTIMIZER,
)

_LOGGER = logging.getLogger(__name__)

# Reconnect delay after WS drop
_RECONNECT_DELAY = 30


class EnionCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Owns the EnionClient + WebSocket; pushes data to HA entities.

    Unlike a polling coordinator this one is push-based: the WebSocket
    fires callbacks on every ``update`` or ``device`` event and we call
    ``async_set_updated_data`` to notify listeners immediately.
    We do not set an ``update_interval`` so HA never polls us.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        session: aiohttp.ClientSession,
        client: EnionClient,
        email: str,
        password: str,
    ) -> None:
        super().__init__(hass, _LOGGER, name=DOMAIN)
        self._session = session
        self._client = client
        self._email = email
        self._password = password
        self._ws: EnionWebSocket | None = None
        self._reconnect_task: asyncio.Task | None = None

        # Static device metadata set once from /auth/me
        self.device_meta: dict[str, Any] = {}

        # Mutable data store; entities read from self.data
        self._store: dict[str, Any] = {
            DATA_DEVICE: {},
            DATA_PORTS: {},   # keyed by port_id (int)
            DATA_PRICES: [],
            DATA_WEATHER: [],
            DATA_OPTIMIZER: {},
        }

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def async_setup(self) -> None:
        """Login, fetch profile, seed data store, and connect the WebSocket."""
        await self._client.login(self._email, self._password)
        me = await self._client.fetch_me()
        self._seed_from_me(me)
        await self._connect_ws()

    def _seed_from_me(self, me: dict[str, Any]) -> None:
        """Pre-populate the data store from the /auth/me response.

        This gives entities valid port IDs and device info immediately on
        startup, before the first WebSocket ``update`` events arrive.
        """
        devices: list[dict[str, Any]] = me.get("devices") or []
        if not devices:
            _LOGGER.warning("No devices found in /auth/me response")
            return

        device = devices[0]
        spec: dict[str, Any] = device.get("device_spec") or {}

        self.device_meta = {
            "device_id": device.get("id"),
            "hw_id": device.get("hw_id", ""),
            "manufacturer": spec.get("manufacturer", "Sunergos"),
            "model": spec.get("model", "Enion"),
            "description": spec.get("description", ""),
        }

        # Seed device online status from the snapshot values in /me
        device_values: dict[str, Any] = device.get("values") or {}
        self._store[DATA_DEVICE].update(
            {
                "online": device_values.get("online", False),
                "last_data": device_values.get("last_data"),
                "firmware_version": device_values.get("firmware_version"),
                "hw_id": device.get("hw_id"),
            }
        )

        # Seed port map so find_port_by_prefix works before any WS events
        for port in device.get("ports") or []:
            port_id = port.get("id")
            port_number = port.get("port_number", "")
            if port_id is not None:
                self._store[DATA_PORTS].setdefault(port_id, {}).update(
                    {
                        "port_number": port_number,
                        "type": port.get("type", ""),
                        "values": port.get("values") or {},
                    }
                )

        _LOGGER.debug(
            "Seeded %d ports for device %s (%s %s)",
            len(self._store[DATA_PORTS]),
            self.device_meta.get("hw_id"),
            self.device_meta.get("manufacturer"),
            self.device_meta.get("model"),
        )

    async def async_shutdown(self) -> None:
        """Disconnect cleanly on HA stop."""
        if self._reconnect_task:
            self._reconnect_task.cancel()
        if self._ws:
            await self._ws.disconnect()

    # ------------------------------------------------------------------
    # DataUpdateCoordinator — we push data; _async_update_data unused
    # ------------------------------------------------------------------

    async def _async_update_data(self) -> dict[str, Any]:
        # Called once on first coordinator refresh; just return current state.
        return self._store

    # ------------------------------------------------------------------
    # WebSocket management
    # ------------------------------------------------------------------

    async def _connect_ws(self) -> None:
        if not self._client.ws_token or not self._client.user_id:
            _LOGGER.error("Cannot connect WebSocket: missing token or user_id")
            return
        self._ws = EnionWebSocket(
            session=self._session,
            ws_token=self._client.ws_token,
            user_id=self._client.user_id,
            on_update=self._handle_update,
            on_device=self._handle_device,
            on_disconnect=self._on_ws_disconnect,
        )
        await self._ws.connect()

    def _on_ws_disconnect(self) -> None:
        _LOGGER.warning("Enion WebSocket disconnected; will reconnect in %ds", _RECONNECT_DELAY)
        self._reconnect_task = self.hass.async_create_task(self._reconnect())

    async def _reconnect(self) -> None:
        await asyncio.sleep(_RECONNECT_DELAY)
        try:
            # Re-authenticate in case the token expired
            await self._client.login(self._email, self._password)
            await self._client.fetch_me()
            await self._connect_ws()
        except Exception as exc:  # noqa: BLE001
            _LOGGER.error("Enion reconnect failed: %s", exc)
            self._reconnect_task = self.hass.async_create_task(self._reconnect())

    # ------------------------------------------------------------------
    # WebSocket event handlers
    # ------------------------------------------------------------------

    def _handle_device(self, payload: dict[str, Any]) -> None:
        """Handle a ``device`` event (device online status)."""
        values = payload.get("values", {})
        self._store[DATA_DEVICE].update(
            {
                "online": values.get("online", False),
                "last_data": values.get("last_data"),
                "firmware_version": values.get("firmware_version"),
                "hw_id": payload.get("hw_id"),
            }
        )
        self.async_set_updated_data(dict(self._store))

    def _handle_update(self, payload: dict[str, Any]) -> None:
        """Handle an ``update`` event (port value change)."""
        port_id = payload.get("port_id")
        port_number: str = payload.get("port_number", "")
        values: dict[str, Any] = payload.get("values") or {}

        if not values or port_id is None:
            return

        port_prefix = port_number.split("/")[0]

        # Merge into port store
        port_data = self._store[DATA_PORTS].setdefault(port_id, {})
        port_data["port_number"] = port_number
        port_data["values"] = values

        # Also propagate to well-known top-level stores for convenience
        if port_prefix == PORT_PRICES:
            prices_raw = values.get("prices", [])
            base_ts = values.get("base_ts")
            timestep = values.get("timestep", 3600)
            if prices_raw and base_ts is not None:
                self._store[DATA_PRICES] = [
                    {"ts": base_ts + i * timestep, "price": p}
                    for i, p in enumerate(prices_raw)
                ]
        elif port_prefix == PORT_WEATHER:
            weathers = values.get("weathers", [])
            base_ts = values.get("base_ts")
            timestep = values.get("timestep", 3600)
            if weathers and base_ts is not None:
                self._store[DATA_WEATHER] = [
                    {"ts": base_ts + i * timestep, **w}
                    for i, w in enumerate(weathers)
                ]
        elif port_prefix == PORT_OPTIMIZER:
            self._store[DATA_OPTIMIZER].update(values)

        self.async_set_updated_data(dict(self._store))

    # ------------------------------------------------------------------
    # Convenience accessors used by entities
    # ------------------------------------------------------------------

    def get_port_values(self, port_id: int) -> dict[str, Any]:
        return self._store[DATA_PORTS].get(port_id, {}).get("values", {})

    def find_port_by_prefix(self, prefix: str, sub: str = "0") -> int | None:
        """Return the first port_id whose port_number matches ``prefix/sub``."""
        target = f"{prefix}/{sub}"
        for pid, pdata in self._store[DATA_PORTS].items():
            if pdata.get("port_number") == target:
                return pid
        return None

    def get_device_info(self) -> dict[str, Any]:
        return self._store[DATA_DEVICE]

    def get_current_price(self) -> float | None:
        """Return the electricity price for the current hour (ct/kWh)."""
        import time
        now = int(time.time())
        for entry in self._store[DATA_PRICES]:
            ts = entry.get("ts", 0)
            if ts <= now < ts + 3600:
                return entry.get("price")
        return None

    def get_next_price(self) -> float | None:
        """Return the electricity price for the next hour."""
        import time
        now = int(time.time())
        for entry in self._store[DATA_PRICES]:
            ts = entry.get("ts", 0)
            if ts > now:
                return entry.get("price")
        return None
