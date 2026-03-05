"""DataUpdateCoordinator for Enion — manages WS connection and data state."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import logging
import time
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

# Exponential backoff: delay = min(BASE * 2^attempt, MAX)
_RECONNECT_DELAY_BASE = 30    # seconds
_RECONNECT_DELAY_MAX = 600    # 10 minutes

# WS JWT token lifetime is 15 minutes; re-login when older than this.
_TOKEN_MAX_AGE = 840          # 14 minutes


def _parse_iso8601_to_unix(iso_str: str | int | float | None) -> int | None:
    """Convert ISO 8601 timestamp string to Unix timestamp.

    Handles string, int, and float inputs.  Returns None for None or
    unparseable input.

    Correctly converts timezone-aware strings (e.g. ``+02:00``) to UTC
    rather than merely replacing the tzinfo attribute, which would silently
    produce a wrong timestamp and, in some Python builds, raise
    ``TypeError: can't compare offset-naive and offset-aware datetimes``
    when the resulting datetime is subtracted from the UTC epoch internally.
    """
    if iso_str is None:
        return None
    if isinstance(iso_str, (int, float)):
        return int(iso_str)
    try:
        # Replace the 'Z' suffix with '+00:00' so fromisoformat always receives
        # an explicit UTC offset, avoiding a naive datetime that can later cause
        # "can't compare offset-naive and offset-aware datetimes" errors.
        normalized = iso_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized)
        if dt.tzinfo is None:
            # No offset in the string at all — assume UTC.
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            # Offset present — convert to UTC, adjusting the time values
            # correctly.  astimezone() does this; replace() would not.
            dt = dt.astimezone(timezone.utc)
        return int(dt.timestamp())
    except (ValueError, AttributeError, TypeError, OverflowError) as e:
        _LOGGER.warning("Failed to parse timestamp '%s': %s", iso_str, e)
        return None


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
        self._reconnect_attempt = 0
        self._last_login_at: float = 0.0

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
        await self._login_and_seed()
        await self._connect_ws()

    async def _login_and_seed(self) -> None:
        """Perform login + /auth/me and seed the data store."""
        await self._client.login(self._email, self._password)
        self._last_login_at = time.monotonic()
        me = await self._client.fetch_me()
        self._seed_from_me(me)

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
                _LOGGER.debug("Seeding port: port_id=%s, port_number=%s, values=%s", port_id, port_number, port.get("values", {}))
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
        if self._reconnect_task and not self._reconnect_task.done():
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
        # Reset backoff on successful connection
        self._reconnect_attempt = 0

    def _on_ws_disconnect(self) -> None:
        """Called by the WebSocket on unexpected disconnect.

        Ensures only one reconnect task is ever running at a time.
        """
        # Cancel any in-progress reconnect before scheduling a new one.
        if self._reconnect_task and not self._reconnect_task.done():
            self._reconnect_task.cancel()

        delay = min(
            _RECONNECT_DELAY_BASE * (2 ** self._reconnect_attempt),
            _RECONNECT_DELAY_MAX,
        )
        _LOGGER.warning(
            "Enion WebSocket disconnected; reconnect attempt %d in %ds",
            self._reconnect_attempt + 1,
            delay,
        )
        self._reconnect_task = self.hass.async_create_task(
            self._reconnect(delay)
        )

    async def _reconnect(self, delay: float) -> None:
        """Wait ``delay`` seconds then attempt to reconnect."""
        try:
            await asyncio.sleep(delay)
        except asyncio.CancelledError:
            return

        self._reconnect_attempt += 1
        try:
            # Only re-login if the WS JWT token may have expired.
            token_age = time.monotonic() - self._last_login_at
            if token_age >= _TOKEN_MAX_AGE:
                _LOGGER.debug("WS token age %.0fs >= %ds, re-logging in", token_age, _TOKEN_MAX_AGE)
                await self._client.login(self._email, self._password)
                self._last_login_at = time.monotonic()

            await self._connect_ws()
            # _connect_ws resets _reconnect_attempt on success
        except Exception as exc:  # noqa: BLE001
            _LOGGER.error(
                "Enion reconnect attempt %d failed: %s", self._reconnect_attempt, exc
            )
            self._on_ws_disconnect()  # schedule next attempt with increased backoff

    # ------------------------------------------------------------------
    # WebSocket event handlers
    # ------------------------------------------------------------------

    def _notify_listeners(self) -> None:
        """Push the current store snapshot to all entity listeners.

        Wraps ``async_set_updated_data`` in a try/except so that an exception
        raised by any listener callback — e.g. a third-party HA integration
        calling the old ``CalendarEvent(title=…)`` API that was renamed to
        ``summary=`` — cannot propagate back into our WebSocket message handler
        and be silently misattributed as a parse failure.
        """
        try:
            self.async_set_updated_data(dict(self._store))
        except Exception:  # noqa: BLE001
            _LOGGER.exception(
                "Exception in an entity listener after coordinator update; "
                "this is likely a bug in another installed integration"
            )

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
        self._notify_listeners()

    def _handle_update(self, payload: dict[str, Any]) -> None:
        """Handle an ``update`` event (port value change)."""
        port_id = payload.get("port_id")
        port_number: str = payload.get("port_number", "")
        values: dict[str, Any] = payload.get("values") or {}

        if not values or port_id is None:
            return

        port_prefix = port_number.split("/")[0]

        _LOGGER.debug("Port update: port_id=%s, port_number=%s, values=%s", port_id, port_number, values)

        # Merge into port store
        port_data = self._store[DATA_PORTS].setdefault(port_id, {})
        port_data["port_number"] = port_number
        port_data["values"] = values

        # Also propagate to well-known top-level stores for convenience
        if port_prefix == PORT_PRICES:
            prices_raw = values.get("prices", [])
            base_ts = _parse_iso8601_to_unix(values.get("base_ts"))
            timestep = values.get("timestep", 3600)
            if prices_raw and base_ts is not None:
                self._store[DATA_PRICES] = [
                    {"ts": base_ts + i * timestep, "price": p}
                    for i, p in enumerate(prices_raw)
                ]
        elif port_prefix == PORT_WEATHER:
            weathers = values.get("weathers", [])
            base_ts = _parse_iso8601_to_unix(values.get("base_ts"))
            timestep = values.get("timestep", 3600)
            if weathers and base_ts is not None:
                self._store[DATA_WEATHER] = [
                    {"ts": base_ts + i * timestep, **w}
                    for i, w in enumerate(weathers)
                ]
        elif port_prefix == PORT_OPTIMIZER:
            self._store[DATA_OPTIMIZER].update(values)

        self._notify_listeners()

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
        now = int(time.time())
        for entry in self._store[DATA_PRICES]:
            ts = entry.get("ts", 0)
            if ts <= now < ts + 3600:
                price = entry.get("price")
                # API returns price in tenths of cents, divide by 10 for ct/kWh
                return price / 10 if price is not None else None
        return None

    def get_next_price(self) -> float | None:
        """Return the electricity price for the next hour."""
        now = int(time.time())
        for entry in self._store[DATA_PRICES]:
            ts = entry.get("ts", 0)
            if ts > now:
                price = entry.get("price")
                # API returns price in tenths of cents, divide by 10 for ct/kWh
                return price / 10 if price is not None else None
        return None

    # ------------------------------------------------------------------
    # Battery Optimizer (220/0)
    # ------------------------------------------------------------------

    def get_optimizer_state(self) -> tuple[str | None, str | None, list[dict[str, Any]]]:
        """Get battery optimizer current state, next state/time, and full schedule.

        Returns:
            Tuple of (current_state, next_event_time, full_schedule)
            - current_state: e.g., "NET_ZERO", "CHARGE", "AVOID_SELL"
            - next_event_time: ISO 8601 string or None if no future events
            - full_schedule: List of dicts with 'time' and 'state' keys
        """
        optimizer_data = self._store.get(DATA_OPTIMIZER, {})
        events = optimizer_data.get("events", [])

        if not events:
            return None, None, []

        # Parse events: each is [timestamp_str, {state, reserve_up, reserve_dn}]
        now = int(time.time())
        current_state = None
        next_event_time = None
        schedule = []

        for event_time_str, event_data in events:
            try:
                event_ts = _parse_iso8601_to_unix(event_time_str)
                if event_ts is None:
                    continue

                state = event_data.get("state", "").replace("BATTERY_OPTIMIZER_STATE_", "")

                schedule.append({
                    "time": event_time_str,
                    "timestamp": event_ts,
                    "state": state,
                    "reserve_up": event_data.get("reserve_up"),
                    "reserve_dn": event_data.get("reserve_dn"),
                })

                # Current state: event time <= now < next event time
                if event_ts <= now:
                    current_state = state
                # Next event: first event in future
                elif next_event_time is None:
                    next_event_time = event_time_str

            except (ValueError, KeyError, TypeError):
                continue

        return current_state, next_event_time, schedule
