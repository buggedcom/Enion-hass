"""Unit tests for api.py — EnionClient and EnionWebSocket."""
from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, call, patch

import aiohttp
import pytest

from custom_components.enion.api import (
    EnionAuthError,
    EnionApiError,
    EnionClient,
    EnionWebSocket,
)
from tests.conftest import LOGIN_RESPONSE, ME_RESPONSE


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_response(status: int = 200, json_data: dict | None = None) -> MagicMock:
    """Return a mock aiohttp response that works as an async context manager."""
    resp = MagicMock()
    resp.status = status
    resp.json = AsyncMock(return_value=json_data or {})
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=resp)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


def _make_session(post_status=200, post_data=None, get_status=200, get_data=None) -> MagicMock:
    """Return a mock aiohttp session. Uses MagicMock so .post()/.get() return
    context managers directly (not coroutines)."""
    session = MagicMock()
    session.post.return_value = _make_response(post_status, post_data)
    session.get.return_value = _make_response(get_status, get_data)
    return session


def _ws_message(msg_type, data=None) -> MagicMock:
    msg = MagicMock()
    msg.type = msg_type
    msg.data = data
    return msg


async def _ws_iter(*messages):
    """Async generator yielding the given mock WS messages."""
    for m in messages:
        yield m


# ---------------------------------------------------------------------------
# EnionClient — login
# ---------------------------------------------------------------------------


class TestEnionClientLogin:
    async def test_success_returns_data_and_stores_token(self):
        session = _make_session(post_data=LOGIN_RESPONSE)
        client = EnionClient(session)

        result = await client.login("a@b.com", "pw")

        assert result == LOGIN_RESPONSE
        assert client.ws_token == LOGIN_RESPONSE["token"]

    async def test_sends_correct_payload(self):
        session = _make_session(post_data=LOGIN_RESPONSE)
        client = EnionClient(session)

        await client.login("user@test.com", "secret")

        session.post.assert_called_once()
        _, kwargs = session.post.call_args
        assert kwargs["json"]["email"] == "user@test.com"
        assert kwargs["json"]["password"] == "secret"
        assert kwargs["json"]["language"] == "en"

    async def test_401_raises_auth_error(self):
        session = _make_session(post_status=401)
        client = EnionClient(session)

        with pytest.raises(EnionAuthError):
            await client.login("a@b.com", "wrong")

    async def test_non_200_raises_api_error(self):
        session = _make_session(post_status=500)
        client = EnionClient(session)

        with pytest.raises(EnionApiError):
            await client.login("a@b.com", "pw")

    async def test_timeout_propagates(self):
        session = MagicMock()
        session.post.side_effect = asyncio.TimeoutError
        client = EnionClient(session)

        with pytest.raises(asyncio.TimeoutError):
            await client.login("a@b.com", "pw")

    async def test_null_token_stored_as_none(self):
        session = _make_session(post_data={"token": None})
        client = EnionClient(session)

        await client.login("a@b.com", "pw")

        assert client.ws_token is None


# ---------------------------------------------------------------------------
# EnionClient — fetch_me
# ---------------------------------------------------------------------------


