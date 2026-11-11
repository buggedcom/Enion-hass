"""Tests for the electricity prices REST API endpoint and coordinator integration."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.enion.api import EnionApiError, EnionClient
from custom_components.enion.const import (
    API_PRICES,
    DATA_PRICES,
    DATA_USER,
    DOMAIN,
)
from custom_components.enion.coordinator import EnionCoordinator
from tests.conftest import ME_RESPONSE

SAMPLE_PRICES_RESPONSE = [
    {
        "from": "2026-11-11T20:00:00Z",
        "to": "2026-11-11T20:15:00Z",
        "price": 150.0,
        "forecast": False,
    },
    {
        "from": "2026-11-11T20:15:00Z",
        "to": "2026-11-11T20:30:00Z",
        "price": 180.0,
        "forecast": False,
    },
    {
        "from": "2026-11-11T20:30:00Z",
        "to": "2026-11-11T20:45:00Z",
        "price": 200.0,
        "forecast": False,
    },
    {
        "from": "2026-11-11T20:45:00Z",
        "to": "2026-11-11T21:00:00Z",
        "price": 220.0,
        "forecast": False,
    },
]


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
    client = MagicMock(spec=EnionClient)
    client.ws_token = "test_token"
    client.user_id = "2628"
    client.fetch_profits = AsyncMock(return_value=[])
    client.fetch_prices = AsyncMock(return_value=SAMPLE_PRICES_RESPONSE)
    coord = EnionCoordinator(
        hass=hass,
        session=MagicMock(),
        client=client,
        email="test@enion.fi",
        password="secret",
    )
    coord._last_login_at = time.monotonic()
    coord._store[DATA_USER]["country_iso_3166"] = "FI"
    # Suppress entity notification side-effects in unit tests
    coord.async_set_updated_data = MagicMock()
    return coord


# ---------------------------------------------------------------------------
# EnionClient.fetch_prices
# ---------------------------------------------------------------------------


class TestEnionClientFetchPrices:
    async def test_fetch_prices_success(self):
        session = _make_session(get_data=SAMPLE_PRICES_RESPONSE)
        client = EnionClient(session)
        client._ws_token = "jwt_token"

        from_dt = datetime(2026, 11, 11, 20, 0, tzinfo=timezone.utc)
        to_dt = datetime(2026, 11, 12, 20, 0, tzinfo=timezone.utc)

        result = await client.fetch_prices(from_dt, to_dt, area="FI")

        assert result == SAMPLE_PRICES_RESPONSE
        session.get.assert_called_once()
        call_args = session.get.call_args
        assert call_args[0][0] == API_PRICES
        assert call_args[1]["params"] == {
            "from": "2026-11-11T20:00:00Z",
            "to": "2026-11-12T20:00:00Z",
            "area": "FI",
        }
        assert call_args[1]["headers"]["Authorization"] == "Bearer jwt_token"

    async def test_fetch_prices_error(self):
        session = _make_session(get_status=500)
        client = EnionClient(session)

        from_dt = datetime(2026, 11, 11, 20, 0, tzinfo=timezone.utc)
        to_dt = datetime(2026, 11, 12, 20, 0, tzinfo=timezone.utc)

        with pytest.raises(EnionApiError):
            await client.fetch_prices(from_dt, to_dt, area="FI")


# ---------------------------------------------------------------------------
# Coordinator price fetching and storage
# ---------------------------------------------------------------------------


class TestCoordinatorPrices:
    async def test_fetch_and_store_prices_populates_data_prices(self, coordinator):
        await coordinator._fetch_and_store_prices()

        prices = coordinator._store[DATA_PRICES]
        assert len(prices) == 4
        # Verify timestamps and conversion
        assert prices[0]["price"] == 150.0
        assert prices[0]["ts"] == 1794427200  # 2026-11-11T20:00:00Z
        assert prices[0]["ts_to"] == 1794428100  # 2026-11-11T20:15:00Z

    async def test_get_current_and_next_price_with_quarter_hourly_data(self, coordinator):
        await coordinator._fetch_and_store_prices()

        # Simulate current time being 20:20:00 UTC (between 20:15 and 20:30)
        simulated_now = 1794427200 + 1200
        with patch("time.time", return_value=simulated_now):
            # 180.0 €/MWh -> 18.0 ct/kWh
            assert coordinator.get_current_price() == 18.0
            # Next interval is 20:30 -> 200.0 €/MWh -> 20.0 ct/kWh
            assert coordinator.get_next_price() == 20.0

    async def test_fetch_and_store_prices_handles_api_exception(self, coordinator):
        coordinator._client.fetch_prices = AsyncMock(side_effect=EnionApiError("network error"))
        # Must not raise
        await coordinator._fetch_and_store_prices()
        assert coordinator._store[DATA_PRICES] == []

    async def test_fetch_and_store_prices_relogins_when_token_expired(self, coordinator):
        coordinator._last_login_at = time.monotonic() - 1000
        coordinator._client.login = AsyncMock()

        await coordinator._fetch_and_store_prices()

        coordinator._client.login.assert_awaited_once_with(
            coordinator._email, coordinator._password
        )
