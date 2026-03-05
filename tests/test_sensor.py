"""Tests for sensor.py helpers."""
from __future__ import annotations

import pytest

from custom_components.enion.sensor import _parse_battery_status


class TestParseBatteryStatus:
    """Unit tests for _parse_battery_status."""

    def test_ok_status_returns_human_readable(self):
        assert _parse_battery_status({"status": "SPP_ENERGYSTORAGE_INFO_STATUS_OK"}) == "OK"

    def test_comm_failure_returns_human_readable(self):
        assert _parse_battery_status({"status": "SPP_ENERGYSTORAGE_INFO_STATUS_COMM_FAILURE"}) == "Communication Failure"

    def test_unknown_status_returned_as_is(self):
        assert _parse_battery_status({"status": "SPP_ENERGYSTORAGE_INFO_STATUS_SOMETHING_NEW"}) == "SPP_ENERGYSTORAGE_INFO_STATUS_SOMETHING_NEW"

    def test_missing_status_returns_none(self):
        assert _parse_battery_status({}) is None

    def test_none_status_returns_none(self):
        assert _parse_battery_status({"status": None}) is None
