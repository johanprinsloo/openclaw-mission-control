"""
Integration tests: SSE → Bridge → Gateway → REST round-trip.
"""

import asyncio
import os

import httpx
import pytest

from mc_bridge.bridge import CommsBridge
from mc_bridge.config import BridgeConfig

os.environ["TEST_MC_API_KEY"] = "test-key-123"
os.environ["TEST_GW_KEY"] = "test-gw-key"

CHANNEL_ID = "ch_test_001"


async def wait_for_message(
    client: httpx.AsyncClient,
    mc_url: str,
    channel_id: str,
    containing: str,
    timeout: float = 10.0,
) -> dict | None:
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        r = await client.get(f"{mc_url}/api/v1/channels/{channel_id}/messages")
        if r.status_code == 200:
            for msg in r.json():
                if containing in msg.get("content", ""):
                    return msg
        await asyncio.sleep(0.3)
    return None


@pytest.mark.asyncio
async def test_message_round_trip(bridge_config_dict):
    mc_url = bridge_config_dict["mission_control"]["url"]
    config = BridgeConfig.model_validate(bridge_config_dict)
    bridge = CommsBridge(config)
    await bridge.start()

    try:
        await asyncio.sleep(2.0)

        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"{mc_url}/api/v1/channels/{CHANNEL_ID}/messages",
                json={"content": "Hello agent!", "sender_id": "user_human", "sender_name": "Human"},
            )
            assert r.status_code == 200

            msg = await wait_for_message(client, mc_url, CHANNEL_ID, "Agent response to: Hello agent!")
            assert msg is not None, "Agent response not found in MC channel"
            assert msg["sender_id"] == "test_agent"
    finally:
        await bridge.stop()


@pytest.mark.asyncio
async def test_command_round_trip(bridge_config_dict):
    mc_url = bridge_config_dict["mission_control"]["url"]
    config = BridgeConfig.model_validate(bridge_config_dict)
    bridge = CommsBridge(config)
    await bridge.start()

    try:
        await asyncio.sleep(2.0)

        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"{mc_url}/api/v1/channels/{CHANNEL_ID}/messages",
                json={"content": "/status", "sender_id": "user_human", "sender_name": "Human"},
            )
            assert r.status_code == 200

            msg = await wait_for_message(client, mc_url, CHANNEL_ID, "Active tasks: 3")
            assert msg is not None, "Status output not found in MC channel"
    finally:
        await bridge.stop()


@pytest.mark.asyncio
async def test_session_persistence(bridge_config_dict):
    mc_url = bridge_config_dict["mission_control"]["url"]
    config = BridgeConfig.model_validate(bridge_config_dict)
    bridge = CommsBridge(config)
    await bridge.start()

    try:
        await asyncio.sleep(2.0)

        async with httpx.AsyncClient() as client:
            await client.post(
                f"{mc_url}/api/v1/channels/{CHANNEL_ID}/messages",
                json={"content": "First message", "sender_id": "user_human"},
            )
            await wait_for_message(client, mc_url, CHANNEL_ID, "Agent response to: First message")

        from mc_bridge.state import BridgeState
        state = BridgeState(bridge_config_dict["state"]["db_path"])
        await state.open()
        sessions = await state.list_sessions("test-agent")
        assert len(sessions) >= 1
        assert any(s["channel_id"] == CHANNEL_ID for s in sessions)
        await state.close()
    finally:
        await bridge.stop()


@pytest.mark.asyncio
async def test_cursor_resume(bridge_config_dict):
    mc_url = bridge_config_dict["mission_control"]["url"]
    config = BridgeConfig.model_validate(bridge_config_dict)

    # First run
    bridge = CommsBridge(config)
    await bridge.start()
    await asyncio.sleep(2.0)

    async with httpx.AsyncClient() as client:
        await client.post(
            f"{mc_url}/api/v1/channels/{CHANNEL_ID}/messages",
            json={"content": "Before restart", "sender_id": "user_human"},
        )
        await wait_for_message(client, mc_url, CHANNEL_ID, "Agent response to: Before restart")

    await bridge.stop()

    # Post while bridge is down
    async with httpx.AsyncClient() as client:
        await client.post(
            f"{mc_url}/api/v1/channels/{CHANNEL_ID}/messages",
            json={"content": "While offline", "sender_id": "user_human"},
        )

    # Second run
    bridge2 = CommsBridge(config)
    await bridge2.start()

    try:
        await asyncio.sleep(3.0)

        async with httpx.AsyncClient() as client:
            msg = await wait_for_message(
                client, mc_url, CHANNEL_ID, "Agent response to: While offline"
            )
            assert msg is not None, "Missed message not processed after restart"
    finally:
        await bridge2.stop()
