#!/bin/bash
set -e

# Start services
docker compose -f docker/docker-compose.yml up -d postgres redis

# Wait for Postgres
echo "Waiting for Postgres..."
sleep 5

# Run migrations
cd packages/server
# If no revisions exist, create one
if [ -z "$(ls -A alembic/versions)" ]; then
    echo "Creating initial migration..."
    uv run alembic revision --autogenerate -m "Initial schema"
fi
uv run alembic upgrade head

echo "Database initialized."
