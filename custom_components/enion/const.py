"""Constants for the Enion integration."""

DOMAIN = "enion"

# Configuration keys
CONF_LOCATION_ID = "location_id"

# API
API_BASE = "https://app.enion.fi/api/v1"
API_LOGIN = f"{API_BASE}/auth/login"
API_ME = f"{API_BASE}/auth/me"
API_WIDGETS = f"{API_BASE}/widgets"
API_PRICES = f"{API_BASE}/data/prices"
API_HISTORY_POWER = f"{API_BASE}/history/power"

# WebSocket
WS_URL = "wss://app.enion.fi/socket/websocket"
WS_VERSION = "2.0.0"

# Phoenix channel events
PHOENIX_JOIN = "phx_join"
PHOENIX_REPLY = "phx_reply"
PHOENIX_HEARTBEAT = "heartbeat"
PHOENIX_LEAVE = "phx_leave"
PHOENIX_CLOSE = "phx_close"
PHOENIX_ERROR = "phx_error"

WS_EVENT_UPDATE = "update"
WS_EVENT_DEVICE = "device"
WS_EVENT_FLAGS = "flags"

# Port type identifiers (port_number prefix)
PORT_RELAY = "3"           # 3/0–3/4: relay/switch
PORT_BATTERY = "22"        # 22/0: battery/inverter
PORT_SYSTEM = "100"        # 100/0: system/firmware
PORT_CLOCK = "106"         # 106/0: clock/schedule
PORT_GRID = "107"          # 107/0–107/1: grid power meter
PORT_ENERGY = "108"        # 108/0: energy meter
PORT_LOAD = "211"          # 211/0–211/7: load controllers
PORT_PRICES = "212"        # 212/0–212/1: electricity price feed
PORT_WEATHER = "214"       # 214/0: weather forecast
PORT_OPTIMIZER = "220"     # 220/0: battery optimizer

# Data store keys
DATA_DEVICE = "device"
DATA_PORTS = "ports"
DATA_PRICES = "prices"
DATA_WEATHER = "weather"
DATA_OPTIMIZER = "optimizer"
