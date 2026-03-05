"""Unit tests for coordinator.py — EnionCoordinator."""
from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.enion.api import EnionClient
from custom_components.enion.const import (
    DATA_DEVICE,
    DATA_OPTIMIZER,
    DATA_PORTS,
    DATA_PRICES,
    DATA_WEATHER,
)
from custom_components.enion.coordinator import (
    EnionCoordinator,
    _RECONNECT_DELAY_BASE,
    _RECONNECT_DELAY_MAX,
    _TOKEN_MAX_AGE,
)
from tests.conftest import (
    ME_RESPONSE,
    WS_DEVICE_EVENT,
    WS_UPDATE_BATTERY,
    WS_UPDATE_PRICES,
    WS_UPDATE_WEATHER,
)


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------


@pytest.fixture
async def coordinator(hass):
    """Create an EnionCoordinator wired to the real hass instance.

    hass.async_create_task is replaced with a MagicMock so backoff tests
    can inspect the coroutine arguments without scheduling real tasks.
    """
    client = MagicMock(spec=EnionClient)
    client.ws_token = "test_token"
    client.user_id = "2628"
    coord = EnionCoordinator(
        hass=hass,
        session=MagicMock(),
        client=client,
        email="test@example.com",
        password="secret",
    )
    # Suppress HA internals — we test the store directly
    coord.async_set_updated_data = MagicMock()
    # Replace async_create_task with a mock so backoff tests can introspect
    hass.async_create_task = MagicMock(return_value=MagicMock())
    return coord


# ---------------------------------------------------------------------------
# _seed_from_me
# ---------------------------------------------------------------------------


class TestSeedFromMe:
    async def test_populates_device_meta(self, coordinator):
        coordinator._seed_from_me(ME_RESPONSE)

        assert coordinator.device_meta["manufacturer"] == "Sunergos"
        assert coordinator.device_meta["model"] == "Mini 3.0"
        assert coordinator.device_meta["hw_id"] == "0B8D7EFB"
        assert coordinator.device_meta["device_id"] == 2392

    async def test_populates_device_online_status(self, coordinator):
        coordinator._seed_from_me(ME_RESPONSE)

        device = coordinator._store[DATA_DEVICE]
        assert device["online"] is True
        assert device["firmware_version"] == "DDBB83BE33D7B2BC"
        assert device["hw_id"] == "0B8D7EFB"

    async def test_populates_port_store_with_all_ports(self, coordinator):
        coordinator._seed_from_me(ME_RESPONSE)

        ports = coordinator._store[DATA_PORTS]
        expected_port_ids = {p["id"] for p in ME_RESPONSE["devices"][0]["ports"]}
        assert set(ports.keys()) == expected_port_ids

    async def test_port_store_entries_have_port_number(self, coordinator):
        coordinator._seed_from_me(ME_RESPONSE)

        assert coordinator._store[DATA_PORTS][104225]["port_number"] == "3/0"
        assert coordinator._store[DATA_PORTS][104230]["port_number"] == "22/0"

    async def test_no_devices_logs_warning(self, coordinator):
        with patch("custom_components.enion.coordinator._LOGGER") as mock_log:
            coordinator._seed_from_me({**ME_RESPONSE, "devices": []})
            mock_log.warning.assert_called_once()

    async def test_device_meta_empty_without_device_spec(self, coordinator):
        no_spec = {
            **ME_RESPONSE,
            "devices": [{**ME_RESPONSE["devices"][0], "device_spec": None}],
        }
        coordinator._seed_from_me(no_spec)
        # Falls back to defaults
        assert coordinator.device_meta["manufacturer"] == "Sunergos"
        assert coordinator.device_meta["model"] == "Enion"


# ---------------------------------------------------------------------------
# _handle_update
# ---------------------------------------------------------------------------


