#!/bin/bash
# Start the Mission Control development environment.

set -e

echo "🚀 Starting Mission Control Development Environment"

# Determine the compose command
if docker compose version > /dev/null 2>&1; then
    COMPOSE_CMD="docker compose"
elif docker-compose --version > /dev/null 2>&1; then
    COMPOSE_CMD="docker-compose"
else
    echo "❌ Error: Neither 'docker compose' nor 'docker-compose' was found."
    echo "   Please install Docker Compose: 'brew install docker-compose'"
    exit 1
fi

# Start PostgreSQL and Redis
echo "📦 Starting PostgreSQL and Redis with $COMPOSE_CMD..."
$COMPOSE_CMD -f docker/docker-compose.dev.yml up -d

# Wait for services to be healthy
echo "⏳ Waiting for services to be ready..."
sleep 3

# Check PostgreSQL
until docker exec mc-postgres pg_isready -U postgres > /dev/null 2>&1; do
    echo "  Waiting for PostgreSQL..."
    sleep 1
done
echo "✅ PostgreSQL ready"

# Check Redis
until docker exec mc-redis redis-cli ping > /dev/null 2>&1; do
    echo "  Waiting for Redis..."
    sleep 1
done
echo "✅ Redis ready"

echo ""
echo "🎉 Development environment is ready!"
echo ""
echo "Next steps:"
echo "  1. cd packages/server && uv run alembic upgrade head"
echo "  2. cd packages/server && uv run uvicorn app.main:app --reload"
echo "  3. cd frontend && npm run dev"
echo ""
