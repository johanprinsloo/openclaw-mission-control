# Mission Control Server

## Setup

1. Install `uv`: `pip install uv`
2. Sync dependencies: `uv sync`
3. Start the database: `docker-compose -f docker/docker-compose.yml up -d`
4. Run migrations: `cd packages/server && uv run alembic upgrade head`
5. Start the server: `cd packages/server && uv run uvicorn app.main:app --reload`

## API Documentation

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
