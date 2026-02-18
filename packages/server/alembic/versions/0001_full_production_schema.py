"""Full production schema with RLS, partitioning, FTS, and event immutability.

Revision ID: 0001_full_schema
Revises:
Create Date: 2026-02-15 14:00:00.000000
"""

from typing import Sequence, Union
from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0001_full_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Tables that get RLS policies (all tenant-scoped tables).
RLS_TABLES = [
    "projects",
    "tasks",
    "task_project_assignments",
    "project_user_assignments",
    "task_user_assignments",
    "task_dependencies",
    "task_evidence",
    "users_orgs",
    "channels",
    "messages",
    "events",
    "sub_agents",
    "subscriptions",
]


def _create_partitions(table: str, ts_col: str) -> None:
    """Create partitions for the current month, next month, and a default."""
    now = datetime.now(timezone.utc)
    for offset in range(2):
        year = now.year + (now.month + offset - 1) // 12
        month = (now.month + offset - 1) % 12 + 1
        next_year = year + (month) // 12
        next_month = (month) % 12 + 1
        part_name = f"{table}_y{year}m{month:02d}"
        start = f"{year}-{month:02d}-01"
        end = f"{next_year}-{next_month:02d}-01"
        op.execute(
            f"CREATE TABLE {part_name} PARTITION OF {table} "
            f"FOR VALUES FROM ('{start}') TO ('{end}')"
        )
    op.execute(f"CREATE TABLE {table}_default PARTITION OF {table} DEFAULT")


# ---------------------------------------------------------------------------
# UPGRADE
# ---------------------------------------------------------------------------


