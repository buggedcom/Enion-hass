# Enion for Home Assistant

A [HACS](https://hacs.xyz/) custom integration for [Enion](https://www.enion.fi/) — a Finnish smart energy management system by Sunergos that combines battery storage, solar, grid monitoring, and price-aware optimisation into a single hub.

![preview of enion integration](./images/Integration.png)

## What is Enion?

Enion is a cloud-connected energy management platform aimed at households and small businesses in Finland and the Nordic region. The physical hub (e.g. **Enion Mini 3.0**) connects to:

- Battery / inverter systems
- Solar PV installations
- Grid power meters (via HAN port)
- Relay switches
- A cloud optimiser that uses live electricity spot prices and weather forecasts to schedule charging and discharging automatically

All device data is pushed in real time through Enion's cloud backend and is accessible via the official app at [app.enion.fi](https://app.enion.fi/).

## What is HACS?

[HACS](https://hacs.xyz/) (Home Assistant Community Store) is the standard way to install community-built integrations, themes, and plugins into [Home Assistant](https://www.home-assistant.io/) without modifying the core installation. Once HACS is set up, installing this integration takes only a few clicks.

---

## Features

This integration connects Home Assistant to the Enion cloud using the same API as the official web app. Real-time data (power, battery, prices) arrives instantly via a persistent WebSocket (Phoenix channels). Profit and earnings data is fetched from the REST API every hour and injected into Home Assistant's long-term statistics.

Depending on your Enion setup we can probably expose more entities, however Please create an issue with information from your HA logs.

![preview of enion integration](./images/Integration-Entities.png)

### Sensors

#### Battery

| Entity | Unit | Description |
|---|---|---|
| `sensor.enion_battery_state_of_charge` | % | Current battery charge level |
| `sensor.enion_battery_power` | W | Charge (+) / discharge (−) power |
| `sensor.enion_battery_energy` | Wh | Current battery energy stored |
| `sensor.enion_battery_voltage_l1` | V | AC voltage at inverter (Phase 1) |
| `sensor.enion_battery_voltage_l2` | V | AC voltage at inverter (Phase 2) |
| `sensor.enion_battery_voltage_l3` | V | AC voltage at inverter (Phase 3) |
| `sensor.enion_battery_current_l1` | A | AC current at inverter (Phase 1) |
| `sensor.enion_battery_current_l2` | A | AC current at inverter (Phase 2) |
| `sensor.enion_battery_current_l3` | A | AC current at inverter (Phase 3) |
| `sensor.enion_battery_frequency` | Hz | AC frequency at the inverter |
| `sensor.enion_battery_status` | — | Text status (e.g. `OK`, `Communication Failure`) |

#### Grid

| Entity | Unit | Description |
|---|---|---|
| `sensor.enion_grid_power` | W | Import (+) / export (−) from the grid |
| `sensor.enion_grid_energy_all_time` | Wh | Cumulative grid energy (all time) |
| `sensor.enion_grid_frequency` | Hz | Grid frequency |
| `sensor.enion_grid_voltage_l1` | V | Grid phase voltage (Phase 1) |
| `sensor.enion_grid_voltage_l2` | V | Grid phase voltage (Phase 2) |
| `sensor.enion_grid_voltage_l3` | V | Grid phase voltage (Phase 3) |
| `sensor.enion_grid_current_l1` | A | Grid phase current (Phase 1) |
| `sensor.enion_grid_current_l2` | A | Grid phase current (Phase 2) |
| `sensor.enion_grid_current_l3` | A | Grid phase current (Phase 3) |

#### Energy Meter

| Entity | Unit | Description |
|---|---|---|
| `sensor.enion_energy_meter_power` | W | Household consumption |
| `sensor.enion_energy_meter_energy` | Wh | Cumulative household energy |
| `sensor.enion_energy_meter_rms_voltage_l1` | V | RMS voltage at meter (Phase 1) |
| `sensor.enion_energy_meter_rms_voltage_l2` | V | RMS voltage at meter (Phase 2) |
| `sensor.enion_energy_meter_rms_voltage_l3` | V | RMS voltage at meter (Phase 3) |
| `sensor.enion_energy_meter_current_l1` | A | Current at meter (Phase 1) |
| `sensor.enion_energy_meter_current_l2` | A | Current at meter (Phase 2) |
| `sensor.enion_energy_meter_current_l3` | A | Current at meter (Phase 3) |
| `sensor.enion_energy_meter_power_factor_l1` | — | Power factor (Phase 1) |
| `sensor.enion_energy_meter_power_factor_l2` | — | Power factor (Phase 2) |
| `sensor.enion_energy_meter_power_factor_l3` | — | Power factor (Phase 3) |
| `sensor.enion_energy_meter_real_power_l1` | W | Real power (Phase 1) |
| `sensor.enion_energy_meter_real_power_l2` | W | Real power (Phase 2) |
| `sensor.enion_energy_meter_real_power_l3` | W | Real power (Phase 3) |

#### Electricity Pricing

| Entity | Unit | Description |
|---|---|---|
| `sensor.enion_electricity_price_current_hour` | ct/kWh | Spot price for the current hour |
| `sensor.enion_electricity_price_next_hour` | ct/kWh | Spot price for the next hour |

#### Weather

| Entity | Unit | Description |
|---|---|---|
| `sensor.enion_outside_temperature` | °C | Hourly weather forecast temperature |
| `sensor.enion_wind_speed` | m/s | Hourly weather forecast wind speed |
| `sensor.enion_wind_direction` | — | Hourly weather forecast wind direction (°) |
| `sensor.enion_sun_condition` | — | Hourly weather forecast sun percentage (0–100) |

#### Battery Optimizer

| Entity | Description |
|---|---|
| `sensor.enion_battery_optimizer_state` | Current optimizer state and schedule as attributes |

#### Profits & Earnings

Earnings data is fetched from the Enion REST API every hour using a rolling 90-day window. FCR (Frequency Containment Reserve) prices settle approximately 3 days after delivery — the hourly refresh means backfilled values are picked up automatically without any manual action.

| Entity | Unit | Description |
|---|---|---|
| `sensor.enion_spot_saving_today` | EUR | Battery spot-price arbitrage savings for today |
| `sensor.enion_fcr_earnings_today` | EUR | Combined FCR-D up + down reserve earnings for today |
| `sensor.enion_total_profit_today` | EUR | Total earnings (spot + FCR) for today |
| `sensor.enion_spot_saving_this_month` | EUR | Battery spot-price arbitrage savings for the current month |
| `sensor.enion_fcr_earnings_this_month` | EUR | Combined FCR reserve earnings for the current month |

In addition to the sensor entities above, the integration injects the full 90-day history into Home Assistant's **long-term statistics** under the following IDs. These are accessible via the **Statistics** panel in Developer Tools and can be added to Energy dashboard cards:

| Statistic ID | Unit | Description |
|---|---|---|
| `enion:profit_spot_saving` | EUR | Daily spot-price savings |
| `enion:profit_fcr_down` | EUR | Daily FCR-D down earnings |
| `enion:profit_fcr_up` | EUR | Daily FCR-D up earnings |
| `enion:profit_total` | EUR | Daily combined earnings |

#### User Account & Settings

| Entity | Description |
|---|---|
| `sensor.enion_area_code` | Geographic area code (e.g., FI) |
| `sensor.enion_area_name` | Geographic area name (e.g., Finland) |
| `sensor.enion_country` | Country name |
| `sensor.enion_country_iso_code` | Country ISO 3166 code |
| `sensor.enion_currency` | Account currency (e.g., EUR) |
| `sensor.enion_last_login_ip` | Last login IP address |
| `sensor.enion_contract_name` | Electricity contract name |
| `sensor.enion_contract_type` | Contract type (e.g., FIXED) |
| `sensor.enion_contract_address` | Contract address |
| `sensor.enion_meter_number` | Electric meter number |
| `sensor.enion_zip_code` | ZIP/postal code |
| `sensor.enion_electricity_price` | Current electricity price (€/kWh) |
| `sensor.enion_margin_price` | Electricity margin price (€/kWh) |
| `sensor.enion_transfer_price` | Grid transfer price (€/kWh) |
| `sensor.enion_cheap_transfer_price` | Cheap transfer rate price (€/kWh) |
| `sensor.enion_cheap_transfer_start_time` | Cheap transfer window start time |
| `sensor.enion_cheap_transfer_end_time` | Cheap transfer window end time |
| `sensor.enion_has_cheap_transfer` | Whether cheap transfer is enabled |
| `sensor.enion_has_reserve_markets` | Whether reserve markets are available |
| `sensor.enion_has_accepted_reserve_markets` | Whether reserve markets have been accepted |
| `sensor.enion_is_vat_registered` | Whether account is VAT registered |

### Binary Sensors

| Entity | Description |
|---|---|
| `binary_sensor.enion_device_online` | Whether the Enion hub is connected to the cloud |
| `binary_sensor.enion_relay_1` | On/off state of relay output 1 |
| `binary_sensor.enion_relay_2` | On/off state of relay output 2 |
| `binary_sensor.enion_relay_3` | On/off state of relay output 3 |
| `binary_sensor.enion_relay_4` | On/off state of relay output 4 |
| `binary_sensor.enion_relay_5` | On/off state of relay output 5 |

### Calendars

| Entity | Description |
|---|---|
| `calendar.enion_battery_optimizer_schedule` | Upcoming battery optimiser events showing scheduled charging/discharging windows |
| `calendar.enion_weather_forecast` | Hourly weather forecast with temperature, wind speed, direction, and sun percentage |

**Battery Optimizer Schedule** exposes the future charge/discharge schedule that the Enion cloud optimiser plans for your battery. Each event represents a scheduled optimiser state (e.g. `BATTERY_OPTIMIZER_STATE_CHARGE`, `BATTERY_OPTIMIZER_STATE_NET_ZERO`, `BATTERY_OPTIMIZER_STATE_AVOID_SELL`) and spans from its scheduled start time until the next event begins (or one hour if it is the last event in the schedule).

**Weather Forecast** exposes the hourly weather forecast as calendar events. Each one-hour event includes the temperature and wind speed in the event title, with full details (wind direction, sun percentage) in the event description. When the Enion cloud pushes an updated forecast for a time slot that has already been received, the calendar automatically reflects the latest values — there are no duplicate events.

Both calendars are updated in real time via the WebSocket — no manual refresh is needed. You can display them in Home Assistant dashboards using the built-in **Calendar** card, or use them in automations to act ahead of a scheduled charging window or an incoming weather change.

---

## Requirements

- Home Assistant 2024.1 or later
- HACS installed ([hacs.xyz](https://hacs.xyz/))
- An active Enion account (the same login used for [app.enion.fi](https://app.enion.fi/))
- An Enion hub registered to your account

---

## Installation

### Via HACS (recommended)

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=buggedcom&repository=Enion-hass&category=integration)

1. Open HACS in your Home Assistant sidebar.
2. Go to **Integrations** → click the three-dot menu → **Custom repositories**.
3. Add `https://github.com/buggedcom/Enion-hass` as an **Integration** repository.
4. Search for **Enion** in HACS and click **Download**.
5. Restart Home Assistant.

### Manual

1. Download or clone this repository.
2. Copy the `custom_components/enion` folder into your Home Assistant `config/custom_components/` directory.
3. Restart Home Assistant.

---

## Setup

After installation:

1. Go to **Settings → Devices & Services → Add Integration**.
2. Search for **Enion**.
3. Enter your Enion account **email** and **password**.
4. Click **Submit** — the integration will verify your credentials, discover your device, and begin streaming data.

Your credentials are stored securely in Home Assistant's config entry store (the same mechanism used by all built-in integrations). They are never written to `configuration.yaml` or any plain-text file.

### Re-authentication

If your session expires or you change your password, Home Assistant will prompt you to re-authenticate via a notification. No reconfiguration of automations or entities is needed.

---

## How it works

```
Enion cloud  ──REST──▶  Login + /auth/me       (on startup)
             ──REST──▶  /profits/{port_id}      (on startup, then every hour)
             ◀──WSS──   Phoenix WebSocket        (persistent, real-time)
                              │
                    update / device events
                              │
                    Home Assistant entities + long-term statistics
```

1. On startup the integration logs in, fetches the device profile (`/auth/me`), and seeds all entities with initial values.
2. A Phoenix WebSocket connection is then opened to `wss://app.enion.fi/socket/websocket`, subscribing to the user channel (`web:user:{id}`) and the global channel (`web:global:0`).
3. Every `update` event from the cloud is dispatched immediately to the relevant HA entities — no polling, no delay.
4. Profits are fetched from the REST API on startup and then every hour, covering a rolling 90-day window. Results are injected into HA's long-term statistics so the Energy dashboard shows historical earnings and FCR backfill is picked up automatically.
5. If the WebSocket drops, automatic reconnection uses exponential backoff (30 s → 60 s → … → 10 min cap) to avoid hammering the API.

---

## Reporting Missing Sensors

The integration logs any API data fields that it receives but doesn't currently expose as sensors. If you see sensors in the Enion app that aren't available in Home Assistant, you can help us add them:

### Enable Debug Logging

1. Go to **Settings → Developer Tools → Logs**.
2. At the bottom, enter this service call:

```yaml
service: logger.set_level
data:
  custom_components.enion.coordinator: DEBUG
```

3. Restart Home Assistant.
4. Wait a few minutes for WebSocket updates to arrive.
5. Search the logs for "Unknown keys detected" to find new API fields.

### Submit an Issue

If you find unknown fields, please [open a GitHub issue](https://github.com/buggedcom/Enion-hass/issues) with:
- The port type (e.g. `22` for Battery, `108` for Energy Meter)
- The field names you found
- A description of what the field represents (if you know)

This helps us expand sensor coverage for future releases.

---

## Languages

The integration UI is available in:

- English (`en`)
- Finnish (`fi`)
- Swedish (`sv`)

---

## Supported hardware

Any Enion hub registered to your account should work. The integration has been developed and tested against the **Sunergos Enion Mini 3.0**.

---

## Contributing

Bug reports and pull requests are welcome at [github.com/buggedcom/Enion-hass](https://github.com/buggedcom/Enion-hass/issues).

### Running tests

```bash
pip install -r requirements_test.txt
pytest
```

---

## Disclaimer

This is an unofficial community integration. It is not affiliated with, endorsed by, or supported by Sunergos or Enion, but their wep app API has been used with permission. Use at your own risk.
