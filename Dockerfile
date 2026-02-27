FROM node:20-alpine AS frontend-build

WORKDIR /frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim AS base

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

COPY pyproject.toml uv.lock ./
COPY packages/shared/ packages/shared/
COPY packages/server/ packages/server/
COPY --from=frontend-build /frontend/dist /app/frontend/dist

RUN uv sync --frozen --no-dev --package mc-server

COPY packages/server/alembic.ini packages/server/alembic.ini

EXPOSE 8000

CMD ["uv", "run", "--no-sync", "--package", "mc-server", \
     "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
