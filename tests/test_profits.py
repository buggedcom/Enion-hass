"""Tests for the profits API endpoint, coordinator integration, and anti-hammer guard."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from custom_components.enion.api import EnionApiError, EnionClient
from custom_components.enion.const import (
    API_PROFITS,
    DATA_PROFITS,
    DOMAIN,
)
from custom_components.enion.coordinator import EnionCoordinator
from tests.conftest import ME_RESPONSE, PROFITS_RESPONSE


# ---------------------------------------------------------------------------
# Helpers (shared with test_api.py pattern)
# ---------------------------------------------------------------------------


def _make_response(status: int = 200, json_data=None) -> MagicMock:
    resp = MagicMock()
    resp.status = status
    resp.json = AsyncMock(return_value=json_data if json_data is not None else [])
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=resp)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


def _make_session(get_status=200, get_data=None) -> MagicMock:
    session = MagicMock()
    session.get.return_value = _make_response(get_status, get_data)
    return session


@pytest.fixture
def coordinator(hass):
    """Coordinator wired to hass with async_set_updated_data suppressed."""
    from custom_components.enion.api import EnionClient as _EC

    client = MagicMock(spec=_EC)
    client.ws_token = "test_token"
    client.user_id = "2628"
    client.fetch_profits = AsyncMock(return_value=PROFITS_RESPONSE)
    coord = EnionCoordinator(
        hass=hass,
        session=MagicMock(),
        client=client,
        email="test@example.com",
        password="secret",
    )
    coord.async_set_updated_data = MagicMock()
    hass.async_create_task = MagicMock(return_value=MagicMock())
    coord._seed_from_me(ME_RESPONSE)
    return coord


# ---------------------------------------------------------------------------
# TestFetchProfitsApi — EnionClient.fetch_profits()
# ---------------------------------------------------------------------------


class TestFetchProfitsApi:
    def _make_client(self, status=200, data=None) -> EnionClient:
        session = _make_session(get_status=status, get_data=data)
        client = EnionClient(session)
        client._ws_token = "test_token"
        return client

    async def test_success_returns_list(self):
        client = self._make_client(data=PROFITS_RESPONSE)
        from_dt = datetime(2026, 1, 1, tzinfo=timezone.utc)
        to_dt = datetime(2026, 3, 19, tzinfo=timezone.utc)

        result = await client.fetch_profits(104230, from_dt, to_dt)

        assert result == PROFITS_RESPONSE

    async def test_sends_correct_url_with_port_id(self):
        client = self._make_client(data=[])
        from_dt = datetime(2026, 1, 1, tzinfo=timezone.utc)
        to_dt = datetime(2026, 3, 19, tzinfo=timezone.utc)

        await client.fetch_profits(104230, from_dt, to_dt)

        call_args = client._session.get.call_args
        url = call_args[0][0]
        assert url == f"{API_PROFITS}/104230"

    async def test_sends_correct_query_params(self):
        client = self._make_client(data=[])
        from_dt = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        to_dt = datetime(2026, 3, 19, 22, 0, 0, tzinfo=timezone.utc)

        await client.fetch_profits(104230, from_dt, to_dt, steps="day")

        params = client._session.get.call_args[1]["params"]
        assert params["from"] == "2026-01-01T00:00:00.000Z"
        assert params["to"] == "2026-03-19T22:00:00.000Z"
        assert params["steps"] == "day"

    async def test_sends_authorization_header(self):
        client = self._make_client(data=[])
        client._ws_token = "my_jwt_token"
        from_dt = datetime(2026, 1, 1, tzinfo=timezone.utc)
        to_dt = datetime(2026, 3, 19, tzinfo=timezone.utc)

        await client.fetch_profits(104230, from_dt, to_dt)

        headers = client._session.get.call_args[1]["headers"]
        assert headers.get("Authorization") == "Bearer my_jwt_token"

    async def test_no_auth_header_when_token_missing(self):
        client = self._make_client(data=[])
        client._ws_token = None
        from_dt = datetime(2026, 1, 1, tzinfo=timezone.utc)
        to_dt = datetime(2026, 3, 19, tzinfo=timezone.utc)

        await client.fetch_profits(104230, from_dt, to_dt)

        headers = client._session.get.call_args[1]["headers"]
        assert "Authorization" not in headers

    async def test_non_200_raises_api_error(self):
        client = self._make_client(status=500)
        from_dt = datetime(2026, 1, 1, tzinfo=timezone.utc)
        to_dt = datetime(2026, 3, 19, tzinfo=timezone.utc)

        with pytest.raises(EnionApiError):
            await client.fetch_profits(104230, from_dt, to_dt)


# ---------------------------------------------------------------------------
# TestFetchAndStoreProfits — coordinator._fetch_and_store_profits()
# ---------------------------------------------------------------------------


class TestFetchAndStoreProfits:
    async def test_stores_profits_in_data_store(self, coordinator):
        with patch.object(coordinator, "_inject_profit_statistics"):
            await coordinator._fetch_and_store_profits()

        assert coordinator._store[DATA_PROFITS] == PROFITS_RESPONSE

    async def test_notifies_listeners_after_fetch(self, coordinator):
        with patch.object(coordinator, "_inject_profit_statistics"):
            await coordinator._fetch_and_store_profits()

        coordinator.async_set_updated_data.assert_called_once()

    async def test_warns_and_returns_if_battery_port_missing(self, coordinator):
        coordinator._store["ports"] = {}  # empty port store

        with patch("custom_components.enion.coordinator._LOGGER") as mock_log:
            await coordinator._fetch_and_store_profits()

        mock_log.warning.assert_called_once()
        coordinator._client.fetch_profits.assert_not_awaited()

    async def test_calls_inject_statistics_with_fetched_records(self, coordinator):
        with patch.object(coordinator, "_inject_profit_statistics") as mock_inject:
            await coordinator._fetch_and_store_profits()

        mock_inject.assert_called_once_with(PROFITS_RESPONSE)

    async def test_api_error_is_caught_and_logged(self, coordinator):
        coordinator._client.fetch_profits = AsyncMock(
            side_effect=EnionApiError("server error")
        )
        with patch("custom_components.enion.coordinator._LOGGER") as mock_log:
            # Must not raise
            await coordinator._fetch_and_store_profits()

        mock_log.error.assert_called_once()

    async def test_fetches_90_day_window(self, coordinator):
        with patch.object(coordinator, "_inject_profit_statistics"):
            await coordinator._fetch_and_store_profits()

        call_args = coordinator._client.fetch_profits.call_args
        from_dt = call_args[0][1]
        to_dt = call_args[0][2]
        delta = to_dt - from_dt
        assert 89 <= delta.days <= 90


# ---------------------------------------------------------------------------
# TestProfitSummaries — get_profits_today() / get_profits_month()
# ---------------------------------------------------------------------------


class TestProfitSummaries:
    def _set_profits(self, coordinator, records):
        coordinator._store[DATA_PROFITS] = records

    def _record_for_local_date(self, year, month, day, spot=1.0, fcr_down=0.5, fcr_up=0.3):
        """Create a profit record whose timestamp falls on the given local calendar date."""
        # Use noon UTC — this should land on the same calendar date in most time zones
        dt = datetime(year, month, day, 12, 0, 0, tzinfo=timezone.utc)
        return {
            "timestamp": dt.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            "batt_power": 0.0,
            "spot_saving": spot,
            "fcr_down_power": 1000.0,
            "fcr_down_price": fcr_down,
            "fcr_up_power": 1000.0,
            "fcr_up_price": fcr_up,
        }

    async def test_get_profits_today_sums_todays_records(self, coordinator):
        import time

        local_now = time.localtime()
        rec = self._record_for_local_date(
            local_now.tm_year, local_now.tm_mon, local_now.tm_mday,
            spot=2.5, fcr_down=1.0, fcr_up=0.5
        )
        self._set_profits(coordinator, [rec])

        result = coordinator.get_profits_today()

        assert result["spot_saving"] == pytest.approx(2.5)
        assert result["fcr_total"] == pytest.approx(1.5)
        assert result["total"] == pytest.approx(4.0)

    async def test_get_profits_today_excludes_other_days(self, coordinator):
        import time

        local_now = time.localtime()
        yesterday = datetime(
            local_now.tm_year, local_now.tm_mon, local_now.tm_mday,
            12, 0, 0, tzinfo=timezone.utc
        ) - timedelta(days=1)
        rec = {
            "timestamp": yesterday.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            "spot_saving": 9.99, "fcr_down_price": 9.99, "fcr_up_price": 9.99,
        }
        self._set_profits(coordinator, [rec])

        result = coordinator.get_profits_today()

        assert result["spot_saving"] == 0.0
        assert result["fcr_total"] == 0.0

    async def test_get_profits_month_sums_all_month_records(self, coordinator):
        import time

        local_now = time.localtime()
        records = [
            self._record_for_local_date(local_now.tm_year, local_now.tm_mon, 1, spot=1.0),
            self._record_for_local_date(local_now.tm_year, local_now.tm_mon, 2, spot=2.0),
            self._record_for_local_date(local_now.tm_year, local_now.tm_mon, 3, spot=3.0),
        ]
        self._set_profits(coordinator, records)

        result = coordinator.get_profits_month()

        assert result["spot_saving"] == pytest.approx(6.0)

    async def test_get_profits_returns_zeros_when_fcr_not_settled(self, coordinator):
        import time

        local_now = time.localtime()
        rec = self._record_for_local_date(
            local_now.tm_year, local_now.tm_mon, local_now.tm_mday,
            spot=1.0, fcr_down=0.0, fcr_up=0.0
        )
        self._set_profits(coordinator, [rec])

        result = coordinator.get_profits_today()

        assert result["fcr_total"] == 0.0
        assert result["spot_saving"] == pytest.approx(1.0)

    async def test_get_profits_today_empty_store(self, coordinator):
        self._set_profits(coordinator, [])

        result = coordinator.get_profits_today()

        assert result == {"spot_saving": 0.0, "fcr_total": 0.0, "total": 0.0}

    async def test_get_profits_handles_malformed_timestamp(self, coordinator):
        self._set_profits(coordinator, [
            {"timestamp": "not-a-date", "spot_saving": 9.99, "fcr_down_price": 1.0, "fcr_up_price": 1.0},
        ])

        # Must not raise
        result = coordinator.get_profits_today()
        assert result["spot_saving"] == 0.0

    async def test_negative_spot_saving_is_included(self, coordinator):
        import time

        local_now = time.localtime()
        rec = self._record_for_local_date(
            local_now.tm_year, local_now.tm_mon, local_now.tm_mday,
            spot=-0.5, fcr_down=0.0, fcr_up=0.0
        )
        self._set_profits(coordinator, [rec])

        result = coordinator.get_profits_today()

        assert result["spot_saving"] == pytest.approx(-0.5)


# ---------------------------------------------------------------------------
# TestProfitStatisticsInjection — coordinator._inject_profit_statistics()
# ---------------------------------------------------------------------------


class TestProfitStatisticsInjection:
    """Patch the recorder symbols at their canonical import paths since the
    coordinator imports them lazily inside _inject_profit_statistics()."""

    _PATCH_ADD = "homeassistant.components.recorder.statistics.async_add_external_statistics"
    _PATCH_GET = "homeassistant.components.recorder.get_instance"

    async def test_inject_calls_async_add_external_statistics(self, coordinator):
        with patch(self._PATCH_ADD) as mock_add, patch(self._PATCH_GET):
            coordinator._inject_profit_statistics(PROFITS_RESPONSE)

        assert mock_add.call_count == 4  # spot_saving, fcr_down, fcr_up, total

    async def test_inject_called_with_correct_statistic_ids(self, coordinator):
        with patch(self._PATCH_ADD) as mock_add, patch(self._PATCH_GET):
            coordinator._inject_profit_statistics(PROFITS_RESPONSE)

        # StatisticMetaData is a TypedDict — use dict access
        stat_ids = {
            call_args[0][1]["statistic_id"]
            for call_args in mock_add.call_args_list
        }
        assert f"{DOMAIN}:profit_spot_saving" in stat_ids
        assert f"{DOMAIN}:profit_fcr_down" in stat_ids
        assert f"{DOMAIN}:profit_fcr_up" in stat_ids
        assert f"{DOMAIN}:profit_total" in stat_ids

    async def test_inject_uses_eur_unit(self, coordinator):
        with patch(self._PATCH_ADD) as mock_add, patch(self._PATCH_GET):
            coordinator._inject_profit_statistics(PROFITS_RESPONSE)

        for call_args in mock_add.call_args_list:
            metadata = call_args[0][1]
            assert metadata["unit_of_measurement"] == "EUR"

    async def test_cumulative_sum_is_calculated_correctly(self, coordinator):
        records = [
            {
                "timestamp": "2026-03-08T22:00:00.000Z",
                "spot_saving": 1.0, "fcr_down_price": 0.0, "fcr_up_price": 0.0,
            },
            {
                "timestamp": "2026-03-09T22:00:00.000Z",
                "spot_saving": 2.0, "fcr_down_price": 0.0, "fcr_up_price": 0.0,
            },
        ]
        captured_stat_data = {}

        # StatisticMetaData and StatisticData are TypedDicts — use dict access
        def capture(hass, metadata, stat_data):
            captured_stat_data[metadata["statistic_id"]] = stat_data

        with patch(self._PATCH_ADD, side_effect=capture), patch(self._PATCH_GET):
            coordinator._inject_profit_statistics(records)

        spot_stats = captured_stat_data[f"{DOMAIN}:profit_spot_saving"]
        assert spot_stats[0]["sum"] == pytest.approx(1.0)
        assert spot_stats[1]["sum"] == pytest.approx(3.0)

    async def test_empty_records_does_not_call_inject(self, coordinator):
        with patch(self._PATCH_ADD) as mock_add, patch(self._PATCH_GET):
            coordinator._inject_profit_statistics([])

        mock_add.assert_not_called()

    async def test_negative_values_included_in_sum(self, coordinator):
        records = [
            {
                "timestamp": "2026-03-08T22:00:00.000Z",
                "spot_saving": 2.0, "fcr_down_price": 0.0, "fcr_up_price": 0.0,
            },
            {
                "timestamp": "2026-03-09T22:00:00.000Z",
                "spot_saving": -0.5, "fcr_down_price": 0.0, "fcr_up_price": 0.0,
            },
        ]
        captured_stat_data = {}

        def capture(hass, metadata, stat_data):
            captured_stat_data[metadata["statistic_id"]] = stat_data

        with patch(self._PATCH_ADD, side_effect=capture), patch(self._PATCH_GET):
            coordinator._inject_profit_statistics(records)

        spot_stats = captured_stat_data[f"{DOMAIN}:profit_spot_saving"]
        assert spot_stats[1]["sum"] == pytest.approx(1.5)

    async def test_records_sorted_by_timestamp_before_cumulation(self, coordinator):
        """Out-of-order records must be sorted before building cumulative sums."""
        records = [
            {
                "timestamp": "2026-03-10T22:00:00.000Z",  # later first
                "spot_saving": 3.0, "fcr_down_price": 0.0, "fcr_up_price": 0.0,
            },
            {
                "timestamp": "2026-03-08T22:00:00.000Z",
                "spot_saving": 1.0, "fcr_down_price": 0.0, "fcr_up_price": 0.0,
            },
        ]
        captured_stat_data = {}

        def capture(hass, metadata, stat_data):
            captured_stat_data[metadata["statistic_id"]] = stat_data

        with patch(self._PATCH_ADD, side_effect=capture), patch(self._PATCH_GET):
            coordinator._inject_profit_statistics(records)

        spot_stats = captured_stat_data[f"{DOMAIN}:profit_spot_saving"]
        # First entry chronologically should be the 1.0 record
        assert spot_stats[0]["sum"] == pytest.approx(1.0)
        assert spot_stats[1]["sum"] == pytest.approx(4.0)


# ---------------------------------------------------------------------------
# TestProfitPollingGuard — anti-hammer + timer management
# ---------------------------------------------------------------------------


class TestProfitPollingGuard:
    async def test_concurrent_fetch_is_skipped(self, coordinator):
        coordinator._profits_fetch_in_progress = True

        await coordinator._fetch_and_store_profits()

        coordinator._client.fetch_profits.assert_not_awaited()

    async def test_flag_is_false_after_successful_fetch(self, coordinator):
        with patch.object(coordinator, "_inject_profit_statistics"):
            await coordinator._fetch_and_store_profits()

        assert coordinator._profits_fetch_in_progress is False

    async def test_flag_reset_after_failed_fetch(self, coordinator):
        coordinator._client.fetch_profits = AsyncMock(
            side_effect=EnionApiError("boom")
        )

        with patch("custom_components.enion.coordinator._LOGGER"):
            await coordinator._fetch_and_store_profits()

        assert coordinator._profits_fetch_in_progress is False

    async def test_hourly_timer_registered_on_setup(self, coordinator):
        coordinator._client.login = AsyncMock()
        coordinator._client.fetch_me = AsyncMock(return_value=ME_RESPONSE)

        with patch(
            "custom_components.enion.coordinator.async_track_time_interval"
        ) as mock_track, patch.object(
            coordinator, "_connect_ws", new_callable=AsyncMock
        ), patch.object(
            coordinator, "_fetch_and_store_profits", new_callable=AsyncMock
        ):
            mock_track.return_value = MagicMock()
            await coordinator.async_setup()

        mock_track.assert_called_once()
        _, interval = mock_track.call_args[0][0], mock_track.call_args[0][2]
        assert interval == timedelta(hours=1)

    async def test_timer_unsubscribed_on_shutdown(self, coordinator):
        unsub_mock = MagicMock()
        coordinator._profits_unsub = unsub_mock
        coordinator._ws = MagicMock()
        coordinator._ws.disconnect = AsyncMock()

        await coordinator.async_shutdown()

        unsub_mock.assert_called_once()
        assert coordinator._profits_unsub is None

    async def test_shutdown_with_no_timer_does_not_raise(self, coordinator):
        coordinator._profits_unsub = None
        coordinator._ws = MagicMock()
        coordinator._ws.disconnect = AsyncMock()

        # Must not raise
        await coordinator.async_shutdown()

    async def test_setup_registers_exactly_one_timer(self, coordinator):
        """Calling async_setup once registers exactly one interval subscription."""
        coordinator._client.login = AsyncMock()
        coordinator._client.fetch_me = AsyncMock(return_value=ME_RESPONSE)

        call_count = 0

        def track_side_effect(hass, cb, interval):
            nonlocal call_count
            call_count += 1
            return MagicMock()

        with patch(
            "custom_components.enion.coordinator.async_track_time_interval",
            side_effect=track_side_effect,
        ), patch.object(
            coordinator, "_connect_ws", new_callable=AsyncMock
        ), patch.object(
            coordinator, "_fetch_and_store_profits", new_callable=AsyncMock
        ):
            await coordinator.async_setup()

        assert call_count == 1

    async def test_scheduled_fetch_calls_fetch_and_store(self, coordinator):
        """_scheduled_profits_fetch is the timer callback and must delegate."""
        with patch.object(
            coordinator, "_fetch_and_store_profits", new_callable=AsyncMock
        ) as mock_fetch:
            await coordinator._scheduled_profits_fetch()

        mock_fetch.assert_awaited_once()
