"""Switch platform for Enion optimizer action overrides."""
from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import EnionCoordinator
from .sensor import _make_device_info

CMD_CHARGING = -1_000_000
CMD_DISCHARGING = 1_000_000
CMD_STOP = 0
CMD_CANCEL = 2**31 - 1


@dataclass(frozen=True, kw_only=True)
class EnionSwitchDescription(SwitchEntityDescription):
    """Describe an Enion optimizer action switch."""

    command_value: int


SWITCH_DESCRIPTIONS: tuple[EnionSwitchDescription, ...] = (
    EnionSwitchDescription(
        key="enion_charge_1h",
        name="Enion Charge 1h",
        command_value=CMD_CHARGING,
    ),
    EnionSwitchDescription(
        key="enion_discharge_1h",
        name="Enion Discharge 1h",
        command_value=CMD_DISCHARGING,
    ),
    EnionSwitchDescription(
        key="enion_stop_1h",
        name="Enion Stop 1h",
        command_value=CMD_STOP,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Enion action switches for a config entry."""
    coordinator: EnionCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        EnionOptimizerActionSwitch(coordinator, entry, description)
        for description in SWITCH_DESCRIPTIONS
    )


class EnionOptimizerActionSwitch(CoordinatorEntity[EnionCoordinator], SwitchEntity):
    """Switch representing one active optimizer override action."""

    entity_description: EnionSwitchDescription

    def __init__(
        self,
        coordinator: EnionCoordinator,
        entry: ConfigEntry,
        description: EnionSwitchDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = _make_device_info(coordinator, entry)

    @property
    def available(self) -> bool:
        if self.coordinator.find_optimizer_port_id() is None:
            return False

        override_active = self.coordinator.is_optimizer_override_active()
        if not override_active:
            return True

        active_command = self.coordinator.get_active_optimizer_override_command()
        return active_command == self.entity_description.command_value

    @property
    def is_on(self) -> bool:
        return (
            self.coordinator.get_active_optimizer_override_command()
            == self.entity_description.command_value
        )

    async def async_turn_on(self, **kwargs) -> None:
        """Send the optimizer override command."""
        if not self.available:
            raise HomeAssistantError("Optimizer action is currently unavailable")
        await self.coordinator.async_send_optimizer_override(
            self.entity_description.command_value
        )

    async def async_turn_off(self, **kwargs) -> None:
        """Cancel the current override when turning off the active switch."""
        if self.is_on:
            await self.coordinator.async_send_optimizer_override(CMD_CANCEL)
