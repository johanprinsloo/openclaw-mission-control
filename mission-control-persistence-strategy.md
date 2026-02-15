# Mission Control Data Persistence Strategy

This document defines the storage architecture for Mission Control. It covers tenant isolation, schema design, indexing, partitioning, and archival.

## Database Selection

PostgreSQL is the sole database backend for both deployment modes (self-hosted single-tenant and hosted multi-tenant). This choice is driven by:

- Strong relational model fit — the data model has many-to-many relationships (tasks ↔ projects, users ↔ orgs) that require joins.
- Native Row Level Security (RLS) for tenant isolation.
- Built-in full-text search (sufficient for v1; pluggable search backends can replace it later).
- Table partitioning for high-volume append-only tables (events, messages).
- Mature, low-cost AWS hosting options (RDS, Aurora Serverless, or self-managed on Lightsail).
- Broad community support for an open-source project.

## Tenant Isolation

### Approach: Row-Level Security (RLS)

Every tenant-scoped table includes an `org_id` column. PostgreSQL RLS policies enforce that queries can only access rows belonging to the authenticated org. This provides database-level isolation as a safety net behind the application-layer org scoping already built into the API.

#### How It Works

1. The application sets a session variable on each database connection:
   ```sql
   SET app.current_org_id = 'org_abc123';
   ```

2. RLS policies reference this variable:
   ```sql
   CREATE POLICY org_isolation ON projects
     USING (org_id = current_setting('app.current_org_id'));
   ```

3. Even if application code omits an `org_id` filter, the database rejects cross-tenant access.

#### Policy Scope

RLS policies are applied to all tenant-scoped tables: `projects`, `tasks`, `task_project_assignments`, `task_dependencies`, `task_evidence`, `users_orgs`, `channels`, `messages`, `events`, `sub_agents`, and `subscriptions`.

The `users` table is **not** RLS-scoped — user identities span orgs. Org membership is controlled via the `users_orgs` join table, which is RLS-scoped.

The `organizations` table is **not** RLS-scoped — it is accessed at the platform level (e.g., `GET /api/v1/orgs`).

#### Escalation Path

If a hosted customer later requires stronger isolation (regulatory, data residency), a single tenant can be migrated to a dedicated database instance. The org-scoped API design supports this without application changes — only the connection routing layer needs to change.

## Schema Overview

The schema below covers the core tables. Indexes and partitioning details follow.

### Core Tables

```
organizations
  id              UUID PRIMARY KEY
  name            TEXT NOT NULL
  slug            TEXT UNIQUE NOT NULL
  status          TEXT NOT NULL DEFAULT 'active'    -- active | suspended | pending_deletion
  settings        JSONB NOT NULL DEFAULT '{}'
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
  deletion_scheduled_at  TIMESTAMPTZ              -- set when deletion begins

users
  id              UUID PRIMARY KEY
  email           TEXT UNIQUE                       -- NULL for agents
  type            TEXT NOT NULL                     -- human | agent
  identifier      TEXT                              -- agent identifier (unique per org via users_orgs)
  oidc_provider   TEXT                              -- github | google
  oidc_subject    TEXT                              -- provider-issued subject ID
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()

users_orgs
  user_id         UUID REFERENCES users(id)
  org_id          UUID REFERENCES organizations(id)
  role            TEXT NOT NULL                     -- administrator | contributor
  display_name    TEXT NOT NULL
  api_key_hash    TEXT                              -- bcrypt hash; only for agents
  PRIMARY KEY (user_id, org_id)

projects
  id              UUID PRIMARY KEY
  org_id          UUID NOT NULL REFERENCES organizations(id)
  name            TEXT NOT NULL
  type            TEXT NOT NULL                     -- software | docs | launch
  description     TEXT                              -- markdown
  stage           TEXT NOT NULL DEFAULT 'definition'
  owner_id        UUID REFERENCES users(id)
  links           JSONB NOT NULL DEFAULT '{}'
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()

tasks
  id              UUID PRIMARY KEY
  org_id          UUID NOT NULL REFERENCES organizations(id)
  title           TEXT NOT NULL
  type            TEXT NOT NULL                     -- bug | feature | chore
  priority        TEXT NOT NULL                     -- low | medium | high | critical
  status          TEXT NOT NULL DEFAULT 'backlog'   -- backlog | in-progress | in-review | complete
  required_evidence_types TEXT[]                    -- pr_link | test_results | doc_url
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
  completed_at    TIMESTAMPTZ                       -- set on transition to complete
  archived_at     TIMESTAMPTZ                       -- set when archived

task_project_assignments
  task_id         UUID REFERENCES tasks(id)
  project_id      UUID REFERENCES projects(id)
  org_id          UUID NOT NULL REFERENCES organizations(id)
  PRIMARY KEY (task_id, project_id)

task_user_assignments
  task_id         UUID REFERENCES tasks(id)
  user_id         UUID REFERENCES users(id)
  org_id          UUID NOT NULL REFERENCES organizations(id)
  PRIMARY KEY (task_id, user_id)

task_dependencies
  task_id         UUID REFERENCES tasks(id)
  blocked_by_id   UUID REFERENCES tasks(id)
  org_id          UUID NOT NULL REFERENCES organizations(id)
  PRIMARY KEY (task_id, blocked_by_id)
  CHECK (task_id != blocked_by_id)

task_evidence
  id              UUID PRIMARY KEY
  task_id         UUID NOT NULL REFERENCES tasks(id)
  org_id          UUID NOT NULL REFERENCES organizations(id)
  type            TEXT NOT NULL                     -- pr_link | test_results | doc_url
  url             TEXT NOT NULL
  submitted_at    TIMESTAMPTZ NOT NULL DEFAULT now()
  submitted_by    UUID NOT NULL REFERENCES users(id)

channels
  id              UUID PRIMARY KEY
  org_id          UUID NOT NULL REFERENCES organizations(id)
  project_id      UUID REFERENCES projects(id)     -- NULL for org-wide channels
  name            TEXT NOT NULL
  type            TEXT NOT NULL                     -- org_wide | project
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()

sub_agents
  id              UUID PRIMARY KEY
  org_id          UUID NOT NULL REFERENCES organizations(id)
  task_id         UUID NOT NULL REFERENCES tasks(id)
  model           TEXT NOT NULL
  instructions    TEXT NOT NULL
  status          TEXT NOT NULL DEFAULT 'active'    -- active | terminated
  created_by      UUID NOT NULL REFERENCES users(id)
  api_key_hash    TEXT                              -- ephemeral key, bcrypt hash
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
  expires_at      TIMESTAMPTZ NOT NULL
  terminated_at   TIMESTAMPTZ
  termination_reason TEXT

subscriptions
  user_id         UUID NOT NULL REFERENCES users(id)
  org_id          UUID NOT NULL REFERENCES organizations(id)
  topic_type      TEXT NOT NULL                     -- project | task | channel
  topic_id        UUID NOT NULL
  PRIMARY KEY (user_id, org_id, topic_type, topic_id)
```

