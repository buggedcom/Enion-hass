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
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
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
    DATA_PROFITS,
    DATA_USER,
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
    entity_registry_enabled_default: bool = True
    entity_category: EntityCategory | None = None


SENSOR_DESCRIPTIONS: tuple[EnionSensorDescription, ...] = (
    # ------------------------------------------------------------------ Battery
    EnionSensorDescription(
        key="enion_battery_soc",
        name="Enion Battery State of Charge",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        port_prefix=PORT_BATTERY,
        port_sub="0",
        value_fn=lambda v: v.get("soc"),
    ),
    EnionSensorDescription(
        key="enion_battery_power",
        name="Enion Battery Power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        port_prefix=PORT_BATTERY,
        port_sub="0",
        value_fn=lambda v: v.get("power"),
    ),
    EnionSensorDescription(
        key="enion_battery_energy",
        name="Enion Battery Energy",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        port_prefix=PORT_BATTERY,
        port_sub="0",
        value_fn=lambda v: v.get("energy"),
    ),
    EnionSensorDescription(
        key="enion_battery_voltage_l1",
        name="Enion Battery Voltage L1",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        port_prefix=PORT_BATTERY,
        port_sub="0",
        value_fn=lambda v: (v.get("phase_volt") or [None])[0],
    ),
    EnionSensorDescription(
        key="enion_battery_voltage_l2",
        name="Enion Battery Voltage L2",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        port_prefix=PORT_BATTERY,
        port_sub="0",
        value_fn=lambda v: (v.get("phase_volt") or [None, None])[1],
    ),
    EnionSensorDescription(
        key="enion_battery_voltage_l3",
        name="Enion Battery Voltage L3",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        port_prefix=PORT_BATTERY,
        port_sub="0",
        value_fn=lambda v: (v.get("phase_volt") or [None, None, None])[2],
    ),
    EnionSensorDescription(
        key="enion_battery_current_l1",
        name="Enion Battery Current L1",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        port_prefix=PORT_BATTERY,
        port_sub="0",
        value_fn=lambda v: (v.get("phase_curr") or [None])[0],
    ),
    EnionSensorDescription(
        key="enion_battery_current_l2",
        name="Enion Battery Current L2",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        port_prefix=PORT_BATTERY,
        port_sub="0",
        value_fn=lambda v: (v.get("phase_curr") or [None, None])[1],
    ),
    EnionSensorDescription(
        key="enion_battery_current_l3",
        name="Enion Battery Current L3",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        port_prefix=PORT_BATTERY,
        port_sub="0",
        value_fn=lambda v: (v.get("phase_curr") or [None, None, None])[2],
    ),
    EnionSensorDescription(
        key="enion_battery_frequency",
        name="Enion Battery Frequency",
        native_unit_of_measurement=UnitOfFrequency.HERTZ,
        device_class=SensorDeviceClass.FREQUENCY,
        state_class=SensorStateClass.MEASUREMENT,
        port_prefix=PORT_BATTERY,
        port_sub="0",
        value_fn=lambda v: v.get("freq"),
    ),
    EnionSensorDescription(
        key="enion_battery_status",
        name="Enion Battery Status",
        port_prefix=PORT_BATTERY,
        port_sub="0",
        value_fn=_parse_battery_status,
    ),
    # ------------------------------------------------------------------ Grid (107/1 = power meter)
    EnionSensorDescription(
        key="enion_grid_power",
        name="Enion Grid Power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        port_prefix=PORT_GRID,
        port_sub="1",
        value_fn=lambda v: v.get("power"),
    ),
    EnionSensorDescription(
        key="enion_grid_energy",
        name="Enion Grid Energy (All Time)",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        port_prefix=PORT_GRID,
        port_sub="1",
        value_fn=lambda v: v.get("all_time_wh"),
    ),
    EnionSensorDescription(
        key="enion_grid_frequency",
        name="Enion Grid Frequency",
        native_unit_of_measurement=UnitOfFrequency.HERTZ,
        device_class=SensorDeviceClass.FREQUENCY,
        state_class=SensorStateClass.MEASUREMENT,
        port_prefix=PORT_GRID,
        port_sub="1",
        value_fn=lambda v: v.get("freq"),
    ),
    EnionSensorDescription(
        key="enion_grid_voltage_l1",
        name="Enion Grid Voltage L1",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        port_prefix=PORT_GRID,
        port_sub="1",
        value_fn=lambda v: (v.get("phase_volt") or [None])[0],
    ),
    EnionSensorDescription(
        key="enion_grid_voltage_l2",
        name="Enion Grid Voltage L2",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        port_prefix=PORT_GRID,
        port_sub="1",
        value_fn=lambda v: (v.get("phase_volt") or [None, None])[1],
    ),
    EnionSensorDescription(
        key="enion_grid_voltage_l3",
        name="Enion Grid Voltage L3",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        port_prefix=PORT_GRID,
        port_sub="1",
        value_fn=lambda v: (v.get("phase_volt") or [None, None, None])[2],
    ),
    EnionSensorDescription(
        key="enion_grid_current_l1",
        name="Enion Grid Current L1",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        port_prefix=PORT_GRID,
        port_sub="1",
        value_fn=lambda v: (v.get("phase_curr") or [None])[0],
    ),
    EnionSensorDescription(
        key="enion_grid_current_l2",
        name="Enion Grid Current L2",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        port_prefix=PORT_GRID,
        port_sub="1",
        value_fn=lambda v: (v.get("phase_curr") or [None, None])[1],
    ),
    EnionSensorDescription(
        key="enion_grid_current_l3",
        name="Enion Grid Current L3",
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
        name="Enion Energy Meter Power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        port_prefix=PORT_ENERGY,
        port_sub="0",
        value_fn=lambda v: v.get("power"),
    ),
    EnionSensorDescription(
        key="enion_energy_meter_energy",
        name="Enion Energy Meter Energy",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        port_prefix=PORT_ENERGY,
        port_sub="0",
        value_fn=lambda v: v.get("energy"),
    ),
    EnionSensorDescription(
        key="enion_energy_meter_voltage_l1",
        name="Enion Energy Meter RMS Voltage L1",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        port_prefix=PORT_ENERGY,
        port_sub="0",
        value_fn=lambda v: (v.get("rms_voltage") or [None])[0],
    ),
    EnionSensorDescription(
        key="enion_energy_meter_voltage_l2",
        name="Enion Energy Meter RMS Voltage L2",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        port_prefix=PORT_ENERGY,
        port_sub="0",
        value_fn=lambda v: (v.get("rms_voltage") or [None, None])[1],
    ),
    EnionSensorDescription(
        key="enion_energy_meter_voltage_l3",
        name="Enion Energy Meter RMS Voltage L3",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        port_prefix=PORT_ENERGY,
        port_sub="0",
        value_fn=lambda v: (v.get("rms_voltage") or [None, None, None])[2],
    ),
    EnionSensorDescription(
        key="enion_energy_meter_current_l1",
        name="Enion Energy Meter Current L1",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        port_prefix=PORT_ENERGY,
        port_sub="0",
        value_fn=lambda v: (v.get("cur_current") or [None])[0],
    ),
    EnionSensorDescription(
        key="enion_energy_meter_current_l2",
        name="Enion Energy Meter Current L2",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        port_prefix=PORT_ENERGY,
        port_sub="0",
        value_fn=lambda v: (v.get("cur_current") or [None, None])[1],
    ),
    EnionSensorDescription(
        key="enion_energy_meter_current_l3",
        name="Enion Energy Meter Current L3",
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
        name="Enion Energy Meter Power Factor L1",
        state_class=SensorStateClass.MEASUREMENT,
        port_prefix=PORT_ENERGY,
        port_sub="0",
        value_fn=lambda v: (v.get("phases") or [{}])[0].get("pf"),
    ),
    EnionSensorDescription(
        key="enion_energy_meter_power_factor_l2",
        name="Enion Energy Meter Power Factor L2",
        state_class=SensorStateClass.MEASUREMENT,
        port_prefix=PORT_ENERGY,
        port_sub="0",
        value_fn=lambda v: (v.get("phases") or [{}, {}])[1].get("pf"),
    ),
    EnionSensorDescription(
        key="enion_energy_meter_power_factor_l3",
        name="Enion Energy Meter Power Factor L3",
        state_class=SensorStateClass.MEASUREMENT,
        port_prefix=PORT_ENERGY,
        port_sub="0",
        value_fn=lambda v: (v.get("phases") or [{}, {}, {}])[2].get("pf"),
    ),
    EnionSensorDescription(
        key="enion_energy_meter_real_power_l1",
        name="Enion Energy Meter Real Power L1",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        port_prefix=PORT_ENERGY,
        port_sub="0",
        value_fn=lambda v: (v.get("phases") or [{}])[0].get("real_power"),
    ),
    EnionSensorDescription(
        key="enion_energy_meter_real_power_l2",
        name="Enion Energy Meter Real Power L2",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        port_prefix=PORT_ENERGY,
        port_sub="0",
        value_fn=lambda v: (v.get("phases") or [{}, {}])[1].get("real_power"),
    ),
    EnionSensorDescription(
        key="enion_energy_meter_real_power_l3",
        name="Enion Energy Meter Real Power L3",
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
        name="Enion Electricity Price (Current Hour)",
        native_unit_of_measurement="ct/kWh",
        device_class=SensorDeviceClass.MONETARY,
        state_class=None,
        port_prefix=PORT_PRICES,
        port_sub="0",
        # Handled specially in EnionPriceSensor
        value_fn=lambda v: None,
    ),
    EnionSensorDescription(
        key="enion_electricity_price_next",
        name="Enion Electricity Price (Next Hour)",
        native_unit_of_measurement="ct/kWh",
        device_class=SensorDeviceClass.MONETARY,
        state_class=None,
        port_prefix=PORT_PRICES,
        port_sub="0",
        value_fn=lambda v: None,
    ),
    # ------------------------------------------------------------------ Weather
    EnionSensorDescription(
        key="enion_weather_temperature",
        name="Enion Outside Temperature",
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
        name="Enion Wind Speed",
        native_unit_of_measurement="m/s",
        device_class=SensorDeviceClass.WIND_SPEED,
        state_class=SensorStateClass.MEASUREMENT,
        port_prefix=PORT_WEATHER,
        port_sub="0",
        value_fn=lambda v: None,
    ),
    EnionSensorDescription(
        key="enion_weather_wind_direction",
        name="Enion Wind Direction",
        port_prefix=PORT_WEATHER,
        port_sub="0",
        # Handled specially in EnionWeatherSensor
        value_fn=lambda v: None,
    ),
    EnionSensorDescription(
        key="enion_weather_sun_condition",
        name="Enion Sun Condition",
        port_prefix=PORT_WEATHER,
        port_sub="0",
        # Handled specially in EnionWeatherSensor
        value_fn=lambda v: None,
    ),
    # ------------------------------------------------------------------ Battery Optimizer (220/0)
    EnionSensorDescription(
        key="enion_battery_optimizer_state",
        name="Enion Battery Optimizer State",
        port_prefix=PORT_OPTIMIZER,
        port_sub="0",
        # Handled specially in EnionOptimizerSensor
        value_fn=lambda v: None,
    ),
    # ------------------------------------------------------------------ User / Account Info
    EnionSensorDescription(
        key="enion_user_area_code",
        name="Enion Area Code",
        port_prefix="user",
        value_fn=lambda v: v.get("area_code"),
        entity_registry_enabled_default=False,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    EnionSensorDescription(
        key="enion_user_area_name",
        name="Enion Area Name",
        port_prefix="user",
        value_fn=lambda v: v.get("area_name"),
        entity_registry_enabled_default=False,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    EnionSensorDescription(
        key="enion_user_country_name",
        name="Enion Country",
        port_prefix="user",
        value_fn=lambda v: v.get("country_name"),
        entity_registry_enabled_default=False,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    EnionSensorDescription(
        key="enion_user_country_iso",
        name="Enion Country ISO Code",
        port_prefix="user",
        value_fn=lambda v: v.get("country_iso_3166"),
        entity_registry_enabled_default=False,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    EnionSensorDescription(
        key="enion_user_currency",
        name="Enion Currency",
        port_prefix="user",
        value_fn=lambda v: v.get("currency"),
        entity_registry_enabled_default=True,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    EnionSensorDescription(
        key="enion_user_last_ip",
        name="Enion Last Login IP",
        port_prefix="user",
        value_fn=lambda v: v.get("last_ip"),
        entity_registry_enabled_default=False,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    EnionSensorDescription(
        key="enion_user_cheap_start_time",
        name="Enion Cheap Transfer Start Time",
        port_prefix="user",
        value_fn=lambda v: v.get("cheap_start_time"),
        entity_registry_enabled_default=False,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    EnionSensorDescription(
        key="enion_user_cheap_end_time",
        name="Enion Cheap Transfer End Time",
        port_prefix="user",
        value_fn=lambda v: v.get("cheap_end_time"),
        entity_registry_enabled_default=False,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    EnionSensorDescription(
        key="enion_user_cheap_transfer_price",
        name="Enion Cheap Transfer Price",
        native_unit_of_measurement="€/kWh",
        port_prefix="user",
        value_fn=lambda v: v.get("cheap_transfer_price"),
        entity_registry_enabled_default=False,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    EnionSensorDescription(
        key="enion_user_contract_address",
        name="Enion Contract Address",
        port_prefix="user",
        value_fn=lambda v: v.get("contract_address"),
        entity_registry_enabled_default=False,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    EnionSensorDescription(
        key="enion_user_contract_name",
        name="Enion Contract Name",
        port_prefix="user",
        value_fn=lambda v: v.get("contract_name"),
        entity_registry_enabled_default=False,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    EnionSensorDescription(
        key="enion_user_contract_type",
        name="Enion Contract Type",
        port_prefix="user",
        value_fn=lambda v: v.get("contract_type"),
        entity_registry_enabled_default=False,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    EnionSensorDescription(
        key="enion_user_electricity_price",
        name="Enion Electricity Price",
        native_unit_of_measurement="€/kWh",
        device_class=SensorDeviceClass.MONETARY,
        port_prefix="user",
        value_fn=lambda v: v.get("electricity_price"),
        entity_registry_enabled_default=False,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    EnionSensorDescription(
        key="enion_user_margin_price",
        name="Enion Margin Price",
        native_unit_of_measurement="€/kWh",
        port_prefix="user",
        value_fn=lambda v: v.get("margin_price"),
        entity_registry_enabled_default=True,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    EnionSensorDescription(
        key="enion_user_transfer_price",
        name="Enion Transfer Price",
        native_unit_of_measurement="€/kWh",
        port_prefix="user",
        value_fn=lambda v: v.get("transfer_price"),
        entity_registry_enabled_default=False,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    EnionSensorDescription(
        key="enion_user_meter_number",
        name="Enion Meter Number",
        port_prefix="user",
        value_fn=lambda v: v.get("meter_number"),
        entity_registry_enabled_default=False,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    EnionSensorDescription(
        key="enion_user_zip_code",
        name="Enion Zip Code",
        port_prefix="user",
        value_fn=lambda v: v.get("zip_code"),
        entity_registry_enabled_default=False,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    EnionSensorDescription(
        key="enion_user_has_cheap_transfer",
        name="Enion Has Cheap Transfer",
        port_prefix="user",
        value_fn=lambda v: v.get("has_cheap_transfer"),
        entity_registry_enabled_default=False,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    EnionSensorDescription(
        key="enion_user_has_reserve_markets",
        name="Enion Has Reserve Markets",
        port_prefix="user",
        value_fn=lambda v: v.get("has_reserve_markets"),
        entity_registry_enabled_default=False,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    EnionSensorDescription(
        key="enion_user_has_accept_reserve_markets",
        name="Enion Has Accepted Reserve Markets",
        port_prefix="user",
        value_fn=lambda v: v.get("has_accept_reserve_markets"),
        entity_registry_enabled_default=True,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    EnionSensorDescription(
        key="enion_user_is_vat_registered",
        name="Enion Is VAT Registered",
        port_prefix="user",
        value_fn=lambda v: v.get("is_vat_registered"),
        entity_registry_enabled_default=False,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    # ------------------------------------------------------------------ Profits
    EnionSensorDescription(
        key="enion_profit_spot_saving_today",
        name="Enion Spot Saving Today",
        native_unit_of_measurement="EUR",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        port_prefix="profits",
        value_fn=lambda v: None,  # handled by EnionProfitSensor
    ),
    EnionSensorDescription(
        key="enion_profit_fcr_total_today",
        name="Enion FCR Earnings Today",
        native_unit_of_measurement="EUR",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        port_prefix="profits",
        value_fn=lambda v: None,
    ),
    EnionSensorDescription(
        key="enion_profit_total_today",
        name="Enion Total Profit Today",
        native_unit_of_measurement="EUR",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        port_prefix="profits",
        value_fn=lambda v: None,
    ),
    EnionSensorDescription(
        key="enion_profit_spot_saving_month",
        name="Enion Spot Saving This Month",
        native_unit_of_measurement="EUR",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        port_prefix="profits",
        value_fn=lambda v: None,
    ),
    EnionSensorDescription(
        key="enion_profit_fcr_total_month",
        name="Enion FCR Earnings This Month",
        native_unit_of_measurement="EUR",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        port_prefix="profits",
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
        elif desc.port_prefix == "user":
            entities.append(EnionUserSensor(coordinator, entry, desc))
        elif desc.port_prefix == "profits":
            entities.append(EnionProfitSensor(coordinator, entry, desc))
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
        self._attr_entity_registry_enabled_default = description.entity_registry_enabled_default
        if description.entity_category:
            self._attr_entity_category = description.entity_category
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
        self._attr_entity_registry_enabled_default = description.entity_registry_enabled_default
        if description.entity_category:
            self._attr_entity_category = description.entity_category

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
        self._attr_entity_registry_enabled_default = description.entity_registry_enabled_default
        if description.entity_category:
            self._attr_entity_category = description.entity_category

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
        self._attr_entity_registry_enabled_default = description.entity_registry_enabled_default
        if description.entity_category:
            self._attr_entity_category = description.entity_category

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


class EnionUserSensor(CoordinatorEntity[EnionCoordinator], SensorEntity):
    """A sensor backed by user account information."""

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
        self._attr_entity_registry_enabled_default = description.entity_registry_enabled_default
        if description.entity_category:
            self._attr_entity_category = description.entity_category

    @property
    def native_value(self) -> Any:
        user_info = self.coordinator.get_user_info()
        return self.entity_description.value_fn(user_info)


# Map sensor key → (period, field) for profit sensors
_PROFIT_SENSOR_MAP: dict[str, tuple[str, str]] = {
    "enion_profit_spot_saving_today": ("today", "spot_saving"),
    "enion_profit_fcr_total_today": ("today", "fcr_total"),
    "enion_profit_total_today": ("today", "total"),
    "enion_profit_spot_saving_month": ("month", "spot_saving"),
    "enion_profit_fcr_total_month": ("month", "fcr_total"),
}


class EnionProfitSensor(CoordinatorEntity[EnionCoordinator], SensorEntity):
    """A sensor showing today's or this month's profit summary."""

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
        self._attr_entity_registry_enabled_default = description.entity_registry_enabled_default
        if description.entity_category:
            self._attr_entity_category = description.entity_category
        period, field = _PROFIT_SENSOR_MAP[description.key]
        self._period = period
        self._field = field

    @property
    def native_value(self) -> float | None:
        if self._period == "today":
            summary = self.coordinator.get_profits_today()
        else:
            summary = self.coordinator.get_profits_month()
        return round(summary[self._field], 4)

