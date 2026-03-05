"""Tests for calendar.py — EnionOptimizerCalendar and EnionWeatherCalendar."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from custom_components.enion.calendar import EnionWeatherCalendar, EnionOptimizerCalendar
from custom_components.enion.const import DATA_WEATHER, DATA_OPTIMIZER


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_coordinator(weather=None, optimizer=None):
    """Return a minimal mock coordinator with the given store data."""
    coord = MagicMock()
    coord.data = {
        DATA_WEATHER: weather or [],
        DATA_OPTIMIZER: optimizer or {},
    }
    # get_optimizer_state is called by EnionOptimizerCalendar; default to empty
    coord.get_optimizer_state.return_value = (None, None, [])
    return coord


def _make_entry():
    entry = MagicMock()
    entry.entry_id = "test_entry"
    return entry


def _ts(dt: datetime) -> int:
    return int(dt.timestamp())


# ---------------------------------------------------------------------------
# EnionWeatherCalendar — _make_event
# ---------------------------------------------------------------------------

class TestWeatherCalendarMakeEvent:
    def _calendar(self, weather=None):
        cal = EnionWeatherCalendar.__new__(EnionWeatherCalendar)
        cal.coordinator = _make_coordinator(weather=weather)
        cal._attr_unique_id = "test_weather"
        return cal

    def test_summary_includes_temp_and_wind(self):
        cal = self._calendar()
        event = cal._make_event({"ts": 1_000_000, "temperature": 5.0, "wind_speed": 3.2})
        assert "5.0°C" in event.summary
        assert "3.2 m/s" in event.summary

    def test_summary_fallback_when_no_fields(self):
        cal = self._calendar()
        event = cal._make_event({"ts": 1_000_000})
        assert event.summary == "Weather Forecast"

    def test_event_duration_is_one_hour(self):
        cal = self._calendar()
        event = cal._make_event({"ts": 1_000_000, "temperature": 3.0})
        assert event.end - event.start == timedelta(hours=1)

    def test_description_includes_all_fields_numeric(self):
        cal = self._calendar()
        event = cal._make_event({
            "ts": 1_000_000,
            "temperature": 5.0,
            "wind_speed": 3.2,
            "wind_dir": 270,
            "sun": 80,
        })
        assert "5.0°C" in event.description
        assert "3.2 m/s" in event.description
        assert "270°" in event.description
        assert "80%" in event.description

    def test_description_string_wind_dir_has_no_degree_sign(self):
        cal = self._calendar()
        event = cal._make_event({
            "ts": 1_000_000,
            "wind_dir": "NW",
            "sun": "PARTLY CLOUDY",
        })
        assert "NW°" not in event.description
        assert "Wind Direction: NW" in event.description
        assert "PARTLY CLOUDY%" not in event.description
        assert "Sun: PARTLY CLOUDY" in event.description

    def test_description_is_none_when_no_fields(self):
        cal = self._calendar()
        event = cal._make_event({"ts": 1_000_000})
        assert event.description is None

    def test_event_times_are_utc_aware(self):
        cal = self._calendar()
        event = cal._make_event({"ts": 1_000_000, "temperature": 1.0})
        assert event.start.tzinfo is not None
        assert event.end.tzinfo is not None


# ---------------------------------------------------------------------------
# EnionWeatherCalendar — event property (current slot)
# ---------------------------------------------------------------------------

class TestWeatherCalendarEventProperty:
    def _calendar(self, weather):
        cal = EnionWeatherCalendar.__new__(EnionWeatherCalendar)
        cal.coordinator = _make_coordinator(weather=weather)
        return cal

    def test_returns_current_hour_event(self):
        now = datetime.now(timezone.utc)
        slot_start = now.replace(minute=0, second=0, microsecond=0)
        weather = [{"ts": _ts(slot_start), "temperature": 7.0, "wind_speed": 2.0}]
        cal = self._calendar(weather)
        event = cal.event
        assert event is not None
        assert "7.0°C" in event.summary

    def test_returns_none_when_no_matching_slot(self):
        # All slots are in the past
        past = datetime(2000, 1, 1, tzinfo=timezone.utc)
        weather = [{"ts": _ts(past), "temperature": 7.0}]
        cal = self._calendar(weather)
        assert cal.event is None

    def test_returns_none_when_weather_empty(self):
        cal = self._calendar([])
        assert cal.event is None


# ---------------------------------------------------------------------------
# EnionWeatherCalendar — async_get_events
# ---------------------------------------------------------------------------

class TestWeatherCalendarGetEvents:
    def _calendar(self, weather):
        cal = EnionWeatherCalendar.__new__(EnionWeatherCalendar)
        cal.coordinator = _make_coordinator(weather=weather)
        return cal

    async def test_returns_events_in_range(self, hass):
        base = datetime(2026, 3, 5, 10, 0, 0, tzinfo=timezone.utc)
        weather = [
            {"ts": _ts(base), "temperature": 5.0},
            {"ts": _ts(base + timedelta(hours=1)), "temperature": 6.0},
            {"ts": _ts(base + timedelta(hours=2)), "temperature": 7.0},
        ]
        cal = self._calendar(weather)
        events = await cal.async_get_events(
            hass,
            start_date=base,
            end_date=base + timedelta(hours=2),
        )
        assert len(events) == 2
        assert "5.0°C" in events[0].summary
        assert "6.0°C" in events[1].summary

    async def test_excludes_events_outside_range(self, hass):
        base = datetime(2026, 3, 5, 10, 0, 0, tzinfo=timezone.utc)
        weather = [
            {"ts": _ts(base - timedelta(hours=1)), "temperature": 3.0},
            {"ts": _ts(base), "temperature": 5.0},
            {"ts": _ts(base + timedelta(hours=5)), "temperature": 9.0},
        ]
        cal = self._calendar(weather)
        events = await cal.async_get_events(
            hass,
            start_date=base,
            end_date=base + timedelta(hours=2),
        )
        assert len(events) == 1
        assert "5.0°C" in events[0].summary

    async def test_returns_empty_list_when_no_weather(self, hass):
        cal = self._calendar([])
        events = await cal.async_get_events(
            hass,
            start_date=datetime(2026, 3, 5, tzinfo=timezone.utc),
            end_date=datetime(2026, 3, 6, tzinfo=timezone.utc),
        )
        assert events == []

    async def test_naive_dates_treated_as_utc(self, hass):
        """async_get_events should accept naive datetimes without crashing."""
        base = datetime(2026, 3, 5, 10, 0, 0, tzinfo=timezone.utc)
        weather = [{"ts": _ts(base), "temperature": 5.0}]
        cal = self._calendar(weather)
        # Pass naive datetimes — the method should normalise them
        events = await cal.async_get_events(
            hass,
            start_date=datetime(2026, 3, 5, 10, 0, 0),
            end_date=datetime(2026, 3, 5, 12, 0, 0),
        )
        assert len(events) == 1

    async def test_updated_forecast_replaces_slot(self, hass):
        """When the same time slot is re-sent, only the latest value appears.

        The coordinator replaces the whole weather list on each WS event, so
        there is never more than one entry per timestamp — this test verifies
        that contract holds at the calendar level too.
        """
        base = datetime(2026, 3, 5, 10, 0, 0, tzinfo=timezone.utc)
        # Simulate an updated forecast: same ts, new temperature
        weather = [{"ts": _ts(base), "temperature": 12.0}]
        cal = self._calendar(weather)
        events = await cal.async_get_events(
            hass,
            start_date=base,
            end_date=base + timedelta(hours=1),
        )
        assert len(events) == 1
        assert "12.0°C" in events[0].summary
