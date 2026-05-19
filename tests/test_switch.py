"""Unit tests for switch.py."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.enion.api import EnionClient
from custom_components.enion.const import DOMAIN
from custom_components.enion.coordinator import EnionCoordinator
from custom_components.enion.switch import (
    CMD_CHARGING,
    CMD_DISCHARGING,
    CMD_STOP,
    EnionOptimizerActionSwitch,
    SWITCH_DESCRIPTIONS,
    async_setup_entry,
)
from tests.conftest import ME_RESPONSE, ME_RESPONSE_NO_OPTIMIZER, WS_UPDATE_OPTIMIZER_OVERRIDE


@pytest.fixture
def entry():
    return MagicMock(entry_id="test-entry-id")


@pytest.fixture
async def coordinator(hass):
    client = MagicMock(spec=EnionClient)
    client.ws_token = "test_token"
    client.user_id = "2628"
    coordinator = EnionCoordinator(
        hass=hass,
        session=MagicMock(),
        client=client,
        email="test@example.com",
        password="secret",
    )
    coordinator.async_set_updated_data = MagicMock()
    hass.async_create_task = MagicMock(return_value=MagicMock())
    return coordinator


def _make_switch(coordinator, entry, key: str) -> EnionOptimizerActionSwitch:
    description = next(desc for desc in SWITCH_DESCRIPTIONS if desc.key == key)
    return EnionOptimizerActionSwitch(coordinator, entry, description)


class TestSwitchSetup:
    async def test_setup_creates_three_entities(self, hass, coordinator, entry):
        coordinator._seed_from_me(ME_RESPONSE)
        hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
        entities = []

        await async_setup_entry(hass, entry, entities.extend)

        assert len(entities) == 3


class TestSwitchCommands:
    async def test_charge_sends_charge_command(self, coordinator, entry):
        coordinator._seed_from_me(ME_RESPONSE)
        entity = _make_switch(coordinator, entry, "enion_charge_1h")
        coordinator.async_send_optimizer_override = AsyncMock()

        await entity.async_turn_on()

        coordinator.async_send_optimizer_override.assert_awaited_once_with(CMD_CHARGING)

    async def test_discharge_sends_discharge_command(self, coordinator, entry):
        coordinator._seed_from_me(ME_RESPONSE)
        entity = _make_switch(coordinator, entry, "enion_discharge_1h")
        coordinator.async_send_optimizer_override = AsyncMock()

        await entity.async_turn_on()

        coordinator.async_send_optimizer_override.assert_awaited_once_with(CMD_DISCHARGING)

    async def test_stop_sends_stop_command(self, coordinator, entry):
        coordinator._seed_from_me(ME_RESPONSE)
        entity = _make_switch(coordinator, entry, "enion_stop_1h")
        coordinator.async_send_optimizer_override = AsyncMock()

        await entity.async_turn_on()

        coordinator.async_send_optimizer_override.assert_awaited_once_with(CMD_STOP)

    async def test_turning_off_active_switch_sends_cancel_command(self, coordinator, entry):
        coordinator._seed_from_me(ME_RESPONSE)
        coordinator._handle_update(WS_UPDATE_OPTIMIZER_OVERRIDE)
        coordinator._last_optimizer_override_command = CMD_CHARGING
        entity = _make_switch(coordinator, entry, "enion_charge_1h")
        coordinator.async_send_optimizer_override = AsyncMock()

        await entity.async_turn_off()

        coordinator.async_send_optimizer_override.assert_awaited_once_with(2**31 - 1)

    async def test_turning_off_inactive_switch_is_noop(self, coordinator, entry):
        coordinator._seed_from_me(ME_RESPONSE)
        entity = _make_switch(coordinator, entry, "enion_charge_1h")
        coordinator.async_send_optimizer_override = AsyncMock()

        await entity.async_turn_off()

        coordinator.async_send_optimizer_override.assert_not_awaited()


class TestSwitchAvailability:
    async def test_override_inactive_charge_discharge_stop_available(self, coordinator, entry):
        coordinator._seed_from_me(ME_RESPONSE)

        charge = _make_switch(coordinator, entry, "enion_charge_1h")
        discharge = _make_switch(coordinator, entry, "enion_discharge_1h")
        stop = _make_switch(coordinator, entry, "enion_stop_1h")

        assert charge.available is True
        assert discharge.available is True
        assert stop.available is True

    async def test_override_active_only_active_switch_available(self, coordinator, entry):
        coordinator._seed_from_me(ME_RESPONSE)
        coordinator._handle_update(WS_UPDATE_OPTIMIZER_OVERRIDE)
        coordinator._last_optimizer_override_command = CMD_CHARGING

        charge = _make_switch(coordinator, entry, "enion_charge_1h")
        discharge = _make_switch(coordinator, entry, "enion_discharge_1h")
        stop = _make_switch(coordinator, entry, "enion_stop_1h")

        assert charge.available is True
        assert discharge.available is False
        assert stop.available is False

    async def test_missing_optimizer_port_all_entities_unavailable(self, coordinator, entry):
        coordinator._seed_from_me(ME_RESPONSE_NO_OPTIMIZER)

        for description in SWITCH_DESCRIPTIONS:
            entity = EnionOptimizerActionSwitch(coordinator, entry, description)
            assert entity.available is False

    async def test_active_switch_is_on_only_during_override(self, coordinator, entry):
        coordinator._seed_from_me(ME_RESPONSE)
        charge = _make_switch(coordinator, entry, "enion_charge_1h")
        discharge = _make_switch(coordinator, entry, "enion_discharge_1h")

        assert charge.is_on is False
        assert discharge.is_on is False

        coordinator._handle_update(WS_UPDATE_OPTIMIZER_OVERRIDE)
        coordinator._last_optimizer_override_command = CMD_CHARGING

        assert charge.is_on is True
        assert discharge.is_on is False

    async def test_active_switch_inferred_from_battery_power_when_cache_missing(self, coordinator, entry):
        coordinator._seed_from_me(ME_RESPONSE)
        coordinator._handle_update(WS_UPDATE_OPTIMIZER_OVERRIDE)
        battery_port_id = coordinator.find_port_by_prefix("22", "0")
        coordinator._store["ports"][battery_port_id]["values"]["power"] = -1200
        coordinator._last_optimizer_override_command = None

        charge = _make_switch(coordinator, entry, "enion_charge_1h")
        discharge = _make_switch(coordinator, entry, "enion_discharge_1h")

        assert charge.is_on is False
        assert discharge.is_on is True