class TestHandleUpdate:
    async def test_updates_port_values_in_store(self, coordinator):
        coordinator._seed_from_me(ME_RESPONSE)
        coordinator._handle_update(WS_UPDATE_BATTERY)

        values = coordinator._store[DATA_PORTS][104230]["values"]
        assert values["soc"] == 72
        assert values["power"] == -1200

    async def test_notifies_listeners(self, coordinator):
        coordinator._seed_from_me(ME_RESPONSE)
        coordinator._handle_update(WS_UPDATE_BATTERY)

        coordinator.async_set_updated_data.assert_called_once()

    async def test_expands_prices_into_data_prices(self, coordinator):
        coordinator._seed_from_me(ME_RESPONSE)
        coordinator._handle_update(WS_UPDATE_PRICES)

        prices = coordinator._store[DATA_PRICES]
        assert len(prices) == 4
        assert prices[0]["price"] == 10.5
        assert prices[0]["ts"] == 1_700_000_000
        assert prices[1]["ts"] == 1_700_000_000 + 3600

    async def test_expands_weather_into_data_weather(self, coordinator):
        coordinator._seed_from_me(ME_RESPONSE)
        coordinator._handle_update(WS_UPDATE_WEATHER)

        weather = coordinator._store[DATA_WEATHER]
        assert len(weather) == 2
        assert weather[0]["temperature"] == 3.5
        assert weather[0]["ts"] == 1_700_000_000

    async def test_empty_values_are_ignored(self, coordinator):
        coordinator._seed_from_me(ME_RESPONSE)
        coordinator.async_set_updated_data.reset_mock()

        coordinator._handle_update({
            "port_id": 104225,
            "port_number": "3/0",
            "values": {},
        })

        coordinator.async_set_updated_data.assert_not_called()

    async def test_missing_port_id_is_ignored(self, coordinator):
        coordinator._seed_from_me(ME_RESPONSE)
        coordinator.async_set_updated_data.reset_mock()

        coordinator._handle_update({"port_number": "3/0", "values": {"soc": 80}})

        coordinator.async_set_updated_data.assert_not_called()

    async def test_prices_not_set_without_base_ts(self, coordinator):
        coordinator._seed_from_me(ME_RESPONSE)
        coordinator._handle_update({
            **WS_UPDATE_PRICES,
            "values": {"prices": [1.0, 2.0], "timestep": 3600},  # no base_ts
        })

        assert coordinator._store[DATA_PRICES] == []


# ---------------------------------------------------------------------------
# _handle_device
# ---------------------------------------------------------------------------


class TestHandleDevice:
    async def test_updates_device_store(self, coordinator):
        coordinator._handle_device(WS_DEVICE_EVENT)

        device = coordinator._store[DATA_DEVICE]
        assert device["online"] is True
        assert device["last_data"] == "2026-03-05T13:00:00Z"
        assert device["firmware_version"] == "DDBB83BE33D7B2BC"
        assert device["hw_id"] == "0B8D7EFB"

    async def test_notifies_listeners(self, coordinator):
        coordinator._handle_device(WS_DEVICE_EVENT)
        coordinator.async_set_updated_data.assert_called_once()

    async def test_device_offline(self, coordinator):
        coordinator._handle_device({
            **WS_DEVICE_EVENT,
            "values": {**WS_DEVICE_EVENT["values"], "online": False},
        })
        assert coordinator._store[DATA_DEVICE]["online"] is False


# ---------------------------------------------------------------------------
# find_port_by_prefix
# ---------------------------------------------------------------------------


class TestFindPortByPrefix:
    async def test_finds_existing_port(self, coordinator):
        coordinator._seed_from_me(ME_RESPONSE)
        result = coordinator.find_port_by_prefix("22", "0")
        assert result == 104230

    async def test_returns_none_for_missing_port(self, coordinator):
        coordinator._seed_from_me(ME_RESPONSE)
        result = coordinator.find_port_by_prefix("99", "0")
        assert result is None

    async def test_finds_relay_port(self, coordinator):
        coordinator._seed_from_me(ME_RESPONSE)
        result = coordinator.find_port_by_prefix("3", "0")
        assert result == 104225


# ---------------------------------------------------------------------------
# get_current_price / get_next_price
# ---------------------------------------------------------------------------


class TestPricing:
    def _set_prices(self, coordinator, base_ts: int, prices: list[float]):
        coordinator._store[DATA_PRICES] = [
            {"ts": base_ts + i * 3600, "price": p}
            for i, p in enumerate(prices)
        ]

    async def test_get_current_price(self, coordinator):
        # Set a price window that contains "now"
        now = int(time.time())
        self._set_prices(coordinator, now - 1800, [12.5, 14.0])

        assert coordinator.get_current_price() == 12.5

    async def test_get_next_price(self, coordinator):
        now = int(time.time())
        self._set_prices(coordinator, now - 1800, [12.5, 14.0])

        assert coordinator.get_next_price() == 14.0

    async def test_returns_none_when_no_data(self, coordinator):
        assert coordinator.get_current_price() is None
        assert coordinator.get_next_price() is None

    async def test_returns_none_when_all_prices_expired(self, coordinator):
        old_ts = int(time.time()) - 7200
        self._set_prices(coordinator, old_ts, [10.0])

        assert coordinator.get_current_price() is None


# ---------------------------------------------------------------------------
# Reconnect backoff and task deduplication
# ---------------------------------------------------------------------------


