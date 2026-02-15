#!/usr/bin/env python3
"""Seed a development database with a test organization, users, projects, and tasks.

Usage:
    uv run python scripts/seed_dev_data.py

Requires MC_DATABASE_URL (or defaults to localhost).
"""

import asyncio
import uuid
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/mission_control"

# Deterministic UUIDs for reproducibility
ORG_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
HUMAN_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000010")
AGENT_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000011")
PROJECT_IDS = [uuid.UUID(f"00000000-0000-0000-0000-0000000001{i:02d}") for i in range(3)]
TASK_IDS = [uuid.UUID(f"00000000-0000-0000-0000-0000000002{i:02d}") for i in range(10)]
CHANNEL_IDS = [uuid.UUID(f"00000000-0000-0000-0000-0000000003{i:02d}") for i in range(4)]


async def seed():
    engine = create_async_engine(DATABASE_URL)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        # Disable RLS for seeding (superuser bypasses, but just in case)
        await session.execute(text(f"SET app.current_org_id = '{ORG_ID}'"))

        # Organization
        await session.execute(text("""
            INSERT INTO organizations (id, name, slug, status, settings)
            VALUES (:id, :name, :slug, 'active', '{}')
            ON CONFLICT (id) DO NOTHING
        """), {"id": ORG_ID, "name": "Acme Robotics", "slug": "acme-robotics"})

        # Users
        await session.execute(text("""
            INSERT INTO users (id, email, type) VALUES (:id, :email, 'human')
            ON CONFLICT (id) DO NOTHING
        """), {"id": HUMAN_USER_ID, "email": "alice@acme.dev"})

        await session.execute(text("""
            INSERT INTO users (id, type, identifier) VALUES (:id, 'agent', 'build-bot')
            ON CONFLICT (id) DO NOTHING
        """), {"id": AGENT_USER_ID})

        # Org memberships
        for uid, role, name in [
            (HUMAN_USER_ID, "administrator", "Alice"),
            (AGENT_USER_ID, "contributor", "Build Bot"),
        ]:
            await session.execute(text("""
                INSERT INTO users_orgs (user_id, org_id, role, display_name)
                VALUES (:uid, :oid, :role, :name)
                ON CONFLICT DO NOTHING
            """), {"uid": uid, "oid": ORG_ID, "role": role, "name": name})

        # Projects
        projects = [
            ("API Server", "software", "definition"),
            ("Documentation Site", "docs", "development"),
            ("Product Launch", "launch", "definition"),
        ]
        for pid, (name, ptype, stage) in zip(PROJECT_IDS, projects):
            await session.execute(text("""
                INSERT INTO projects (id, org_id, name, type, stage, owner_id, links)
                VALUES (:id, :oid, :name, :type, :stage, :owner, '{}')
                ON CONFLICT (id) DO NOTHING
            """), {"id": pid, "oid": ORG_ID, "name": name, "type": ptype, "stage": stage, "owner": HUMAN_USER_ID})

        # Channels (1 org-wide + 1 per project)
        await session.execute(text("""
            INSERT INTO channels (id, org_id, name, type)
            VALUES (:id, :oid, 'general', 'org_wide')
            ON CONFLICT (id) DO NOTHING
        """), {"id": CHANNEL_IDS[0], "oid": ORG_ID})

        for i, pid in enumerate(PROJECT_IDS):
            await session.execute(text("""
                INSERT INTO channels (id, org_id, project_id, name, type)
                VALUES (:id, :oid, :pid, :name, 'project')
                ON CONFLICT (id) DO NOTHING
            """), {"id": CHANNEL_IDS[i + 1], "oid": ORG_ID, "pid": pid, "name": f"proj-{i}"})

        # Tasks
        task_specs = [
            ("Set up CI pipeline", "chore", "high", "backlog"),
            ("Implement auth middleware", "feature", "critical", "in-progress"),
            ("Fix login redirect bug", "bug", "high", "in-progress"),
            ("Add health check endpoint", "chore", "medium", "complete"),
            ("Design API schema", "feature", "high", "complete"),
            ("Write contribution guide", "chore", "low", "backlog"),
            ("Add rate limiting", "feature", "medium", "backlog"),
            ("Set up staging environment", "chore", "high", "in-review"),
            ("Implement WebSocket chat", "feature", "critical", "in-progress"),
            ("Add search endpoint", "feature", "medium", "backlog"),
        ]
        for tid, (title, ttype, priority, status) in zip(TASK_IDS, task_specs):
            await session.execute(text("""
                INSERT INTO tasks (id, org_id, title, type, priority, status)
                VALUES (:id, :oid, :title, :type, :priority, :status)
                ON CONFLICT (id) DO NOTHING
            """), {"id": tid, "oid": ORG_ID, "title": title, "type": ttype, "priority": priority, "status": status})

        # Assign first 5 tasks to project 0, next 5 to project 1
        for i, tid in enumerate(TASK_IDS):
            pid = PROJECT_IDS[0] if i < 5 else PROJECT_IDS[1]
            await session.execute(text("""
                INSERT INTO task_project_assignments (task_id, project_id, org_id)
                VALUES (:tid, :pid, :oid)
                ON CONFLICT DO NOTHING
            """), {"tid": tid, "pid": pid, "oid": ORG_ID})

        await session.commit()

    await engine.dispose()
    print(f"✅ Seeded org '{ORG_ID}' with 2 users, 3 projects, 4 channels, 10 tasks.")


if __name__ == "__main__":
    asyncio.run(seed())
