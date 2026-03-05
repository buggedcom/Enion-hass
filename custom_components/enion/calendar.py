"""Calendar platform for Enion battery optimizer schedule."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, DATA_WEATHER
from .coordinator import EnionCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Enion calendar."""
    coordinator: EnionCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        EnionOptimizerCalendar(coordinator, entry),
        EnionWeatherCalendar(coordinator, entry),
    ])


class EnionOptimizerCalendar(CoordinatorEntity[EnionCoordinator], CalendarEntity):
    """Calendar showing battery optimizer schedule."""

    _attr_name = "Battery Optimizer Schedule"

    def __init__(self, coordinator: EnionCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_battery_optimizer_schedule"
        self.entry = entry

    @property
    def event(self) -> CalendarEvent | None:
        """Return the next/current event."""
        _, next_event_time, schedule = self.coordinator.get_optimizer_state()

        if not schedule:
            return None

        # Find the current or next event
        now = datetime.now(timezone.utc)
        for i, event_data in enumerate(schedule):
            try:
                # Parse the ISO 8601 timestamp
                event_time = datetime.fromisoformat(
                    event_data["time"].replace("Z", "+00:00")
                )

                # Find next event or current event
                if event_time > now:
                    # This is a future event
                    duration_hours = 1  # Events last 1 hour
                    if i + 1 < len(schedule):
                        # If there's a next event, duration is until then
                        next_time = datetime.fromisoformat(
                            schedule[i + 1]["time"].replace("Z", "+00:00")
                        )
                        duration = next_time - event_time
                    else:
                        duration = None

                    return CalendarEvent(
                        summary=f"Optimizer: {event_data['state']}",
                        start=event_time,
                        end=event_time + (duration if duration is not None else timedelta(hours=1)),
                        description=f"Battery Optimizer State: {event_data['state']}",
                    )
            except (ValueError, KeyError):
                continue

        return None

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        """Return events in the given date range."""
        _, _, schedule = self.coordinator.get_optimizer_state()
        events = []

        for i, event_data in enumerate(schedule):
            try:
                # Parse the ISO 8601 timestamp
                event_time = datetime.fromisoformat(
                    event_data["time"].replace("Z", "+00:00")
                )

                # Ensure start_date and end_date are timezone-aware
                if start_date.tzinfo is None:
                    start_date = start_date.replace(tzinfo=timezone.utc)
                if end_date.tzinfo is None:
                    end_date = end_date.replace(tzinfo=timezone.utc)

                # Calculate event duration
                if i + 1 < len(schedule):
                    # Duration until next event
                    next_time = datetime.fromisoformat(
                        schedule[i + 1]["time"].replace("Z", "+00:00")
                    )
                    end_time = next_time
                else:
                    # Default 1 hour duration for last event
                    end_time = event_time + timedelta(hours=1)

                # Skip events outside the requested range
                if event_time >= end_date:
                    continue
                if end_time <= start_date:
                    continue

                event = CalendarEvent(
                    summary=f"Optimizer: {event_data['state']}",
                    start=event_time,
                    end=end_time,
                    description=f"Battery Optimizer State: {event_data['state']}",
                )
                events.append(event)
            except (ValueError, KeyError):
                _LOGGER.warning("Failed to parse optimizer event: %s", event_data)
                continue

        return events


class EnionWeatherCalendar(CoordinatorEntity[EnionCoordinator], CalendarEntity):
    """Calendar showing the hourly weather forecast from the Enion cloud.

    Each event covers a one-hour slot.  When the Enion cloud pushes an updated
    forecast for a slot that already exists, the coordinator replaces the entire
    weather list, so the calendar automatically reflects the latest values —
    there is no risk of duplicate events for the same time slot.
    """

    _attr_name = "Weather Forecast"

    def __init__(self, coordinator: EnionCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_weather_forecast"
        self.entry = entry

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _make_event(self, weather_entry: dict) -> CalendarEvent:
        """Build a CalendarEvent from a single weather store entry."""
        ts = weather_entry["ts"]
        start = datetime.fromtimestamp(ts, tz=timezone.utc)
        end = start + timedelta(hours=1)

        temp = weather_entry.get("temperature")
        wind = weather_entry.get("wind_speed")

        # Compact summary shown in calendar grid cells
        parts = []
        if temp is not None:
            parts.append(f"{temp}°C")
        if wind is not None:
            parts.append(f"{wind} m/s")
        summary = "Weather: " + ", ".join(parts) if parts else "Weather Forecast"

        # Detailed description shown when the event is expanded
        desc_lines = []
        if temp is not None:
            desc_lines.append(f"Temperature: {temp}°C")
        if wind is not None:
            desc_lines.append(f"Wind Speed: {wind} m/s")
        wind_dir = weather_entry.get("wind_dir")
        if wind_dir is not None:
            unit = "°" if isinstance(wind_dir, (int, float)) else ""
            desc_lines.append(f"Wind Direction: {wind_dir}{unit}")
        sun = weather_entry.get("sun")
        if sun is not None:
            unit = "%" if isinstance(sun, (int, float)) else ""
            desc_lines.append(f"Sun: {sun}{unit}")
        description = "\n".join(desc_lines) or None

        return CalendarEvent(
            summary=summary,
            start=start,
            end=end,
            description=description,
        )

    # ------------------------------------------------------------------
    # CalendarEntity interface
    # ------------------------------------------------------------------

    @property
    def event(self) -> CalendarEvent | None:
        """Return the weather event covering the current moment, if any."""
        now = datetime.now(timezone.utc)
        if self.coordinator.data is None:
            return None
        for entry in self.coordinator.data.get(DATA_WEATHER, []):
            ts = entry.get("ts", 0)
            start = datetime.fromtimestamp(ts, tz=timezone.utc)
            end = start + timedelta(hours=1)
            if start <= now < end:
                return self._make_event(entry)
        return None

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        """Return all forecast events that overlap the requested date range."""
        if start_date.tzinfo is None:
            start_date = start_date.replace(tzinfo=timezone.utc)
        if end_date.tzinfo is None:
            end_date = end_date.replace(tzinfo=timezone.utc)

        events = []
        if self.coordinator.data is None:
            return events
        for entry in self.coordinator.data.get(DATA_WEATHER, []):
            try:
                ts = entry["ts"]
                start = datetime.fromtimestamp(ts, tz=timezone.utc)
                end = start + timedelta(hours=1)

                # Skip slots entirely outside the requested window
                if start >= end_date or end <= start_date:
                    continue

                events.append(self._make_event(entry))
            except (KeyError, ValueError, OSError):
                _LOGGER.warning("Failed to parse weather entry: %s", entry)
                continue

        return events
