#!/bin/bash
# Reset the Mission Control local database (PostgreSQL 16 Native)

set -e

DB_NAME="mission_control"
PG_BIN="/opt/homebrew/opt/postgresql@16/bin"

echo "🗑️  Dropping database: $DB_NAME..."
$PG_BIN/dropdb --if-exists $DB_NAME

echo "✨ Creating database: $DB_NAME..."
$PG_BIN/createdb $DB_NAME

echo "🚀 Running migrations..."
cd packages/server
uv run alembic upgrade head

echo "✅ Database reset complete!"
echo "Next: uv run python -m app.scripts.create_local_admin --email your@email.com --password devpass"