class TestEnionClientFetchMe:
    async def test_success_parses_user_id_and_location(self):
        session = _make_session(get_data=ME_RESPONSE)
        client = EnionClient(session)

        await client.fetch_me()

        assert client.user_id == "2628"
        assert client.location_id == "1938"

    async def test_uses_token_from_login_when_me_token_is_null(self):
        # Login first to set the token, then fetch_me (which has token=null)
        session = MagicMock()
        session.post.return_value = _make_response(200, LOGIN_RESPONSE)
        session.get.return_value = _make_response(200, ME_RESPONSE)
        client = EnionClient(session)

        await client.login("a@b.com", "pw")
        await client.fetch_me()

        assert client.ws_token == LOGIN_RESPONSE["token"]

    async def test_falls_back_to_me_token_when_login_token_missing(self):
        me_with_token = {**ME_RESPONSE, "token": "me_token_123"}
        session = _make_session(get_data=me_with_token)
        client = EnionClient(session)

        await client.fetch_me()

        assert client.ws_token == "me_token_123"

    async def test_401_raises_auth_error(self):
        session = _make_session(get_status=401)
        client = EnionClient(session)

        with pytest.raises(EnionAuthError):
            await client.fetch_me()

    async def test_non_200_raises_api_error(self):
        session = _make_session(get_status=503)
        client = EnionClient(session)

        with pytest.raises(EnionApiError):
            await client.fetch_me()

    async def test_returns_full_response(self):
        session = _make_session(get_data=ME_RESPONSE)
        client = EnionClient(session)

        result = await client.fetch_me()

        assert result == ME_RESPONSE

    async def test_logs_warning_when_no_token_anywhere(self):
        no_token_me = {**ME_RESPONSE, "token": None}
        session = _make_session(get_data=no_token_me)
        client = EnionClient(session)

        with patch("custom_components.enion.api._LOGGER") as mock_logger:
            await client.fetch_me()
            mock_logger.warning.assert_called_once()


# ---------------------------------------------------------------------------
# EnionWebSocket — connect / disconnect
# ---------------------------------------------------------------------------


class TestEnionWebSocketConnect:
    def _make_ws(self, messages=()) -> MagicMock:
        ws = MagicMock()
        ws.closed = False
        ws.send_str = AsyncMock()
        ws.close = AsyncMock()
        ws.__aiter__ = lambda self: _ws_iter(*messages)
        return ws

    async def test_connect_joins_user_and_global_channels(self):
        mock_ws = self._make_ws()
        on_update = MagicMock()
        on_device = MagicMock()
        session = MagicMock()

        async def fake_wait_for(coro, timeout=None):
            return mock_ws

        with patch("custom_components.enion.api.asyncio.wait_for", side_effect=fake_wait_for):
            ws_client = EnionWebSocket(
                session=session,
                ws_token="tok",
                user_id="2628",
                on_update=on_update,
                on_device=on_device,
            )
            await ws_client.connect()

        sent = [call.args[0] for call in mock_ws.send_str.call_args_list]
        topics = [json.loads(s)[2] for s in sent]
        assert "web:user:2628" in topics
        assert "web:global:0" in topics

    async def test_disconnect_does_not_trigger_on_disconnect_callback(self):
        mock_ws = self._make_ws()
        on_disconnect = MagicMock()
        session = MagicMock()

        async def fake_wait_for(coro, timeout=None):
            return mock_ws

        with patch("custom_components.enion.api.asyncio.wait_for", side_effect=fake_wait_for):
            ws_client = EnionWebSocket(
                session=session,
                ws_token="tok",
                user_id="2628",
                on_update=MagicMock(),
                on_device=MagicMock(),
                on_disconnect=on_disconnect,
            )
            await ws_client.connect()
            await ws_client.disconnect()
            # Allow the listener task to finish
            await asyncio.sleep(0)

        on_disconnect.assert_not_called()

    async def test_unexpected_close_triggers_on_disconnect(self):
        close_msg = _ws_message(aiohttp.WSMsgType.CLOSED)
        mock_ws = self._make_ws(messages=[close_msg])
        on_disconnect = MagicMock()
        session = MagicMock()

        async def fake_wait_for(coro, timeout=None):
            return mock_ws

        with patch("custom_components.enion.api.asyncio.wait_for", side_effect=fake_wait_for):
            ws_client = EnionWebSocket(
                session=session,
                ws_token="tok",
                user_id="2628",
                on_update=MagicMock(),
                on_device=MagicMock(),
                on_disconnect=on_disconnect,
            )
            await ws_client.connect()
            # Wait for listener to process the close message
            await asyncio.sleep(0.05)

        on_disconnect.assert_called_once()


# ---------------------------------------------------------------------------
# EnionWebSocket — message dispatch
# ---------------------------------------------------------------------------


