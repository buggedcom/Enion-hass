"""DataUpdateCoordinator for Enion — manages WS connection and data state."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import logging
import time
from typing import Any

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util.dt import utcnow

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
    DATA_PROFITS,
    DATA_WEATHER,
    DATA_OPTIMIZER,
    DATA_USER,
)

_LOGGER = logging.getLogger(__name__)

# Map of known port types to keys we explicitly handle from the API
# This helps identify new/undocumented API fields for future expansion
_KNOWN_PORT_KEYS: dict[str, set[str]] = {
    PORT_BATTERY: {
        "soc", "power", "energy", "phase_volt", "phase_curr", "freq", "status"
    },
    PORT_GRID: {
        "power", "all_time_wh", "freq", "phase_volt", "phase_curr"
    },
    PORT_ENERGY: {
        "power", "energy", "rms_voltage", "cur_current", "phases"
    },
    PORT_PRICES: {
        "base_ts", "timestep", "prices"
    },
    PORT_WEATHER: {
        "base_ts", "timestep", "weathers"
    },
    PORT_RELAY: {
        "is_on"
    },
    PORT_OPTIMIZER: {
        "commissioning_state", "commissioning_errcode", "events"
    },
}

# Exponential backoff: delay = min(BASE * 2^attempt, MAX)
_RECONNECT_DELAY_BASE = 30    # seconds
_RECONNECT_DELAY_MAX = 600    # 10 minutes

# WS JWT token lifetime is 15 minutes; re-login when older than this.
_TOKEN_MAX_AGE = 840          # 14 minutes


def _log_unknown_keys(port_prefix: str, values: dict[str, Any]) -> None:
    """Log any keys in values that aren't in our known set.

    This helps identify new API fields that aren't yet exposed as sensors,
    so users can report them for future incorporation.
    """
    known_keys = _KNOWN_PORT_KEYS.get(port_prefix, set())
    if not known_keys:
        return  # Unknown port type, don't log

    received_keys = set(values.keys())
    unknown_keys = received_keys - known_keys

    if unknown_keys:
        _LOGGER.debug(
            "Unknown keys detected on %s port: %s. "
            "If these are important values, please open an issue at "
            "https://github.com/buggedcom/Enion-hass/issues with this information",
            port_prefix,
            sorted(unknown_keys),
        )


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
            DATA_PROFITS: [],
            DATA_USER: {},
        }

        # Profits polling state
        self._profits_fetch_in_progress: bool = False
        self._profits_unsub: Any = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def async_setup(self) -> None:
        """Login, fetch profile, seed data store, and connect the WebSocket."""
        await self._login_and_seed()
        await self._connect_ws()
        await self._fetch_and_store_profits()
        self._profits_unsub = async_track_time_interval(
            self.hass, self._scheduled_profits_fetch, timedelta(hours=1)
        )

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
                port_values = port.get("values") or {}
                port_prefix = port_number.split("/")[0]
                _LOGGER.debug("Seeding port: port_id=%s, port_number=%s, values=%s", port_id, port_number, port_values)
                # Log unknown keys during seed
                _log_unknown_keys(port_prefix, port_values)
                self._store[DATA_PORTS].setdefault(port_id, {}).update(
                    {
                        "port_number": port_number,
                        "type": port.get("type", ""),
                        "values": port_values,
                    }
                )

        _LOGGER.debug(
            "Seeded %d ports for device %s (%s %s)",
            len(self._store[DATA_PORTS]),
            self.device_meta.get("hw_id"),
            self.device_meta.get("manufacturer"),
            self.device_meta.get("model"),
        )

        # Seed user data from /auth/me response
        user: dict[str, Any] = me.get("user") or {}
        if user:
            area: dict[str, Any] = user.get("area") or {}
            country: dict[str, Any] = user.get("country") or {}
            settings: dict[str, Any] = user.get("settings") or {}

            self._store[DATA_USER].update(
                {
                    "area_code": area.get("code"),
                    "area_id": area.get("id"),
                    "area_name": area.get("name"),
                    "country_id": country.get("id"),
                    "country_name": country.get("name"),
                    "country_iso_3166": country.get("iso_3166"),
                    "currency": user.get("currency"),
                    "last_ip": user.get("last_ip"),
                    # Settings (excluding iban)
                    "cheap_end_time": settings.get("cheapEndTime"),
                    "cheap_start_time": settings.get("cheapStartTime"),
                    "cheap_transfer_price": settings.get("cheapTransferPrice"),
                    "contract_address": settings.get("contractAddress"),
                    "contract_name": settings.get("contractName"),
                    "contract_type": settings.get("contractType"),
                    "electricity_price": settings.get("electricityPrice"),
                    "has_accept_reserve_markets": settings.get("hasAcceptReserveMarkets"),
                    "has_cheap_transfer": settings.get("hasCheapTransfer"),
                    "has_reserve_markets": settings.get("hasReserveMarkets"),
                    "is_vat_registered": settings.get("isVatRegistered"),
                    "margin_price": settings.get("marginPrice"),
                    "meter_number": settings.get("meterNumber"),
                    "transfer_price": settings.get("transferPrice"),
                    "zip_code": settings.get("zipCode"),
                }
            )

    async def async_shutdown(self) -> None:
        """Disconnect cleanly on HA stop."""
        if self._profits_unsub is not None:
            self._profits_unsub()
            self._profits_unsub = None
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

        # Log any unknown keys for debugging
        _log_unknown_keys(port_prefix, values)

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
    # Profits polling
    # ------------------------------------------------------------------

    async def _scheduled_profits_fetch(self, _now: Any = None) -> None:
        """Called by async_track_time_interval every hour."""
        await self._fetch_and_store_profits()

    async def _fetch_and_store_profits(self) -> None:
        """Fetch the rolling 90-day profit window and update the store + statistics."""
        if self._profits_fetch_in_progress:
            _LOGGER.debug("Profits fetch already in progress, skipping")
            return

        port_id = self.find_port_by_prefix(PORT_BATTERY, "0")
        if port_id is None:
            _LOGGER.warning(
                "Cannot fetch profits: battery port (22/0) not found in port store"
            )
            return

        self._profits_fetch_in_progress = True
        try:
            to_dt = utcnow()
            from_dt = to_dt - timedelta(days=90)
            records: list[dict[str, Any]] = await self._client.fetch_profits(
                port_id, from_dt, to_dt
            )
            self._store[DATA_PROFITS] = records
            _LOGGER.debug("Fetched %d profit records", len(records))
            self._inject_profit_statistics(records)
            self._notify_listeners()
        except Exception as exc:  # noqa: BLE001
            _LOGGER.error("Failed to fetch profits: %s", exc)
        finally:
            self._profits_fetch_in_progress = False

    def _inject_profit_statistics(self, records: list[dict[str, Any]]) -> None:
        """Inject profit data as HA external statistics for Energy dashboard backfill."""
        if not records:
            return

        try:
            from homeassistant.components.recorder import get_instance
            from homeassistant.components.recorder.models import (
                StatisticData,
                StatisticMetaData,
            )
            from homeassistant.components.recorder.statistics import (
                async_add_external_statistics,
            )
        except ImportError:
            _LOGGER.debug("Recorder not available, skipping statistics injection")
            return

        # Sort records chronologically so cumulative sums build correctly
        sorted_records = sorted(records, key=lambda r: r.get("timestamp", ""))

        stat_keys = {
            "profit_spot_saving": "spot_saving",
            "profit_fcr_down": "fcr_down_price",
            "profit_fcr_up": "fcr_up_price",
        }

        for stat_suffix, field in stat_keys.items():
            statistic_id = f"{DOMAIN}:{stat_suffix}"
            metadata = StatisticMetaData(
                source=DOMAIN,
                statistic_id=statistic_id,
                name=f"Enion {stat_suffix.replace('_', ' ').title()}",
                unit_of_measurement="EUR",
                has_mean=False,
                has_sum=True,
            )
            cumulative = 0.0
            stat_data: list[StatisticData] = []
            for rec in sorted_records:
                value = float(rec.get(field) or 0.0)
                cumulative += value
                try:
                    start = datetime.fromisoformat(
                        rec["timestamp"].replace("Z", "+00:00")
                    )
                except (KeyError, ValueError):
                    continue
                stat_data.append(
                    StatisticData(start=start, state=value, sum=cumulative)
                )

            async_add_external_statistics(self.hass, metadata, stat_data)

        # Combined total statistic
        statistic_id = f"{DOMAIN}:profit_total"
        metadata = StatisticMetaData(
            source=DOMAIN,
            statistic_id=statistic_id,
            name="Enion Profit Total",
            unit_of_measurement="EUR",
            has_mean=False,
            has_sum=True,
        )
        cumulative = 0.0
        stat_data = []
        for rec in sorted_records:
            value = float(
                (rec.get("spot_saving") or 0.0)
                + (rec.get("fcr_down_price") or 0.0)
                + (rec.get("fcr_up_price") or 0.0)
            )
            cumulative += value
            try:
                start = datetime.fromisoformat(
                    rec["timestamp"].replace("Z", "+00:00")
                )
            except (KeyError, ValueError):
                continue
            stat_data.append(StatisticData(start=start, state=value, sum=cumulative))

        async_add_external_statistics(self.hass, metadata, stat_data)

    def get_profits_today(self) -> dict[str, float]:
        """Return summed profit fields for the current calendar day (local time)."""
        return self._sum_profits_for_period("today")

    def get_profits_month(self) -> dict[str, float]:
        """Return summed profit fields for the current calendar month (local time)."""
        return self._sum_profits_for_period("month")

    def _sum_profits_for_period(self, period: str) -> dict[str, float]:
        """Sum profit records matching the given period ('today' or 'month').

        Timestamps from the API are UTC; we compare against local date so the
        sensor resets at local midnight rather than UTC midnight.
        """
        import time as _time
        local_now = _time.localtime()
        today_date = (local_now.tm_year, local_now.tm_mon, local_now.tm_mday)
        month_key = (local_now.tm_year, local_now.tm_mon)

        spot = 0.0
        fcr = 0.0
        for rec in self._store.get(DATA_PROFITS, []):
            ts_str = rec.get("timestamp", "")
            try:
                dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                local_dt = _time.localtime(dt.timestamp())
                rec_date = (local_dt.tm_year, local_dt.tm_mon, local_dt.tm_mday)
                rec_month = (local_dt.tm_year, local_dt.tm_mon)
            except (ValueError, AttributeError, OSError):
                continue

            if period == "today" and rec_date != today_date:
                continue
            if period == "month" and rec_month != month_key:
                continue

            spot += float(rec.get("spot_saving") or 0.0)
            fcr += float((rec.get("fcr_down_price") or 0.0) + (rec.get("fcr_up_price") or 0.0))

        return {"spot_saving": spot, "fcr_total": fcr, "total": spot + fcr}

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

    def get_user_info(self) -> dict[str, Any]:
        """Return user account and settings information."""
        return self._store.get(DATA_USER, {})

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
