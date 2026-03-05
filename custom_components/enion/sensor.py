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

# Map raw API battery status strings to human-readable labels.
_BATTERY_STATUS_MAP: dict[str, str] = {
    "SPP_ENERGYSTORAGE_INFO_STATUS_OK": "OK",
    "SPP_ENERGYSTORAGE_INFO_STATUS_COMM_FAILURE": "Communication Failure",
}


def _parse_battery_status(values: dict) -> str | None:
    raw = values.get("status")
    if raw is None:
        return None
    return _BATTERY_STATUS_MAP.get(raw, raw)


@dataclass(frozen=True, kw_only=True)
class EnionSensorDescription(SensorEntityDescription):
    """Describe an Enion sensor with its port and value extractor."""

    port_prefix: str
    port_sub: str = "0"
    value_fn: Callable[[dict[str, Any]], Any] = lambda v: None


SENSOR_DESCRIPTIONS: tuple[EnionSensorDescription, ...] = (
    # ------------------------------------------------------------------ Battery
    EnionSensorDescription(
        key="enion_battery_soc",
        name="Battery State of Charge",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        port_prefix=PORT_BATTERY,
        port_sub="0",
        value_fn=lambda v: v.get("soc"),
    ),
    EnionSensorDescription(
        key="enion_battery_power",
        name="Battery Power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        port_prefix=PORT_BATTERY,
        port_sub="0",
        value_fn=lambda v: v.get("power"),
    ),
    EnionSensorDescription(
        key="enion_battery_energy",
        name="Battery Energy",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        port_prefix=PORT_BATTERY,
        port_sub="0",
        value_fn=lambda v: v.get("energy"),
    ),
    EnionSensorDescription(
        key="enion_battery_voltage_l1",
        name="Battery Voltage L1",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        port_prefix=PORT_BATTERY,
        port_sub="0",
        value_fn=lambda v: (v.get("phase_volt") or [None])[0],
    ),
    EnionSensorDescription(
        key="enion_battery_voltage_l2",
        name="Battery Voltage L2",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        port_prefix=PORT_BATTERY,
        port_sub="0",
        value_fn=lambda v: (v.get("phase_volt") or [None, None])[1],
    ),
    EnionSensorDescription(
        key="enion_battery_voltage_l3",
        name="Battery Voltage L3",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        port_prefix=PORT_BATTERY,
        port_sub="0",
        value_fn=lambda v: (v.get("phase_volt") or [None, None, None])[2],
    ),
    EnionSensorDescription(
        key="enion_battery_current_l1",
        name="Battery Current L1",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        port_prefix=PORT_BATTERY,
        port_sub="0",
        value_fn=lambda v: (v.get("phase_curr") or [None])[0],
    ),
    EnionSensorDescription(
        key="enion_battery_current_l2",
        name="Battery Current L2",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        port_prefix=PORT_BATTERY,
        port_sub="0",
        value_fn=lambda v: (v.get("phase_curr") or [None, None])[1],
    ),
    EnionSensorDescription(
        key="enion_battery_current_l3",
        name="Battery Current L3",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        port_prefix=PORT_BATTERY,
        port_sub="0",
        value_fn=lambda v: (v.get("phase_curr") or [None, None, None])[2],
    ),
    EnionSensorDescription(
        key="enion_battery_frequency",
        name="Battery Frequency",
        native_unit_of_measurement=UnitOfFrequency.HERTZ,
        device_class=SensorDeviceClass.FREQUENCY,
        state_class=SensorStateClass.MEASUREMENT,
        port_prefix=PORT_BATTERY,
        port_sub="0",
        value_fn=lambda v: v.get("freq"),
    ),
    EnionSensorDescription(
        key="enion_battery_status",
        name="Battery Status",
        port_prefix=PORT_BATTERY,
        port_sub="0",
        value_fn=_parse_battery_status,
    ),
    # ------------------------------------------------------------------ Grid (107/1 = power meter)
    EnionSensorDescription(
        key="enion_grid_power",
        name="Grid Power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        port_prefix=PORT_GRID,
        port_sub="1",
        value_fn=lambda v: v.get("power"),
    ),
    EnionSensorDescription(
        key="enion_grid_energy",
        name="Grid Energy (All Time)",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        port_prefix=PORT_GRID,
        port_sub="1",
        value_fn=lambda v: v.get("all_time_wh"),
    ),
    EnionSensorDescription(
        key="enion_grid_frequency",
        name="Grid Frequency",
        native_unit_of_measurement=UnitOfFrequency.HERTZ,
        device_class=SensorDeviceClass.FREQUENCY,
        state_class=SensorStateClass.MEASUREMENT,
        port_prefix=PORT_GRID,
        port_sub="1",
        value_fn=lambda v: v.get("freq"),
    ),
    EnionSensorDescription(
        key="enion_grid_voltage_l1",
        name="Grid Voltage L1",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        port_prefix=PORT_GRID,
        port_sub="1",
        value_fn=lambda v: (v.get("phase_volt") or [None])[0],
    ),
    EnionSensorDescription(
        key="enion_grid_voltage_l2",
        name="Grid Voltage L2",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        port_prefix=PORT_GRID,
        port_sub="1",
        value_fn=lambda v: (v.get("phase_volt") or [None, None])[1],
    ),
    EnionSensorDescription(
        key="enion_grid_voltage_l3",
        name="Grid Voltage L3",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        port_prefix=PORT_GRID,
        port_sub="1",
        value_fn=lambda v: (v.get("phase_volt") or [None, None, None])[2],
    ),
    EnionSensorDescription(
        key="enion_grid_current_l1",
        name="Grid Current L1",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        port_prefix=PORT_GRID,
        port_sub="1",
        value_fn=lambda v: (v.get("phase_curr") or [None])[0],
    ),
    EnionSensorDescription(
        key="enion_grid_current_l2",
        name="Grid Current L2",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        port_prefix=PORT_GRID,
        port_sub="1",
        value_fn=lambda v: (v.get("phase_curr") or [None, None])[1],
    ),
    EnionSensorDescription(
        key="enion_grid_current_l3",
        name="Grid Current L3",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        port_prefix=PORT_GRID,
        port_sub="1",
        value_fn=lambda v: (v.get("phase_curr") or [None, None, None])[2],
    ),
    # ------------------------------------------------------------------ Energy meter (108/0)
    EnionSensorDescription(
        key="enion_energy_meter_power",
        name="Energy Meter Power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        port_prefix=PORT_ENERGY,
        port_sub="0",
        value_fn=lambda v: v.get("power"),
    ),
    EnionSensorDescription(
        key="enion_energy_meter_energy",
        name="Energy Meter Energy",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        port_prefix=PORT_ENERGY,
        port_sub="0",
        value_fn=lambda v: v.get("energy"),
    ),
    EnionSensorDescription(
        key="enion_energy_meter_voltage_l1",
        name="Energy Meter RMS Voltage L1",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        port_prefix=PORT_ENERGY,
        port_sub="0",
        value_fn=lambda v: (v.get("rms_voltage") or [None])[0],
    ),
    EnionSensorDescription(
        key="enion_energy_meter_voltage_l2",
        name="Energy Meter RMS Voltage L2",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        port_prefix=PORT_ENERGY,
        port_sub="0",
        value_fn=lambda v: (v.get("rms_voltage") or [None, None])[1],
    ),
    EnionSensorDescription(
        key="enion_energy_meter_voltage_l3",
        name="Energy Meter RMS Voltage L3",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        port_prefix=PORT_ENERGY,
        port_sub="0",
        value_fn=lambda v: (v.get("rms_voltage") or [None, None, None])[2],
    ),
    EnionSensorDescription(
        key="enion_energy_meter_current_l1",
        name="Energy Meter Current L1",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        port_prefix=PORT_ENERGY,
        port_sub="0",
        value_fn=lambda v: (v.get("cur_current") or [None])[0],
    ),
    EnionSensorDescription(
        key="enion_energy_meter_current_l2",
        name="Energy Meter Current L2",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        port_prefix=PORT_ENERGY,
        port_sub="0",
        value_fn=lambda v: (v.get("cur_current") or [None, None])[1],
    ),
    EnionSensorDescription(
        key="enion_energy_meter_current_l3",
        name="Energy Meter Current L3",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        port_prefix=PORT_ENERGY,
        port_sub="0",
        value_fn=lambda v: (v.get("cur_current") or [None, None, None])[2],
    ),
    # ------------------------------------------------------------------ Energy meter power factor and real power
    EnionSensorDescription(
        key="enion_energy_meter_power_factor_l1",
        name="Energy Meter Power Factor L1",
        state_class=SensorStateClass.MEASUREMENT,
        port_prefix=PORT_ENERGY,
        port_sub="0",
        value_fn=lambda v: (v.get("phases") or [{}])[0].get("pf"),
    ),
    EnionSensorDescription(
        key="enion_energy_meter_power_factor_l2",
        name="Energy Meter Power Factor L2",
        state_class=SensorStateClass.MEASUREMENT,
        port_prefix=PORT_ENERGY,
        port_sub="0",
        value_fn=lambda v: (v.get("phases") or [{}, {}])[1].get("pf"),
    ),
    EnionSensorDescription(
        key="enion_energy_meter_power_factor_l3",
        name="Energy Meter Power Factor L3",
        state_class=SensorStateClass.MEASUREMENT,
        port_prefix=PORT_ENERGY,
        port_sub="0",
        value_fn=lambda v: (v.get("phases") or [{}, {}, {}])[2].get("pf"),
    ),
    EnionSensorDescription(
        key="enion_energy_meter_real_power_l1",
        name="Energy Meter Real Power L1",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        port_prefix=PORT_ENERGY,
        port_sub="0",
        value_fn=lambda v: (v.get("phases") or [{}])[0].get("real_power"),
    ),
    EnionSensorDescription(
        key="enion_energy_meter_real_power_l2",
        name="Energy Meter Real Power L2",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        port_prefix=PORT_ENERGY,
        port_sub="0",
        value_fn=lambda v: (v.get("phases") or [{}, {}])[1].get("real_power"),
    ),
    EnionSensorDescription(
        key="enion_energy_meter_real_power_l3",
        name="Energy Meter Real Power L3",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        port_prefix=PORT_ENERGY,
        port_sub="0",
        value_fn=lambda v: (v.get("phases") or [{}, {}, {}])[2].get("real_power"),
    ),
    # ------------------------------------------------------------------ Electricity prices
    EnionSensorDescription(
        key="enion_electricity_price_current",
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
        key="enion_electricity_price_next",
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
        key="enion_weather_temperature",
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
        key="enion_weather_wind_speed",
        name="Wind Speed",
        native_unit_of_measurement="m/s",
        device_class=SensorDeviceClass.WIND_SPEED,
        state_class=SensorStateClass.MEASUREMENT,
        port_prefix=PORT_WEATHER,
        port_sub="0",
        value_fn=lambda v: None,
    ),
    EnionSensorDescription(
        key="enion_weather_wind_direction",
        name="Wind Direction",
        port_prefix=PORT_WEATHER,
        port_sub="0",
        # Handled specially in EnionWeatherSensor
        value_fn=lambda v: None,
    ),
    EnionSensorDescription(
        key="enion_weather_sun_condition",
        name="Sun Condition",
        port_prefix=PORT_WEATHER,
        port_sub="0",
        # Handled specially in EnionWeatherSensor
        value_fn=lambda v: None,
    ),
    # ------------------------------------------------------------------ Battery Optimizer (220/0)
    EnionSensorDescription(
        key="enion_battery_optimizer_state",
        name="Battery Optimizer State",
        port_prefix=PORT_OPTIMIZER,
        port_sub="0",
        # Handled specially in EnionOptimizerSensor
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
        if desc.key == "enion_electricity_price_current":
            entities.append(EnionPriceSensor(coordinator, entry, desc, current=True))
        elif desc.key == "enion_electricity_price_next":
            entities.append(EnionPriceSensor(coordinator, entry, desc, current=False))
        elif desc.key == "enion_weather_temperature":
            entities.append(EnionWeatherSensor(coordinator, entry, desc, field="temperature"))
        elif desc.key == "enion_weather_wind_speed":
            entities.append(EnionWeatherSensor(coordinator, entry, desc, field="wind_speed"))
        elif desc.key == "enion_weather_wind_direction":
            entities.append(EnionWeatherSensor(coordinator, entry, desc, field="wind_dir"))
        elif desc.key == "enion_weather_sun_condition":
            entities.append(EnionWeatherSensor(coordinator, entry, desc, field="sun"))
        elif desc.key == "enion_battery_optimizer_state":
            entities.append(EnionOptimizerSensor(coordinator, entry, desc))
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
        if self.coordinator.data is None:
            return None
        for entry in self.coordinator.data.get("weather", []):
            ts = entry.get("ts", 0)
            if ts <= now < ts + 3600:
                return entry.get(self._field)
        return None


class EnionOptimizerSensor(CoordinatorEntity[EnionCoordinator], SensorEntity):
    """Battery optimizer state sensor with full schedule in attributes."""

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

    @property
    def native_value(self) -> str | None:
        """Return the current optimizer state."""
        current_state, _, _ = self.coordinator.get_optimizer_state()
        return current_state

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the optimizer schedule and next state in attributes."""
        _, next_event_time, schedule = self.coordinator.get_optimizer_state()

        # Format schedule for display
        formatted_schedule = []
        for event in schedule:
            formatted_schedule.append({
                "time": event["time"],
                "state": event["state"],
            })

        return {
            "next_event_time": next_event_time,
            "schedule": formatted_schedule,
        }