class TestEnionWebSocketMessages:
    def _phoenix_msg(self, event: str, payload: dict, topic: str = "web:user:2628") -> MagicMock:
        data = json.dumps([None, "1", topic, event, payload])
        return _ws_message(aiohttp.WSMsgType.TEXT, data)

    async def test_update_event_dispatched_to_on_update(self):
        payload = {"port_id": 104230, "port_number": "22/0", "values": {"soc": 80}}
        update_msg = self._phoenix_msg("update", payload)
        mock_ws = MagicMock()
        mock_ws.closed = False
        mock_ws.send_str = AsyncMock()
        mock_ws.close = AsyncMock()
        mock_ws.__aiter__ = lambda self: _ws_iter(update_msg)

        on_update = MagicMock()

        async def fake_wait_for(coro, timeout=None):
            return mock_ws

        with patch("custom_components.enion.api.asyncio.wait_for", side_effect=fake_wait_for):
            ws_client = EnionWebSocket(
                session=MagicMock(),
                ws_token="tok",
                user_id="2628",
                on_update=on_update,
                on_device=MagicMock(),
            )
            await ws_client.connect()
            await asyncio.sleep(0.05)

        on_update.assert_called_once_with(payload)

    async def test_device_event_dispatched_to_on_device(self):
        payload = {"hw_id": "0B8D7EFB", "values": {"online": True}}
        device_msg = self._phoenix_msg("device", payload)
        mock_ws = MagicMock()
        mock_ws.closed = False
        mock_ws.send_str = AsyncMock()
        mock_ws.close = AsyncMock()
        mock_ws.__aiter__ = lambda self: _ws_iter(device_msg)

        on_device = MagicMock()

        async def fake_wait_for(coro, timeout=None):
            return mock_ws

        with patch("custom_components.enion.api.asyncio.wait_for", side_effect=fake_wait_for):
            ws_client = EnionWebSocket(
                session=MagicMock(),
                ws_token="tok",
                user_id="2628",
                on_update=MagicMock(),
                on_device=on_device,
            )
            await ws_client.connect()
            await asyncio.sleep(0.05)

        on_device.assert_called_once_with(payload)

    async def test_malformed_message_does_not_raise(self):
        bad_msg = _ws_message(aiohttp.WSMsgType.TEXT, "not-json{{{")
        mock_ws = MagicMock()
        mock_ws.closed = False
        mock_ws.send_str = AsyncMock()
        mock_ws.close = AsyncMock()
        mock_ws.__aiter__ = lambda self: _ws_iter(bad_msg)

        async def fake_wait_for(coro, timeout=None):
            return mock_ws

        with patch("custom_components.enion.api.asyncio.wait_for", side_effect=fake_wait_for):
            ws_client = EnionWebSocket(
                session=MagicMock(),
                ws_token="tok",
                user_id="2628",
                on_update=MagicMock(),
                on_device=MagicMock(),
            )
            await ws_client.connect()
            await asyncio.sleep(0.05)  # must not raise

    async def test_phoenix_reply_silently_ignored(self):
        reply = self._phoenix_msg("phx_reply", {"status": "ok", "response": {}}, topic="phoenix")
        mock_ws = MagicMock()
        mock_ws.closed = False
        mock_ws.send_str = AsyncMock()
        mock_ws.close = AsyncMock()
        mock_ws.__aiter__ = lambda self: _ws_iter(reply)

        on_update = MagicMock()
        on_device = MagicMock()

        async def fake_wait_for(coro, timeout=None):
            return mock_ws

        with patch("custom_components.enion.api.asyncio.wait_for", side_effect=fake_wait_for):
            ws_client = EnionWebSocket(
                session=MagicMock(),
                ws_token="tok",
                user_id="2628",
                on_update=on_update,
                on_device=on_device,
            )
            await ws_client.connect()
            await asyncio.sleep(0.05)

        on_update.assert_not_called()
        on_device.assert_not_called()