### Partitioned Tables (High Volume)

These tables use PostgreSQL declarative partitioning by month on `created_at` (or `timestamp`). Partitioning enables efficient time-range queries, fast bulk deletes for retention, and keeps index sizes manageable.

```
messages (PARTITIONED BY RANGE (created_at))
  id              UUID NOT NULL
  org_id          UUID NOT NULL REFERENCES organizations(id)
  channel_id      UUID NOT NULL REFERENCES channels(id)
  sender_id       UUID NOT NULL REFERENCES users(id)
  content         TEXT NOT NULL
  mentions        UUID[]                            -- user IDs mentioned
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
  PRIMARY KEY (id, created_at)

events (PARTITIONED BY RANGE (timestamp))
  id              UUID NOT NULL
  org_id          UUID NOT NULL REFERENCES organizations(id)
  type            TEXT NOT NULL                     -- e.g., task.transitioned, project.created
  actor_id        UUID REFERENCES users(id)
  actor_type      TEXT NOT NULL                     -- human | agent | system
  payload         JSONB NOT NULL
  timestamp       TIMESTAMPTZ NOT NULL DEFAULT now()
  PRIMARY KEY (id, timestamp)
```

New partitions are created automatically via a scheduled job (or pg_partman) ahead of the upcoming month. Old partitions are detached and archived according to the retention policy (see Archival below).

## Indexing Strategy

### Standard B-tree Indexes

```sql
-- Org-scoped lookups (critical path for RLS performance)
CREATE INDEX idx_projects_org       ON projects (org_id);
CREATE INDEX idx_tasks_org          ON tasks (org_id);
CREATE INDEX idx_channels_org       ON channels (org_id);
CREATE INDEX idx_sub_agents_org     ON sub_agents (org_id);

-- Frequent query patterns
CREATE INDEX idx_tasks_status       ON tasks (org_id, status);
CREATE INDEX idx_tasks_priority     ON tasks (org_id, priority);
CREATE INDEX idx_projects_stage     ON projects (org_id, stage);
CREATE INDEX idx_channels_project   ON channels (org_id, project_id);
CREATE INDEX idx_sub_agents_status  ON sub_agents (org_id, status) WHERE status = 'active';

-- Join table lookups
CREATE INDEX idx_task_projects_project  ON task_project_assignments (project_id);
CREATE INDEX idx_task_users_user        ON task_user_assignments (user_id);
```

### BRIN Indexes (Append-Only Tables)

BRIN indexes are much smaller than B-tree for timestamp-ordered data and perform well for range scans on partitioned tables.

```sql
CREATE INDEX idx_messages_time  ON messages USING BRIN (created_at);
CREATE INDEX idx_events_time    ON events USING BRIN (timestamp);

-- Per-channel message lookups still need B-tree
CREATE INDEX idx_messages_channel ON messages (channel_id, created_at DESC);
```

### Full-Text Search Indexes

GIN indexes on tsvector columns power the unified search endpoint.

