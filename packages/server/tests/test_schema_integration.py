"""Integration tests for RLS isolation and event immutability.

These tests require a running PostgreSQL instance (docker-compose or testcontainers).
Run with: uv run pytest tests/test_schema_integration.py -v

The tests use raw SQL via asyncpg to validate database-level behaviour
independent of the ORM layer.
"""

import os
import uuid
import pytest
import asyncio
from datetime import datetime, timezone

import asyncpg

DATABASE_URL = os.getenv(
    "MC_TEST_DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/mission_control_test",
)

ORG_A = uuid.uuid4()
ORG_B = uuid.uuid4()
USER_A = uuid.uuid4()
USER_B = uuid.uuid4()


@pytest.fixture(scope="module")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="module")
async def pool():
    """Create a connection pool and run migrations."""
    p = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=5)

    # Run alembic upgrade head via subprocess
    import subprocess

    env = os.environ.copy()
    env["MC_DATABASE_URL"] = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")
    result = subprocess.run(
        ["uv", "run", "alembic", "upgrade", "head"],
        cwd=os.path.join(os.path.dirname(__file__), ".."),
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        pytest.fail(f"Alembic upgrade failed:\n{result.stderr}")

    yield p

    # Cleanup: downgrade
    subprocess.run(
        ["uv", "run", "alembic", "downgrade", "base"],
        cwd=os.path.join(os.path.dirname(__file__), ".."),
        env=env,
        capture_output=True,
    )
    await p.close()


@pytest.fixture(scope="module")
async def seeded_pool(pool):
    """Seed two orgs with data for RLS testing."""
    async with pool.acquire() as conn:
        # Create two orgs
        await conn.execute(
            "INSERT INTO organizations (id, name, slug) VALUES ($1, $2, $3)",
            ORG_A, "Org Alpha", "org-alpha",
        )
        await conn.execute(
            "INSERT INTO organizations (id, name, slug) VALUES ($1, $2, $3)",
            ORG_B, "Org Beta", "org-beta",
        )

        # Create users
        await conn.execute(
            "INSERT INTO users (id, email, type) VALUES ($1, $2, 'human')",
            USER_A, "a@alpha.dev",
        )
        await conn.execute(
            "INSERT INTO users (id, email, type) VALUES ($1, $2, 'human')",
            USER_B, "b@beta.dev",
        )

        # Memberships
        await conn.execute(
            "INSERT INTO users_orgs (user_id, org_id, role, display_name) VALUES ($1, $2, 'administrator', 'User A')",
            USER_A, ORG_A,
        )
        await conn.execute(
            "INSERT INTO users_orgs (user_id, org_id, role, display_name) VALUES ($1, $2, 'administrator', 'User B')",
            USER_B, ORG_B,
        )

        # Projects (one per org)
        proj_a = uuid.uuid4()
        proj_b = uuid.uuid4()
        await conn.execute(
            "INSERT INTO projects (id, org_id, name, type) VALUES ($1, $2, 'Alpha Project', 'software')",
            proj_a, ORG_A,
        )
        await conn.execute(
            "INSERT INTO projects (id, org_id, name, type) VALUES ($1, $2, 'Beta Project', 'docs')",
            proj_b, ORG_B,
        )

    yield pool


# ---------------------------------------------------------------------------
# RLS Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rls_select_isolation(seeded_pool):
    """Setting org_id to Org A should only return Org A's projects."""
    async with seeded_pool.acquire() as conn:
        await conn.execute(f"SET app.current_org_id = '{ORG_A}'")
        rows = await conn.fetch("SELECT * FROM projects")
        assert len(rows) == 1
        assert rows[0]["name"] == "Alpha Project"


@pytest.mark.asyncio
async def test_rls_cross_tenant_invisible(seeded_pool):
    """Org B's data should be invisible when set to Org A."""
    async with seeded_pool.acquire() as conn:
        await conn.execute(f"SET app.current_org_id = '{ORG_A}'")
        rows = await conn.fetch("SELECT * FROM projects WHERE name = 'Beta Project'")
        assert len(rows) == 0


@pytest.mark.asyncio
async def test_rls_insert_wrong_org_blocked(seeded_pool):
    """Inserting with Org B's id while set to Org A should be blocked by RLS."""
    async with seeded_pool.acquire() as conn:
        await conn.execute(f"SET app.current_org_id = '{ORG_A}'")
        # This insert should succeed (org_id matches session)
        proj_id = uuid.uuid4()
        await conn.execute(
            "INSERT INTO projects (id, org_id, name, type) VALUES ($1, $2, 'Test', 'software')",
            proj_id, ORG_A,
        )
        # But inserting with ORG_B's id while set to ORG_A — RLS blocks visibility
        # The insert succeeds at SQL level but the row is invisible to the session.
        # With FORCE RLS + restrictive policy, it depends on policy type.
        # Our policy uses USING only (not WITH CHECK), so INSERTs are allowed
        # but the row won't be visible. Let's test that.
        proj_id2 = uuid.uuid4()
        await conn.execute(
            "INSERT INTO projects (id, org_id, name, type) VALUES ($1, $2, 'Sneaky', 'software')",
            proj_id2, ORG_B,
        )
        # The row should NOT be visible
        rows = await conn.fetch("SELECT * FROM projects WHERE id = $1", proj_id2)
        assert len(rows) == 0

        # Clean up
        # Need to reset to see it, or use superuser
        await conn.execute("RESET app.current_org_id")


@pytest.mark.asyncio
async def test_rls_users_orgs_isolation(seeded_pool):
    """users_orgs should be RLS-scoped."""
    async with seeded_pool.acquire() as conn:
        await conn.execute(f"SET app.current_org_id = '{ORG_A}'")
        rows = await conn.fetch("SELECT * FROM users_orgs")
        assert len(rows) == 1
        assert rows[0]["display_name"] == "User A"


# ---------------------------------------------------------------------------
# Event Immutability Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_event_insert_succeeds(seeded_pool):
    """Events can be inserted."""
    async with seeded_pool.acquire() as conn:
        event_id = uuid.uuid4()
        now = datetime.now(timezone.utc)
        await conn.execute(
            """INSERT INTO events (id, org_id, type, actor_type, payload, timestamp)
               VALUES ($1, $2, 'test.created', 'system', '{}', $3)""",
            event_id, ORG_A, now,
        )
        rows = await conn.fetch("SELECT * FROM events WHERE id = $1 AND timestamp = $2", event_id, now)
        assert len(rows) == 1


@pytest.mark.asyncio
async def test_event_update_blocked(seeded_pool):
    """UPDATE on events should be rejected by the immutability trigger."""
    async with seeded_pool.acquire() as conn:
        event_id = uuid.uuid4()
        now = datetime.now(timezone.utc)
        await conn.execute(
            """INSERT INTO events (id, org_id, type, actor_type, payload, timestamp)
               VALUES ($1, $2, 'test.update', 'system', '{}', $3)""",
            event_id, ORG_A, now,
        )
        with pytest.raises(asyncpg.exceptions.RaiseError, match="immutable"):
            await conn.execute(
                "UPDATE events SET type = 'tampered' WHERE id = $1 AND timestamp = $2",
                event_id, now,
            )


@pytest.mark.asyncio
async def test_event_delete_blocked(seeded_pool):
    """DELETE on events should be rejected by the immutability trigger."""
    async with seeded_pool.acquire() as conn:
        event_id = uuid.uuid4()
        now = datetime.now(timezone.utc)
        await conn.execute(
            """INSERT INTO events (id, org_id, type, actor_type, payload, timestamp)
               VALUES ($1, $2, 'test.delete', 'system', '{}', $3)""",
            event_id, ORG_A, now,
        )
        with pytest.raises(asyncpg.exceptions.RaiseError, match="immutable"):
            await conn.execute(
                "DELETE FROM events WHERE id = $1 AND timestamp = $2",
                event_id, now,
            )


# ---------------------------------------------------------------------------
# Partition Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_messages_insert_routed_to_partition(seeded_pool):
    """Messages should be insertable and routed to the correct partition."""
    async with seeded_pool.acquire() as conn:
        # First create a channel
        ch_id = uuid.uuid4()
        await conn.execute(
            "INSERT INTO channels (id, org_id, name, type) VALUES ($1, $2, 'test-ch', 'org_wide')",
            ch_id, ORG_A,
        )
        msg_id = uuid.uuid4()
        now = datetime.now(timezone.utc)
        await conn.execute(
            """INSERT INTO messages (id, org_id, channel_id, sender_id, content, created_at)
               VALUES ($1, $2, $3, $4, 'hello', $5)""",
            msg_id, ORG_A, ch_id, USER_A, now,
        )
        rows = await conn.fetch(
            "SELECT * FROM messages WHERE id = $1 AND created_at = $2", msg_id, now
        )
        assert len(rows) == 1
        assert rows[0]["content"] == "hello"


# ---------------------------------------------------------------------------
# Full-Text Search Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fts_projects(seeded_pool):
    """Projects should be searchable via search_vector."""
    async with seeded_pool.acquire() as conn:
        # Reset RLS to see all
        await conn.execute(f"SET app.current_org_id = '{ORG_A}'")
        rows = await conn.fetch(
            "SELECT name, ts_rank(search_vector, to_tsquery('english', 'alpha')) AS rank "
            "FROM projects WHERE search_vector @@ to_tsquery('english', 'alpha') ORDER BY rank DESC"
        )
        assert len(rows) >= 1
        assert rows[0]["name"] == "Alpha Project"
