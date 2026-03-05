"""Binary sensor platform for Enion integration."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, PORT_RELAY, DATA_DEVICE, DATA_PORTS
from .coordinator import EnionCoordinator
from .sensor import _make_device_info


@dataclass(frozen=True, kw_only=True)
class EnionBinarySensorDescription(BinarySensorEntityDescription):
    """Describe an Enion binary sensor."""

    port_prefix: str = ""
    port_sub: str = "0"
    value_fn: Callable[[dict[str, Any]], bool | None] = lambda v: None
    from_device: bool = False  # True = read from device info, not port


BINARY_SENSOR_DESCRIPTIONS: tuple[EnionBinarySensorDescription, ...] = (
    # ------------------------------------------------------------------ Device online
    EnionBinarySensorDescription(
        key="enion_device_online",
        name="Enion Device Online",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        from_device=True,
        value_fn=lambda v: v.get("online"),
    ),
    # ------------------------------------------------------------------ Relays (3/0 – 3/4)
    EnionBinarySensorDescription(
        key="enion_relay_0",
        name="Enion Relay 1",
        device_class=BinarySensorDeviceClass.POWER,
        port_prefix=PORT_RELAY,
        port_sub="0",
        value_fn=lambda v: v.get("is_on"),
    ),
    EnionBinarySensorDescription(
        key="enion_relay_1",
        name="Enion Relay 2",
        device_class=BinarySensorDeviceClass.POWER,
        port_prefix=PORT_RELAY,
        port_sub="1",
        value_fn=lambda v: v.get("is_on"),
    ),
    EnionBinarySensorDescription(
        key="enion_relay_2",
        name="Enion Relay 3",
        device_class=BinarySensorDeviceClass.POWER,
        port_prefix=PORT_RELAY,
        port_sub="2",
        value_fn=lambda v: v.get("is_on"),
    ),
    EnionBinarySensorDescription(
        key="enion_relay_3",
        name="Enion Relay 4",
        device_class=BinarySensorDeviceClass.POWER,
        port_prefix=PORT_RELAY,
        port_sub="3",
        value_fn=lambda v: v.get("is_on"),
    ),
    EnionBinarySensorDescription(
        key="enion_relay_4",
        name="Enion Relay 5",
        device_class=BinarySensorDeviceClass.POWER,
        port_prefix=PORT_RELAY,
        port_sub="4",
        value_fn=lambda v: v.get("is_on"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: EnionCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[BinarySensorEntity] = []

    for desc in BINARY_SENSOR_DESCRIPTIONS:
        entities.append(EnionBinarySensor(coordinator, entry, desc))

    async_add_entities(entities)


class EnionBinarySensor(CoordinatorEntity[EnionCoordinator], BinarySensorEntity):
    """A binary sensor for the Enion system."""

    entity_description: EnionBinarySensorDescription

    def __init__(
        self,
        coordinator: EnionCoordinator,
        entry: ConfigEntry,
        description: EnionBinarySensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = _make_device_info(coordinator, entry)

    @property
    def is_on(self) -> bool | None:
        if self.entity_description.from_device:
            return self.entity_description.value_fn(self.coordinator.get_device_info())

        port_id = self.coordinator.find_port_by_prefix(
            self.entity_description.port_prefix,
            self.entity_description.port_sub,
        )
        if port_id is None:
            return None
        values = self.coordinator.get_port_values(port_id)
        return self.entity_description.value_fn(values)
