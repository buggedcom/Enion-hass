"""Enion API client — handles REST auth and Phoenix WebSocket channel."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Callable

import aiohttp

from .const import (
    API_LOGIN,
    API_ME,
    WS_URL,
    WS_VERSION,
    WS_EVENT_UPDATE,
    WS_EVENT_DEVICE,
    WS_EVENT_FLAGS,
    PHOENIX_JOIN,
    PHOENIX_HEARTBEAT,
    PHOENIX_REPLY,
    PHOENIX_ERROR,
    PHOENIX_CLOSE,
)

_LOGGER = logging.getLogger(__name__)

# Heartbeat interval in seconds (server expects <= 60 s)
_HEARTBEAT_INTERVAL = 30

# Timeout for REST API calls
_HTTP_TIMEOUT = aiohttp.ClientTimeout(total=30)

# Timeout for the WebSocket upgrade handshake
_WS_CONNECT_TIMEOUT = 20


class EnionAuthError(Exception):
    """Raised when login fails."""


class EnionApiError(Exception):
    """Raised on unexpected API errors."""


class EnionClient:
    """Thin async client for the Enion cloud API."""

    def __init__(self, session: aiohttp.ClientSession) -> None:
        self._session = session
        self._ws_token: str | None = None
        self._user_id: str | None = None
        self._location_id: str | None = None

    # ------------------------------------------------------------------
    # REST helpers
    # ------------------------------------------------------------------

    async def login(self, email: str, password: str) -> dict[str, Any]:
        """POST /api/v1/auth/login.

        Sets the session cookie on the shared aiohttp session so subsequent
        calls are authenticated automatically.
        Returns the parsed JSON body which contains the WS token.
        """
        payload = {"email": email, "password": password, "language": "en"}
        _LOGGER.debug("Attempting login to %s with email: %s", API_LOGIN, email)
        async with self._session.post(
            API_LOGIN,
            json=payload,
            timeout=_HTTP_TIMEOUT
        ) as resp:
            _LOGGER.debug("Login response status: %d", resp.status)
            if resp.status == 401:
                _LOGGER.warning("Login failed: Invalid credentials for email %s", email)
                raise EnionAuthError("Invalid credentials")
            if resp.status != 200:
                try:
                    error_body = await resp.text()
                    _LOGGER.error("Login failed with HTTP %d: %s", resp.status, error_body)
                except Exception:
                    _LOGGER.error("Login failed with HTTP %d", resp.status)
                raise EnionApiError(f"Login failed with HTTP {resp.status}")
            data = await resp.json()
            _LOGGER.debug("Login successful, token received: %s", bool(data.get("token")))
            # The login response contains a token used for the WebSocket
            self._ws_token = data.get("token")
            return data

    async def fetch_me(self) -> dict[str, Any]:
        """GET /api/v1/auth/me — returns full user/account/location profile.

        Response shape:
          { "user": {"id": 2628, ...}, "token": <str|null>,
            "devices": [...], "locations": [{"id": 1938, ...}], ... }
        """
        _LOGGER.debug("Fetching /auth/me")

        # Use the token from login as a Bearer header
        headers = {}
        if self._ws_token:
            headers["Authorization"] = f"Bearer {self._ws_token}"

        async with self._session.get(
            API_ME,
            timeout=_HTTP_TIMEOUT,
            headers=headers
        ) as resp:
            _LOGGER.debug("/auth/me response status: %d", resp.status)
            if resp.status == 401:
                _LOGGER.warning("Session expired or invalid")
                raise EnionAuthError("Session expired")
            if resp.status != 200:
                try:
                    error_body = await resp.text()
                    _LOGGER.error("/auth/me failed with HTTP %d: %s", resp.status, error_body)
                except Exception:
                    _LOGGER.error("/auth/me failed with HTTP %d", resp.status)
                raise EnionApiError(f"/auth/me returned HTTP {resp.status}")
            data = await resp.json()
            _LOGGER.debug("/auth/me successful, found %d devices", len(data.get("devices", [])))

            self._user_id = str(data["user"]["id"])

            locations = data.get("locations") or []
            if locations:
                self._location_id = str(locations[0]["id"])

            # Token is null in /me when it comes from the login response;
            # fall back gracefully in case a future API version puts it here.
            if not self._ws_token:
                self._ws_token = data.get("token") or None

            if not self._ws_token:
                _LOGGER.warning(
                    "No WebSocket token found in login or /auth/me responses. "
                    "Real-time updates will not be available."
                )

            return data

    @property
    def user_id(self) -> str | None:
        return self._user_id

    @property
    def location_id(self) -> str | None:
        return self._location_id

    @property
    def ws_token(self) -> str | None:
        return self._ws_token


class EnionWebSocket:
    """Phoenix channel WebSocket client for real-time Enion data.

    Subscribes to ``web:user:{user_id}`` and dispatches incoming
    ``update``, ``device``, and ``flags`` events to registered callbacks.
    """

    def __init__(
        self,
        session: aiohttp.ClientSession,
        ws_token: str,
        user_id: str,
        on_update: Callable[[dict[str, Any]], None],
        on_device: Callable[[dict[str, Any]], None],
        on_disconnect: Callable[[], None] | None = None,
    ) -> None:
        self._session = session
        self._ws_token = ws_token
        self._user_id = user_id
        self._on_update = on_update
        self._on_device = on_device
        self._on_disconnect = on_disconnect

        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._task: asyncio.Task | None = None
        self._heartbeat_task: asyncio.Task | None = None
        self._ref = 0
        self._connected = False
        # Set to True before cancelling tasks so the finally block in
        # _listen() does not fire the on_disconnect callback.
        self._shutting_down = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Open the WebSocket and start background listener + heartbeat."""
        url = (
            f"{WS_URL}?token={self._ws_token}"
            f"&vsn={WS_VERSION}"
        )
        # Pre-truncate the token so the full JWT is never stored in a log record
        # argument (Python's lazy % formatting keeps raw args in the LogRecord).
        token_prefix = (self._ws_token or "")[:8]
        _LOGGER.debug(
            "Connecting to Enion WebSocket at %s (token=%s…)",
            WS_URL,
            token_prefix,
        )
        self._ws = await asyncio.wait_for(
            self._session.ws_connect(url),
            timeout=_WS_CONNECT_TIMEOUT,
        )
        self._connected = True
        self._shutting_down = False
        await self._join_channel(f"web:user:{self._user_id}")
        await self._join_channel("web:global:0")
        self._task = asyncio.create_task(self._listen())
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

    async def disconnect(self) -> None:
        """Close the WebSocket gracefully without triggering a reconnect."""
        self._shutting_down = True
        self._connected = False
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
        if self._task:
            self._task.cancel()
        if self._ws and not self._ws.closed:
            await self._ws.close()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _next_ref(self) -> str:
        self._ref += 1
        return str(self._ref)

    def _make_message(
        self,
        join_ref: str | None,
        topic: str,
        event: str,
        payload: Any,
    ) -> str:
        """Encode a Phoenix message as a JSON array."""
        return json.dumps([join_ref, self._next_ref(), topic, event, payload])

    async def _send(self, msg: str) -> None:
        if self._ws and not self._ws.closed:
            await self._ws.send_str(msg)

    async def _join_channel(self, topic: str) -> None:
        ref = self._next_ref()
        msg = json.dumps([ref, ref, topic, PHOENIX_JOIN, {}])
        await self._send(msg)
        _LOGGER.debug("Joined Phoenix channel: %s", topic)

    async def _heartbeat_loop(self) -> None:
        while self._connected:
            await asyncio.sleep(_HEARTBEAT_INTERVAL)
            msg = self._make_message(None, "phoenix", PHOENIX_HEARTBEAT, {})
            await self._send(msg)

    async def _listen(self) -> None:
        try:
            async for msg in self._ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    # Catch per-message errors so a single bad payload never
                    # kills the whole listener and forces an unnecessary reconnect.
                    try:
                        await self._handle_text(msg.data)
                    except Exception as exc:  # noqa: BLE001
                        _LOGGER.error(
                            "Error processing WebSocket message: %s",
                            exc,
                            exc_info=True,
                        )
                elif msg.type in (
                    aiohttp.WSMsgType.CLOSED,
                    aiohttp.WSMsgType.ERROR,
                ):
                    _LOGGER.warning("WebSocket closed/error: %s", msg)
                    break
        except asyncio.CancelledError:
            pass
        except Exception as exc:  # noqa: BLE001
            _LOGGER.error("WebSocket listener fatal error: %s", exc, exc_info=True)
        finally:
            self._connected = False
            # Only trigger reconnect for unexpected disconnects, not intentional ones.
            if not self._shutting_down and self._on_disconnect:
                self._on_disconnect()

    async def _handle_text(self, raw: str) -> None:
        try:
            # Phoenix message format: [join_ref, ref, topic, event, payload]
            msg = json.loads(raw)
            if not isinstance(msg, list) or len(msg) != 5:
                return
            _join_ref, _ref, _topic, event, payload = msg
            if not isinstance(payload, dict):
                return

            if event == WS_EVENT_UPDATE:
                self._on_update(payload)
            elif event == WS_EVENT_DEVICE:
                self._on_device(payload)
            elif event in (PHOENIX_REPLY, PHOENIX_ERROR, PHOENIX_CLOSE):
                pass  # silently ignore control frames
            else:
                _LOGGER.debug("Unhandled WS event '%s': %s", event, payload)
        except (json.JSONDecodeError, ValueError) as exc:
            _LOGGER.debug("Failed to parse WS message: %.200s — %s", raw, exc)