class TestReconnectBackoff:
    async def test_first_disconnect_uses_base_delay(self, coordinator):
        coordinator._reconnect_attempt = 0
        coordinator._on_ws_disconnect()

        mock_hass = coordinator.hass
        assert mock_hass.async_create_task.called
        # The delay passed to _reconnect should be BASE * 2^0 = 30
        coro = mock_hass.async_create_task.call_args[0][0]
        assert coro.cr_frame.f_locals.get("delay") == _RECONNECT_DELAY_BASE
        coro.close()

    async def test_backoff_doubles_each_attempt(self, coordinator):
        # 30*2^0=30, 30*2^1=60, ..., 30*2^4=480, 30*2^5=960→capped 600
        for attempt, expected_delay in enumerate([30, 60, 120, 240, 480, 600]):
            coordinator._reconnect_attempt = attempt
            coordinator.hass.async_create_task.reset_mock()
            coordinator._on_ws_disconnect()
            coro = coordinator.hass.async_create_task.call_args[0][0]
            actual_delay = coro.cr_frame.f_locals.get("delay")
            assert actual_delay == expected_delay, f"attempt={attempt}"
            coro.close()  # clean up the unawaited coroutine

    async def test_backoff_capped_at_max(self, coordinator):
        coordinator._reconnect_attempt = 100
        coordinator._on_ws_disconnect()
        coro = coordinator.hass.async_create_task.call_args[0][0]
        assert coro.cr_frame.f_locals["delay"] == _RECONNECT_DELAY_MAX
        coro.close()

    async def test_existing_task_cancelled_before_new_one(self, coordinator):
        existing_task = MagicMock()
        existing_task.done.return_value = False
        coordinator._reconnect_task = existing_task

        coordinator._on_ws_disconnect()

        existing_task.cancel.assert_called_once()
        coordinator.hass.async_create_task.call_args[0][0].close()

    async def test_done_task_not_cancelled(self, coordinator):
        done_task = MagicMock()
        done_task.done.return_value = True
        coordinator._reconnect_task = done_task

        coordinator._on_ws_disconnect()

        done_task.cancel.assert_not_called()
        coordinator.hass.async_create_task.call_args[0][0].close()


class TestReconnectLogic:
    async def test_resets_attempt_on_successful_connect(self, coordinator):
        coordinator._reconnect_attempt = 3

        # Patch EnionWebSocket so _connect_ws runs fully (including the reset)
        # without opening a real WebSocket connection.
        mock_ws_instance = MagicMock()
        mock_ws_instance.connect = AsyncMock()
        with patch("custom_components.enion.coordinator.EnionWebSocket", return_value=mock_ws_instance):
            await coordinator._reconnect(0)

        assert coordinator._reconnect_attempt == 0

    async def test_relogins_when_token_is_stale(self, coordinator):
        coordinator._last_login_at = time.monotonic() - (_TOKEN_MAX_AGE + 10)
        coordinator._client.login = AsyncMock(return_value={"token": "new"})

        with patch.object(coordinator, "_connect_ws", new_callable=AsyncMock):
            await coordinator._reconnect(0)

        coordinator._client.login.assert_awaited_once_with(
            "test@example.com", "secret"
        )

    async def test_skips_relogin_when_token_is_fresh(self, coordinator):
        coordinator._last_login_at = time.monotonic()  # just logged in
        coordinator._client.login = AsyncMock(return_value={"token": "fresh"})

        with patch.object(coordinator, "_connect_ws", new_callable=AsyncMock):
            await coordinator._reconnect(0)

        coordinator._client.login.assert_not_awaited()

    async def test_reconnect_schedules_next_attempt_on_failure(self, coordinator):
        coordinator._client.login = AsyncMock(side_effect=Exception("network down"))
        coordinator._last_login_at = 0  # force re-login

        with patch.object(coordinator, "_on_ws_disconnect") as mock_disconnect:
            await coordinator._reconnect(0)
            mock_disconnect.assert_called_once()

    async def test_reconnect_returns_early_if_sleep_cancelled(self, coordinator):
        coordinator._client.login = AsyncMock()

        async def cancel_sleep(delay):
            raise asyncio.CancelledError

        with patch("custom_components.enion.coordinator.asyncio.sleep", side_effect=cancel_sleep):
            with patch.object(coordinator, "_connect_ws", new_callable=AsyncMock) as mock_connect:
                await coordinator._reconnect(30)
                mock_connect.assert_not_awaited()


# ---------------------------------------------------------------------------
# async_shutdown
# ---------------------------------------------------------------------------


class TestShutdown:
    async def test_cancels_pending_reconnect_task(self, coordinator):
        task = MagicMock()
        task.done.return_value = False
        coordinator._reconnect_task = task
        coordinator._ws = MagicMock()
        coordinator._ws.disconnect = AsyncMock()

        await coordinator.async_shutdown()

        task.cancel.assert_called_once()

    async def test_disconnects_websocket(self, coordinator):
        coordinator._reconnect_task = None
        mock_ws = MagicMock()
        mock_ws.disconnect = AsyncMock()
        coordinator._ws = mock_ws

        await coordinator.async_shutdown()

        mock_ws.disconnect.assert_awaited_once()

    async def test_does_not_cancel_done_task(self, coordinator):
        done_task = MagicMock()
        done_task.done.return_value = True
        coordinator._reconnect_task = done_task
        coordinator._ws = MagicMock()
        coordinator._ws.disconnect = AsyncMock()

        await coordinator.async_shutdown()

        done_task.cancel.assert_not_called()
