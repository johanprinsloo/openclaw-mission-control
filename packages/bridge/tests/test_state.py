"""Tests for SQLite state persistence."""

import pytest

from mc_bridge.state import BridgeState


@pytest.fixture
async def state(tmp_path):
    s = BridgeState(str(tmp_path / "test.db"))
    await s.open()
    yield s
    await s.close()


async def test_session_mapping_crud(state: BridgeState):
    # Create
    await state.create_session_mapping(
        "mc:acme:project:ch1", "agent-1", "acme", "ch1", "project"
    )

    # Read
    key = await state.get_session_key("ch1", "agent-1")
    assert key == "mc:acme:project:ch1"

    ch = await state.get_channel_id("mc:acme:project:ch1")
    assert ch == "ch1"

    # List
    sessions = await state.list_sessions("agent-1")
    assert len(sessions) == 1

    # Delete
    await state.delete_session_mapping("mc:acme:project:ch1")
    key = await state.get_session_key("ch1", "agent-1")
    assert key is None


async def test_event_cursor(state: BridgeState):
    assert await state.get_cursor("agent-1") is None

    await state.save_cursor("agent-1", "acme", "42")
    assert await state.get_cursor("agent-1") == "42"

    await state.save_cursor("agent-1", "acme", "99")
    assert await state.get_cursor("agent-1") == "99"
