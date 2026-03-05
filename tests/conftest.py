"""Shared fixtures and sample data for Enion tests."""
from __future__ import annotations

import pytest

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
        "base_ts": 1_700_000_000,
        "timestep": 3600,
        "prices": [10.5, 11.0, 9.8, 8.5],
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
        "base_ts": 1_700_000_000,
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