def upgrade() -> None:
    # -----------------------------------------------------------------------
    # 1. Core tables (non-partitioned)
    # -----------------------------------------------------------------------

    # organizations (NOT RLS-scoped)
    op.create_table(
        "organizations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("slug", sa.Text(), nullable=False, unique=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="active"),
        sa.Column("settings", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("deletion_scheduled_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("idx_organizations_slug", "organizations", ["slug"], unique=True)

    # users (NOT RLS-scoped)
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.Text(), nullable=True, unique=True),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("identifier", sa.Text(), nullable=True),
        sa.Column("oidc_provider", sa.Text(), nullable=True),
        sa.Column("oidc_subject", sa.Text(), nullable=True),
        sa.Column("password_hash", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("idx_users_email", "users", ["email"], unique=True)

    # users_orgs
    op.create_table(
        "users_orgs",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), primary_key=True),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("api_key_hash", sa.Text(), nullable=True),
        sa.Column("api_key_previous_hash", sa.Text(), nullable=True),
        sa.Column("api_key_previous_expires_at", sa.Text(), nullable=True),
    )

    # projects
    op.create_table(
        "projects",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("stage", sa.Text(), nullable=False, server_default="definition"),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("links", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        # FTS generated column added via raw SQL below
    )
    op.create_index("idx_projects_org", "projects", ["org_id"])
    op.create_index("idx_projects_stage", "projects", ["org_id", "stage"])

    # tasks
    op.create_table(
        "tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("priority", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="backlog"),
        sa.Column("required_evidence_types", postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        # FTS generated column added via raw SQL below
    )
    op.create_index("idx_tasks_org", "tasks", ["org_id"])
    op.create_index("idx_tasks_status", "tasks", ["org_id", "status"])
    op.create_index("idx_tasks_priority", "tasks", ["org_id", "priority"])

    # task_project_assignments
    op.create_table(
        "task_project_assignments",
        sa.Column("task_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tasks.id"), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id"), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
    )
    op.create_index("idx_task_projects_project", "task_project_assignments", ["project_id"])

    # project_user_assignments
    op.create_table(
        "project_user_assignments",
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id"), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("idx_project_users_user", "project_user_assignments", ["user_id"])

    # task_user_assignments
    op.create_table(
        "task_user_assignments",
        sa.Column("task_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tasks.id"), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
    )
    op.create_index("idx_task_users_user", "task_user_assignments", ["user_id"])

    # task_dependencies
    op.create_table(
        "task_dependencies",
        sa.Column("task_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tasks.id"), primary_key=True),
        sa.Column("blocked_by_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tasks.id"), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.CheckConstraint("task_id != blocked_by_id", name="no_self_dependency"),
    )

    # task_evidence
    op.create_table(
        "task_evidence",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tasks.id"), nullable=False),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("submitted_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
    )

    # channels
    op.create_table(
        "channels",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("idx_channels_org", "channels", ["org_id"])
    op.create_index("idx_channels_project", "channels", ["org_id", "project_id"])

    # sub_agents
    op.create_table(
        "sub_agents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tasks.id"), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("instructions", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="active"),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("api_key_hash", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("terminated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("termination_reason", sa.Text(), nullable=True),
    )
    op.create_index("idx_sub_agents_org", "sub_agents", ["org_id"])
    op.create_index("idx_sub_agents_status", "sub_agents", ["org_id", "status"], postgresql_where=sa.text("status = 'active'"))

    # subscriptions
    op.create_table(
        "subscriptions",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), primary_key=True),
        sa.Column("topic_type", sa.Text(), nullable=False, primary_key=True),
        sa.Column("topic_id", postgresql.UUID(as_uuid=True), nullable=False, primary_key=True),
    )

    # -----------------------------------------------------------------------
    # 2. Partitioned tables
    # -----------------------------------------------------------------------

    # messages (partitioned by RANGE on created_at)
    op.create_table(
        "messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("channel_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sender_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("mentions", postgresql.ARRAY(postgresql.UUID(as_uuid=True)), server_default="{}", nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id", "created_at"),
        postgresql_partition_by="RANGE (created_at)",
    )
    op.create_index("idx_messages_channel", "messages", ["channel_id", sa.text("created_at DESC")])

    # events (partitioned by RANGE on timestamp)
    op.create_table(
        "events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sequence_id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("actor_type", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id", "timestamp"),
        postgresql_partition_by="RANGE (timestamp)",
    )

    # Create sequence for events.sequence_id
    op.execute("CREATE SEQUENCE IF NOT EXISTS events_sequence_id_seq")
    op.execute("ALTER TABLE events ALTER COLUMN sequence_id SET DEFAULT nextval('events_sequence_id_seq')")

    # BRIN indexes for partitioned tables
    op.execute("CREATE INDEX idx_messages_time ON messages USING BRIN (created_at)")
    op.execute("CREATE INDEX idx_events_time ON events USING BRIN (timestamp)")

    # Create partitions
    _create_partitions("messages", "created_at")
    _create_partitions("events", "timestamp")

    # -----------------------------------------------------------------------
    # 3. Full-Text Search (generated tsvector columns + GIN indexes)
    # -----------------------------------------------------------------------

    op.execute("""
        ALTER TABLE projects ADD COLUMN search_vector tsvector
        GENERATED ALWAYS AS (
            setweight(to_tsvector('english', coalesce(name, '')), 'A') ||
            setweight(to_tsvector('english', coalesce(description, '')), 'B')
        ) STORED
    """)
    op.execute("CREATE INDEX idx_projects_fts ON projects USING GIN (search_vector)")

    op.execute("""
        ALTER TABLE tasks ADD COLUMN search_vector tsvector
        GENERATED ALWAYS AS (
            setweight(to_tsvector('english', coalesce(title, '')), 'A') ||
            setweight(to_tsvector('english', coalesce(description, '')), 'B')
        ) STORED
    """)
    op.execute("CREATE INDEX idx_tasks_fts ON tasks USING GIN (search_vector)")

    # Messages FTS — added on the partitioned parent; PG propagates to partitions
    op.execute("""
        ALTER TABLE messages ADD COLUMN search_vector tsvector
        GENERATED ALWAYS AS (
            setweight(to_tsvector('english', coalesce(content, '')), 'B')
        ) STORED
    """)
    op.execute("CREATE INDEX idx_messages_fts ON messages USING GIN (search_vector)")

    # -----------------------------------------------------------------------
    # 4. Event immutability trigger
    # -----------------------------------------------------------------------

    op.execute("""
        CREATE OR REPLACE FUNCTION prevent_event_mutation()
        RETURNS TRIGGER AS $$
        BEGIN
            RAISE EXCEPTION 'Events are immutable. UPDATE and DELETE are not permitted.';
        END;
        $$ LANGUAGE plpgsql
    """)
    op.execute("""
        CREATE TRIGGER events_immutable
        BEFORE UPDATE OR DELETE ON events
        FOR EACH ROW EXECUTE FUNCTION prevent_event_mutation()
    """)

    # -----------------------------------------------------------------------
    # 5. Row Level Security (RLS) policies
    # -----------------------------------------------------------------------

    for table in RLS_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"""
            CREATE POLICY org_isolation ON {table}
            USING (org_id = current_setting('app.current_org_id')::uuid)
        """)
        # Allow the table owner (migration runner / superuser) to bypass RLS
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")


# ---------------------------------------------------------------------------
# DOWNGRADE
# ---------------------------------------------------------------------------


def downgrade() -> None:
    # Drop RLS policies
    for table in reversed(RLS_TABLES):
        op.execute(f"DROP POLICY IF EXISTS org_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")

    # Drop event immutability
    op.execute("DROP TRIGGER IF EXISTS events_immutable ON events")
    op.execute("DROP FUNCTION IF EXISTS prevent_event_mutation()")

    # Drop FTS indexes and columns
    op.execute("DROP INDEX IF EXISTS idx_messages_fts")
    op.execute("DROP INDEX IF EXISTS idx_tasks_fts")
    op.execute("DROP INDEX IF EXISTS idx_projects_fts")
    # Generated columns can't be dropped easily; dropping tables handles it.

    # Drop partitioned tables (cascade drops partitions)
    op.drop_table("events")
    op.execute("DROP SEQUENCE IF EXISTS events_sequence_id_seq")
    op.drop_table("messages")

    # Drop regular tables in reverse dependency order
    op.drop_table("subscriptions")
    op.drop_table("sub_agents")
    op.drop_table("task_evidence")
    op.drop_table("task_dependencies")
    op.drop_table("task_user_assignments")
    op.drop_table("project_user_assignments")
    op.drop_table("task_project_assignments")
    op.drop_table("channels")
    op.drop_table("tasks")
    op.drop_table("projects")
    op.drop_table("users_orgs")
    op.drop_table("users")
    op.drop_table("organizations")