```sql
-- Projects: search name + description
ALTER TABLE projects ADD COLUMN search_vector tsvector
  GENERATED ALWAYS AS (
    setweight(to_tsvector('english', coalesce(name, '')), 'A') ||
    setweight(to_tsvector('english', coalesce(description, '')), 'B')
  ) STORED;
CREATE INDEX idx_projects_fts ON projects USING GIN (search_vector);

-- Tasks: search title
ALTER TABLE tasks ADD COLUMN search_vector tsvector
  GENERATED ALWAYS AS (
    to_tsvector('english', coalesce(title, ''))
  ) STORED;
CREATE INDEX idx_tasks_fts ON tasks USING GIN (search_vector);

-- Messages: search content
ALTER TABLE messages ADD COLUMN search_vector tsvector
  GENERATED ALWAYS AS (
    to_tsvector('english', coalesce(content, ''))
  ) STORED;
CREATE INDEX idx_messages_fts ON messages USING GIN (search_vector);
```

The search API queries these indexes with `ts_rank` for relevance scoring and `ts_headline` for snippet generation with `<mark>` highlighting.

#### Scaling Note

PostgreSQL full-text search is sufficient for single-tenant and small multi-tenant deployments. If search latency or volume becomes a bottleneck in the hosted offering, the search layer can be replaced with a dedicated engine (e.g., Typesense, Meilisearch) without changing the API contract. The `search_vector` columns and GIN indexes would be dropped, and the search endpoint would query the external engine instead.

## Event Log Immutability

The events table is append-only. Immutability is enforced at the database level:

```sql
CREATE OR REPLACE FUNCTION prevent_event_mutation()
RETURNS TRIGGER AS $$
BEGIN
  RAISE EXCEPTION 'Events are immutable. UPDATE and DELETE are not permitted.';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER events_immutable
  BEFORE UPDATE OR DELETE ON events
  FOR EACH ROW EXECUTE FUNCTION prevent_event_mutation();
```

This ensures the audit trail cannot be tampered with, even by application-level bugs.

## Archival and Retention

### Completed Tasks

Completed tasks remain in the `tasks` table with `status = 'complete'` and a `completed_at` timestamp. They are queryable and searchable indefinitely. After a configurable retention period (default: 12 months after completion), tasks are marked with an `archived_at` timestamp. Archived tasks are excluded from default list queries (the API filters them out unless `?include_archived=true` is passed) but remain in the database and are included in data exports.

### End-of-Life Projects

Projects transitioned to `end-of-life` follow the same pattern: they remain in the database with their full history but are excluded from default Project Board views. Their associated tasks, channels, and events are retained.

### Chat Messages

Messages follow a time-based retention policy:

- **Hot tier (default: 12 months):** Messages remain in PostgreSQL, fully searchable.
- **Cold tier:** Partitions older than the hot retention window are detached from the partitioned table and exported to object storage (S3) as compressed JSON. They remain accessible via the data export API but are no longer searchable or returned in channel history queries.

Partition detachment is a metadata operation — no row-by-row deletion is needed.

### Event Log

Events follow the same partition-based retention as messages, with a longer default window (default: 24 months hot). Older partitions are archived to S3.

### Org Deletion

When an org enters `pending_deletion` status:

1. A grace period begins (configurable, default: 30 days).
2. During the grace period, the org is suspended (read-only). Admins can cancel the deletion or trigger a data export.
3. After the grace period, all org data is permanently deleted:
   - All rows with the org's `org_id` are removed from every tenant-scoped table.
   - Archived partitions in S3 for the org are deleted.
   - Users who belong only to this org are deactivated. Users in other orgs are unaffected.

## Connection Pooling

PostgreSQL connections are managed via an application-level connection pool (e.g., PgBouncer or the framework's built-in pooler). Each request acquires a connection, sets the `app.current_org_id` session variable for RLS, executes queries, and returns the connection to the pool. Connection pool size is configured based on deployment mode:

- **Self-hosted:** Small pool (5–20 connections), matching expected concurrency.
- **Hosted:** Larger pool scaled to tenant count and traffic, with PgBouncer in transaction-mode pooling to maximize connection reuse.

## Backup Strategy

### Hosted Offering

Automated daily snapshots via RDS/Aurora automated backups with point-in-time recovery (PITR) enabled. Retention: 14 days minimum.

### Self-Hosted

Admins configure backup location and schedule via org settings (as defined in the product doc). Recommended approach: `pg_dump` to a user-specified S3 bucket or local path on a cron schedule. Mission Control provides a built-in backup command that wraps `pg_dump` with org-scoped filtering for single-tenant deployments.

## Migration Strategy

Schema migrations are managed via a versioned migration tool (e.g., golang-migrate, Flyway, or framework-native migrations). Migrations are:

- Stored in version control alongside application code.
- Applied automatically on deployment (CI/CD pipeline runs migrations before starting the new application version).
- Backward-compatible where possible — additive changes (new columns, new tables) are preferred over destructive changes.
- Tested against a staging database before production deployment.

For the hosted multi-tenant deployment, migrations run once against the shared database. RLS policies ensure they apply uniformly across all tenants.
