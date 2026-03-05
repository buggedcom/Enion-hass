"""Sensor platform for Enion integration."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    UnitOfEnergy,
    UnitOfFrequency,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfPower,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    PORT_BATTERY,
    PORT_ENERGY,
    PORT_GRID,
    PORT_OPTIMIZER,
    PORT_PRICES,
    PORT_WEATHER,
    DATA_DEVICE,
    DATA_PORTS,
)
from .coordinator import EnionCoordinator


@dataclass(frozen=True, kw_only=True)
class EnionSensorDescription(SensorEntityDescription):
    """Describe an Enion sensor with its port and value extractor."""

    port_prefix: str
    port_sub: str = "0"
    value_fn: Callable[[dict[str, Any]], Any] = lambda v: None


SENSOR_DESCRIPTIONS: tuple[EnionSensorDescription, ...] = (
    # ------------------------------------------------------------------ Battery
    EnionSensorDescription(
        key="battery_soc",
        name="Battery State of Charge",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        port_prefix=PORT_BATTERY,
        port_sub="0",
        value_fn=lambda v: v.get("soc"),
    ),
    EnionSensorDescription(
        key="battery_power",
        name="Battery Power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        port_prefix=PORT_BATTERY,
        port_sub="0",
        value_fn=lambda v: v.get("power"),
    ),
    EnionSensorDescription(
        key="battery_energy",
        name="Battery Energy",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        port_prefix=PORT_BATTERY,
        port_sub="0",
        value_fn=lambda v: v.get("energy"),
    ),
    EnionSensorDescription(
        key="battery_voltage",
        name="Battery Voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        port_prefix=PORT_BATTERY,
        port_sub="0",
        value_fn=lambda v: v.get("phase_volt"),
    ),
    EnionSensorDescription(
        key="battery_current",
        name="Battery Current",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        port_prefix=PORT_BATTERY,
        port_sub="0",
        value_fn=lambda v: v.get("phase_curr"),
    ),
    EnionSensorDescription(
        key="battery_frequency",
        name="Battery Frequency",
        native_unit_of_measurement=UnitOfFrequency.HERTZ,
        device_class=SensorDeviceClass.FREQUENCY,
        state_class=SensorStateClass.MEASUREMENT,
        port_prefix=PORT_BATTERY,
        port_sub="0",
        value_fn=lambda v: v.get("freq"),
    ),
    EnionSensorDescription(
        key="battery_status",
        name="Battery Status",
        port_prefix=PORT_BATTERY,
        port_sub="0",
        value_fn=lambda v: v.get("status"),
    ),
    # ------------------------------------------------------------------ Grid (107/1 = power meter)
    EnionSensorDescription(
        key="grid_power",
        name="Grid Power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        port_prefix=PORT_GRID,
        port_sub="1",
        value_fn=lambda v: v.get("power"),
    ),
    EnionSensorDescription(
        key="grid_energy",
        name="Grid Energy (All Time)",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        port_prefix=PORT_GRID,
        port_sub="1",
        value_fn=lambda v: v.get("all_time_wh"),
    ),
    EnionSensorDescription(
        key="grid_frequency",
        name="Grid Frequency",
        native_unit_of_measurement=UnitOfFrequency.HERTZ,
        device_class=SensorDeviceClass.FREQUENCY,
        state_class=SensorStateClass.MEASUREMENT,
        port_prefix=PORT_GRID,
        port_sub="1",
        value_fn=lambda v: v.get("freq"),
    ),
    EnionSensorDescription(
        key="grid_voltage_l1",
        name="Grid Voltage L1",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        port_prefix=PORT_GRID,
        port_sub="1",
        value_fn=lambda v: (v.get("phase_volt") or [None])[0],
    ),
    EnionSensorDescription(
        key="grid_current_l1",
        name="Grid Current L1",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        port_prefix=PORT_GRID,
        port_sub="1",
        value_fn=lambda v: (v.get("phase_curr") or [None])[0],
    ),
    # ------------------------------------------------------------------ Energy meter (108/0)
    EnionSensorDescription(
        key="energy_meter_power",
        name="Energy Meter Power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        port_prefix=PORT_ENERGY,
        port_sub="0",
        value_fn=lambda v: v.get("power"),
    ),
    EnionSensorDescription(
        key="energy_meter_energy",
        name="Energy Meter Energy",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        port_prefix=PORT_ENERGY,
        port_sub="0",
        value_fn=lambda v: v.get("energy"),
    ),
    EnionSensorDescription(
        key="energy_meter_voltage",
        name="Energy Meter RMS Voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        port_prefix=PORT_ENERGY,
        port_sub="0",
        value_fn=lambda v: v.get("rms_voltage"),
    ),
    EnionSensorDescription(
        key="energy_meter_current",
        name="Energy Meter Current",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        port_prefix=PORT_ENERGY,
        port_sub="0",
        value_fn=lambda v: v.get("cur_current"),
    ),
    # ------------------------------------------------------------------ Electricity prices
    EnionSensorDescription(
        key="electricity_price_current",
        name="Electricity Price (Current Hour)",
        native_unit_of_measurement="ct/kWh",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.MEASUREMENT,
        port_prefix=PORT_PRICES,
        port_sub="0",
        # Handled specially in EnionPriceSensor
        value_fn=lambda v: None,
    ),
    EnionSensorDescription(
        key="electricity_price_next",
        name="Electricity Price (Next Hour)",
        native_unit_of_measurement="ct/kWh",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.MEASUREMENT,
        port_prefix=PORT_PRICES,
        port_sub="0",
        value_fn=lambda v: None,
    ),
    # ------------------------------------------------------------------ Weather
    EnionSensorDescription(
        key="weather_temperature",
        name="Outside Temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        port_prefix=PORT_WEATHER,
        port_sub="0",
        # Handled specially in EnionWeatherSensor
        value_fn=lambda v: None,
    ),
    EnionSensorDescription(
        key="weather_wind_speed",
        name="Wind Speed",
        native_unit_of_measurement="m/s",
        device_class=SensorDeviceClass.WIND_SPEED,
        state_class=SensorStateClass.MEASUREMENT,
        port_prefix=PORT_WEATHER,
        port_sub="0",
        value_fn=lambda v: None,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: EnionCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[SensorEntity] = []

    for desc in SENSOR_DESCRIPTIONS:
        if desc.key == "electricity_price_current":
            entities.append(EnionPriceSensor(coordinator, entry, desc, current=True))
        elif desc.key == "electricity_price_next":
            entities.append(EnionPriceSensor(coordinator, entry, desc, current=False))
        elif desc.key == "weather_temperature":
            entities.append(EnionWeatherSensor(coordinator, entry, desc, field="temperature"))
        elif desc.key == "weather_wind_speed":
            entities.append(EnionWeatherSensor(coordinator, entry, desc, field="wind_speed"))
        else:
            entities.append(EnionPortSensor(coordinator, entry, desc))

    async_add_entities(entities)


def _make_device_info(coordinator: EnionCoordinator, entry: ConfigEntry) -> DeviceInfo:
    meta = coordinator.device_meta
    device = coordinator.get_device_info()
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=f"Enion {meta.get('model', 'Hub')}",
        manufacturer=meta.get("manufacturer", "Sunergos"),
        model=meta.get("model", "Enion"),
        hw_version=meta.get("hw_id"),
        sw_version=device.get("firmware_version"),
        configuration_url="https://app.enion.fi/",
    )


class EnionPortSensor(CoordinatorEntity[EnionCoordinator], SensorEntity):
    """A sensor backed by a specific Enion port."""

    entity_description: EnionSensorDescription

    def __init__(
        self,
        coordinator: EnionCoordinator,
        entry: ConfigEntry,
        description: EnionSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = _make_device_info(coordinator, entry)
        self._entry = entry

    @property
    def native_value(self) -> Any:
        port_id = self.coordinator.find_port_by_prefix(
            self.entity_description.port_prefix,
            self.entity_description.port_sub,
        )
        if port_id is None:
            return None
        values = self.coordinator.get_port_values(port_id)
        return self.entity_description.value_fn(values)


class EnionPriceSensor(CoordinatorEntity[EnionCoordinator], SensorEntity):
    """Electricity price sensor (current or next hour)."""

    entity_description: EnionSensorDescription

    def __init__(
        self,
        coordinator: EnionCoordinator,
        entry: ConfigEntry,
        description: EnionSensorDescription,
        current: bool,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._current = current
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = _make_device_info(coordinator, entry)

    @property
    def native_value(self) -> float | None:
        if self._current:
            return self.coordinator.get_current_price()
        return self.coordinator.get_next_price()


class EnionWeatherSensor(CoordinatorEntity[EnionCoordinator], SensorEntity):
    """Weather forecast sensor (current hour)."""

    entity_description: EnionSensorDescription

    def __init__(
        self,
        coordinator: EnionCoordinator,
        entry: ConfigEntry,
        description: EnionSensorDescription,
        field: str,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._field = field
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = _make_device_info(coordinator, entry)

    @property
    def native_value(self) -> Any:
        import time
        now = int(time.time())
        for entry in self.coordinator.data.get("weather", []):
            ts = entry.get("ts", 0)
            if ts <= now < ts + 3600:
                return entry.get(self._field)
        return None
