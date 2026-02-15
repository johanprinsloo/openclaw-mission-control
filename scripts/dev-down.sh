#!/bin/bash
# Stop the Mission Control development environment.

set -e

echo "🛑 Stopping Mission Control Development Environment"
docker compose -f docker/docker-compose.dev.yml down

echo "✅ Development environment stopped"
