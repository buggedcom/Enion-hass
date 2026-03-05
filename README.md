# Enion for Home Assistant

A [HACS](https://hacs.xyz/) custom integration for [Enion](https://www.enion.fi/) — a Finnish smart energy management system by Sunergos that combines battery storage, solar, grid monitoring, and price-aware optimisation into a single hub.

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

This integration connects Home Assistant to the Enion cloud using the same API as the official web app. Data arrives instantly via a persistent WebSocket (Phoenix channels) — there is no polling.

### Sensors

| Entity | Unit | Description |
|---|---|---|
| Battery State of Charge | % | Current battery charge level |
| Battery Power | W | Charge (+) / discharge (−) power |
| Battery Energy | Wh | Cumulative battery energy |
| Battery Voltage | V | AC phase voltage at the inverter |
| Battery Current | A | AC phase current at the inverter |
| Battery Frequency | Hz | AC frequency at the inverter |
| Battery Status | — | Text status (e.g. `charging`, `discharging`, `idle`) |
| Grid Power | W | Import (+) / export (−) from the grid |
| Grid Energy (All Time) | Wh | Cumulative grid energy |
| Grid Frequency | Hz | Grid frequency |
| Grid Voltage L1 | V | Grid phase voltage |
| Grid Current L1 | A | Grid phase current |
| Energy Meter Power | W | Household consumption |
| Energy Meter Energy | Wh | Cumulative household energy |
| Energy Meter RMS Voltage | V | RMS voltage at the energy meter |
| Energy Meter Current | A | Current at the energy meter |
| Electricity Price (Current Hour) | ct/kWh | Live spot price for the current hour |
| Electricity Price (Next Hour) | ct/kWh | Spot price for the next hour |
| Outside Temperature | °C | Weather forecast temperature |
| Wind Speed | m/s | Weather forecast wind speed |

More sensors could be added if so configured in Enion, but they will need to be manually added to the repository at this stage.

### Binary Sensors

| Entity | Description |
|---|---|
| Device Online | Whether the Enion hub is connected to the cloud |
| Relay 1–5 | On/off state of each relay output |

### Calendar

| Entity | Description |
|---|---|
| Battery Optimizer Schedule | Upcoming battery optimiser events as a HA calendar |
| Weather Forecast | Hourly weather forecast as a HA calendar |

**Battery Optimizer Schedule** exposes the future charge/discharge schedule that the Enion cloud optimiser plans for your battery. Each event represents a scheduled optimiser state (e.g. `CHARGE`, `NET_ZERO`, `AVOID_SELL`) and spans from its scheduled start time until the next event begins (or one hour if it is the last event in the schedule).

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

1. Open HACS in your Home Assistant sidebar.
2. Go to **Integrations** → click the three-dot menu → **Custom repositories**.
3. Add `https://github.com/ollieread/enion-hacs` as an **Integration** repository.
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
Enion cloud  ──REST──▶  Login + /auth/me  (on startup)
             ◀──WSS──   Phoenix WebSocket  (persistent, real-time)
                              │
                    update / device events
                              │
                    Home Assistant entities
```

1. On startup the integration logs in, fetches the device profile (`/auth/me`), and seeds all entities with initial values.
2. A Phoenix WebSocket connection is then opened to `wss://app.enion.fi/socket/websocket`, subscribing to the user channel (`web:user:{id}`) and the global channel (`web:global:0`).
3. Every `update` event from the cloud is dispatched immediately to the relevant HA entities — no polling, no delay.
4. If the connection drops, automatic reconnection uses exponential backoff (30 s → 60 s → … → 10 min cap) to avoid hammering the API.

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

Bug reports and pull requests are welcome at [github.com/ollieread/enion-hacs](https://github.com/ollieread/enion-hacs/issues).

### Running tests

```bash
pip install -r requirements_test.txt
pytest
```

---

## Disclaimer

This is an unofficial community integration. It is not affiliated with, endorsed by, or supported by Sunergos or Enion, but their wep app API has been used with permission. Use at your own risk.
