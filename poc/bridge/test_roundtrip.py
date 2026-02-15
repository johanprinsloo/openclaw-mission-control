"""
Test script for POC-6: Comms Bridge ↔ Mission Control Round-Trip.

Starts MC server, Mock Gateway, and Bridge, then validates:
1. Message round-trip (human → MC → Bridge → Gateway → MC)
2. Command round-trip (/status → MC → Bridge → Gateway → MC)
3. Session mapping persistence in SQLite
4. Cursor resume after Bridge restart
"""

import asyncio
import json
import os
import signal
import sqlite3
import subprocess
import sys
import time

import httpx

MC_URL = "http://127.0.0.1:8100"
GW_URL = "http://127.0.0.1:8200"
BRIDGE_DB = "bridge_state.db"


def cleanup_dbs():
    for f in ["mc_server.db", "bridge_state.db"]:
        if os.path.exists(f):
            os.remove(f)


def start_process(cmd: list[str]) -> subprocess.Popen:
    return subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        cwd=os.path.dirname(os.path.abspath(__file__)),
    )


async def wait_healthy(url: str, label: str, timeout: float = 10.0):
    async with httpx.AsyncClient() as client:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                r = await client.get(f"{url}/health")
                if r.status_code == 200:
                    print(f"  ✓ {label} healthy")
                    return
            except httpx.ConnectError:
                pass
            await asyncio.sleep(0.3)
    raise TimeoutError(f"{label} did not become healthy within {timeout}s")


async def wait_for_message(client: httpx.AsyncClient, channel_id: str, containing: str, timeout: float = 5.0):
    """Poll messages until one containing the expected text appears."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        r = await client.get(f"{MC_URL}/api/v1/channels/{channel_id}/messages")
        r.raise_for_status()
        messages = r.json()
        for msg in messages:
            if containing in msg["content"]:
                return msg
        await asyncio.sleep(0.3)
    raise TimeoutError(f"Message containing '{containing}' not found within {timeout}s")


async def run_tests():
    print("\n" + "=" * 60)
    print("POC-6: Comms Bridge ↔ Mission Control Round-Trip")
    print("=" * 60)

    cleanup_dbs()
    procs = []

    try:
        # Start services
        print("\n[1] Starting services...")
        mc = start_process([sys.executable, "mc_server.py"])
        gw = start_process([sys.executable, "mock_gateway.py"])
        procs.extend([mc, gw])

        await wait_healthy(MC_URL, "MC Server")
        await wait_healthy(GW_URL, "Mock Gateway")

        bridge = start_process([sys.executable, "bridge.py"])
        procs.append(bridge)
        await asyncio.sleep(1.5)  # Let Bridge connect SSE
        print("  ✓ Bridge started")

        async with httpx.AsyncClient() as client:
            # Get channel ID
            r = await client.get(f"{MC_URL}/api/v1/channels")
            channels = r.json()
            ch_id = channels[0]["id"]
            print(f"  Channel: {channels[0]['name']} ({ch_id[:8]}...)")

            # --- Test 1: Message Round-Trip ---
            print("\n[2] Test: Message Round-Trip")
            r = await client.post(
                f"{MC_URL}/api/v1/channels/{ch_id}/messages",
                json={"content": "Hello agent, please help!", "sender_id": "user_human", "sender_name": "Human User"},
            )
            assert r.status_code == 200, f"Post failed: {r.status_code}"
            print("  → Message posted by human")

            reply = await wait_for_message(client, ch_id, "Agent response to: Hello agent, please help!")
            print(f"  ← Agent replied: {reply['content']}")
            assert reply["sender_id"] == "agent_builder_01"
            print("  ✓ Message round-trip PASSED")

            # --- Test 2: Command Round-Trip ---
            print("\n[3] Test: Command Round-Trip (/status)")
            r = await client.post(
                f"{MC_URL}/api/v1/channels/{ch_id}/messages",
                json={"content": "/status", "sender_id": "user_human", "sender_name": "Human User"},
            )
            assert r.status_code == 200
            print("  → /status command posted")

            reply = await wait_for_message(client, ch_id, "Active tasks: 3")
            print(f"  ← Status output: {reply['content'][:60]}...")
            print("  ✓ Command round-trip PASSED")

            # --- Test 3: Session Mapping in SQLite ---
            print("\n[4] Test: Session Mapping Persistence")
            conn = sqlite3.connect(os.path.join(os.path.dirname(os.path.abspath(__file__)), BRIDGE_DB))
            rows = conn.execute("SELECT session_key, channel_id FROM session_mappings").fetchall()
            assert len(rows) >= 1, "No session mappings found"
            print(f"  Session mappings: {len(rows)}")
            for sk, cid in rows:
                print(f"    {sk} → {cid[:8]}...")
            print("  ✓ Session mapping PASSED")

            # --- Test 4: Cursor Persistence ---
            print("\n[5] Test: Cursor Persistence & Resume")
            cursor_row = conn.execute(
                "SELECT last_sequence_id FROM event_cursors WHERE agent_id = 'agent-builder-01'"
            ).fetchone()
            assert cursor_row is not None, "No cursor found"
            last_seq = cursor_row[0]
            print(f"  Last sequence_id before restart: {last_seq}")
            conn.close()

            # Kill bridge
            bridge.terminate()
            bridge.wait(timeout=5)
            procs.remove(bridge)
            print("  Bridge stopped")

            # Post a message while bridge is down
            r = await client.post(
                f"{MC_URL}/api/v1/channels/{ch_id}/messages",
                json={"content": "Message while bridge is down", "sender_id": "user_human", "sender_name": "Human User"},
            )
            assert r.status_code == 200
            print("  → Message posted while bridge was offline")

            # Restart bridge
            bridge = start_process([sys.executable, "bridge.py"])
            procs.append(bridge)
            await asyncio.sleep(2.0)  # Let it reconnect and process
            print("  Bridge restarted")

            # Check that the bridge processed the missed message
            reply = await wait_for_message(
                client, ch_id, "Agent response to: Message while bridge is down", timeout=5.0
            )
            print(f"  ← Caught up: {reply['content']}")
            print("  ✓ Cursor resume PASSED")

            # Verify cursor advanced
            conn = sqlite3.connect(os.path.join(os.path.dirname(os.path.abspath(__file__)), BRIDGE_DB))
            new_seq = conn.execute(
                "SELECT last_sequence_id FROM event_cursors WHERE agent_id = 'agent-builder-01'"
            ).fetchone()[0]
            assert new_seq > last_seq, f"Cursor did not advance: {new_seq} <= {last_seq}"
            print(f"  Cursor advanced: {last_seq} → {new_seq}")
            conn.close()

        print("\n" + "=" * 60)
        print("ALL TESTS PASSED ✅")
        print("=" * 60 + "\n")

    finally:
        for p in procs:
            try:
                p.terminate()
                p.wait(timeout=3)
            except Exception:
                p.kill()
        cleanup_dbs()


if __name__ == "__main__":
    asyncio.run(run_tests())
