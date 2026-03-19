"""Shared fixtures and sample data for Enion tests."""
from __future__ import annotations

import pytest
import time

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading of custom integrations for all tests."""

# ---------------------------------------------------------------------------
# Sample API payloads (based on confirmed response shapes)
# ---------------------------------------------------------------------------

LOGIN_RESPONSE = {
    "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test",
}

ME_RESPONSE = {
    "user": {
        "id": 2628,
        "email": "test@example.com",
        "currency": "EUR",
        "country": {"id": 70, "name": "Finland", "iso_3166": "FI"},
        "area": {"code": "FI", "id": 6, "name": "Finland"},
    },
    "token": None,
    "features": ["LOGIN", "HISTORY_PAGE"],
    "devices": [
        {
            "id": 2392,
            "hw_id": "0B8D7EFB",
            "name": "0B8D7EFB",
            "location_id": 1938,
            "values": {
                "firmware_version": "DDBB83BE33D7B2BC",
                "last_data": "2026-03-05T12:51:35Z",
                "online": True,
            },
            "device_spec": {
                "id": 1,
                "manufacturer": "Sunergos",
                "model": "Mini 3.0",
                "description": "Enion Mini 3.0.",
            },
            "ports": [
                {"id": 104225, "port_number": "3/0", "type": "RELAY", "values": {}},
                {"id": 104226, "port_number": "3/1", "type": "RELAY", "values": {}},
                {"id": 104230, "port_number": "22/0", "type": "ENERGY_STORAGE", "values": {}},
                {"id": 104251, "port_number": "107/1", "type": "SOLAR", "values": {}},
                {"id": 104252, "port_number": "108/0", "type": "EM_HAN", "values": {}},
                {"id": 104264, "port_number": "212/0", "type": "OPTIMIZER_PRICE", "values": {}},
                {"id": 104266, "port_number": "214/0", "type": "OPTIMIZER_WEATHER", "values": {}},
                {"id": 104267, "port_number": "220/0", "type": "BATTERY_OPTIMIZER", "values": {}},
            ],
            "comments": "generic_customer",
            "rules": [],
        }
    ],
    "locations": [{"id": 1938, "name": "Home"}],
    "announcements": [],
}

# Realistic WS update payloads
WS_UPDATE_BATTERY = {
    "device_id": 2392,
    "event": "update",
    "hw_id": "0B8D7EFB",
    "port_id": 104230,
    "port_number": "22/0",
    "refresh": False,
    "version": "0.162.236",
    "values": {
        "soc": 72,
        "power": -1200,
        "energy": 5400,
        "phase_volt": 230.5,
        "phase_curr": 5.2,
        "freq": 50.01,
        "status": "discharging",
    },
}

WS_UPDATE_PRICES = {
    "device_id": 2392,
    "event": "update",
    "hw_id": "0B8D7EFB",
    "port_id": 104264,
    "port_number": "212/0",
    "refresh": True,
    "version": "0.162.236",
    "values": {
        "base_ts": "2023-11-15T00:13:20Z",
        "timestep": 3600,
        "prices": [105, 110, 98, 85],
    },
}

WS_UPDATE_WEATHER = {
    "device_id": 2392,
    "event": "update",
    "hw_id": "0B8D7EFB",
    "port_id": 104266,
    "port_number": "214/0",
    "refresh": True,
    "version": "0.162.236",
    "values": {
        "base_ts": "2023-11-15T00:13:20Z",
        "timestep": 3600,
        "weathers": [
            {"temperature": 3.5, "wind_speed": 4.2, "wind_dir": 180, "sun": 0},
            {"temperature": 4.0, "wind_speed": 3.8, "wind_dir": 185, "sun": 10},
        ],
    },
}

WS_DEVICE_EVENT = {
    "event": "device",
    "hw_id": "0B8D7EFB",
    "refresh": True,
    "version": "0.162.236",
    "values": {
        "online": True,
        "last_data": "2026-03-05T13:00:00Z",
        "firmware_version": "DDBB83BE33D7B2BC",
    },
}

PROFITS_RESPONSE = [
    {
        "timestamp": "2026-03-08T22:00:00.000Z",
        "batt_power": 23.07,
        "spot_saving": 0.14,
        "fcr_down_power": 11883.0,
        "fcr_down_price": 1.01,
        "fcr_up_power": 11975.0,
        "fcr_up_price": 1.36,
    },
    {
        "timestamp": "2026-03-09T22:00:00.000Z",
        "batt_power": -60.87,
        "spot_saving": 1.11,
        "fcr_down_power": 1.24e4,
        "fcr_down_price": 0.83,
        "fcr_up_power": 12496.0,
        "fcr_up_price": 1.15,
    },
]

WS_UPDATE_OPTIMIZER = {
    "device_id": 2392,
    "event": "update",
    "hw_id": "0B8D7EFB",
    "port_id": 104267,
    "port_number": "220/0",
    "refresh": True,
    "version": "0.162.236",
    "values": {
        "commissioning_state": 0,
        "commissioning_errcode": 0,
        "events": [
            ["2026-03-05T17:00:00Z", {"state": "BATTERY_OPTIMIZER_STATE_NET_ZERO", "reserve_up": "BATOPT_EVENT_RESERVE_UNKNOWN", "reserve_dn": "BATOPT_EVENT_RESERVE_UNKNOWN"}],
            ["2026-03-05T20:00:00Z", {"state": "BATTERY_OPTIMIZER_STATE_AVOID_SELL", "reserve_up": "BATOPT_EVENT_RESERVE_UNKNOWN", "reserve_dn": "BATOPT_EVENT_RESERVE_UNKNOWN"}],
            ["2026-03-05T22:00:00Z", {"state": "BATTERY_OPTIMIZER_STATE_CHARGE", "reserve_up": "BATOPT_EVENT_RESERVE_UNKNOWN", "reserve_dn": "BATOPT_EVENT_RESERVE_UNKNOWN"}],
        ],
    },
}
