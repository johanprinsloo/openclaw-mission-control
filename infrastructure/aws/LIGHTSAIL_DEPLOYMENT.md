# Mission Control: AWS Lightsail Deployment Guide

This guide covers deploying Mission Control to AWS Lightsail via GitHub Actions CI/CD.

## Table of Contents
1. [AWS Lightsail Setup](#aws-lightsail-setup)
2. [GitHub Repository Configuration](#github-repository-configuration)
3. [CI/CD Workflows](#cicd-workflows)
4. [Database Setup](#database-setup)
5. [First Deployment](#first-deployment)
6. [Environment Variables & Secrets Reference](#environment-variables--secrets-reference)
7. [Troubleshooting](#troubleshooting)
8. [Cost Summary](#cost-summary)

---

## AWS Lightsail Setup

### Step 1: Create AWS Account & Access Keys

1. **Sign up for AWS** (if not already done):
   - Go to https://aws.amazon.com
   - Create a new account or sign in

2. **Create an IAM User** (recommended over using root account):
   - Navigate to **IAM > Users > Add User**
   - User name: `mission-control-deployer`
   - Access type: **Programmatic access** (for CI/CD)
   - Permissions: Attach policies directly:
     - `AmazonLightsailFullAccess`
   - **Save the Access Key ID and Secret Access Key** — you'll need these for GitHub secrets

### Step 2: Create Lightsail Container Service

1. **Navigate to Lightsail**:
   - Go to https://lightsail.aws.amazon.com
   - Select your region (recommend `us-west-2`)

2. **Create Container Service**:
   - Click **"Containers"** tab > **"Create container service"**
   - **Service name**: `mission-control-prod` (must match the `LIGHTSAIL_SERVICE_NAME` GitHub variable)
   - **Power**: **"Nano"** ($7/month) for dev, or **"Micro"** ($12/month) for production
   - **Scale**: 1 for dev, 2 for production

3. **Configure Container**:
   - **Container name**: `app`
   - **Image**: Leave blank (CI/CD pushes the image)
   - **Ports**: `8000` (HTTP)

4. **Public Endpoint**:
   - Enable public endpoint
   - **Health check path**: `/health`
   - Create the service

5. **Note the Service URL** (e.g., `https://mission-control-prod.abc123xyz.us-west-2.cs.amazonlightsail.com`)

> **Note**: The deploy workflow will also auto-create the service if it doesn't exist yet (see `Ensure Lightsail Service exists` step in `deploy.yml`).

### Step 3: Create Lightsail Database

1. In Lightsail, click **"Databases"** > **"Create database"**
2. **Configuration**:
   - **Database engine**: PostgreSQL 16
   - **Plan**: Micro ($15/month for dev)
   - **Master username**: `postgres`
   - **Master password**: Generate a strong password and **save it**
3. Wait for status **"Available"**
4. Note the **Endpoint** and **Port** (usually `5432`)

---

## GitHub Repository Configuration

### Step 1: Add GitHub Secrets (Sensitive Data)

Navigate to **Settings > Secrets and variables > Actions > Secrets tab**:

| Secret | Description | Example |
|--------|-------------|---------|
| `AWS_ACCESS_KEY_ID` | IAM user access key | `AKIAIOSFODNN7EXAMPLE` |
| `AWS_SECRET_ACCESS_KEY` | IAM user secret key | `wJalrXUtnFEMI/K7MDENG/...` |
| `DATABASE_URL` | Full asyncpg connection string | `postgresql+asyncpg://postgres:PASS@host:5432/mission_control` |
| `SECRET_KEY` | App secret for JWT/crypto — generate with `openssl rand -base64 32` | `random-base64-string` |

### Step 2: Add GitHub Variables (Non-Sensitive Config)

Navigate to **Settings > Secrets and variables > Actions > Variables tab**:

| Variable | Description | Example |
|----------|-------------|---------|
| `AWS_REGION` | AWS region | `us-west-2` |
| `LIGHTSAIL_SERVICE_NAME` | Container service name | `mission-control-prod` |
| `CORS_ORIGINS` | Comma-separated allowed origins | `https://app.example.com,http://localhost:5173` |

> **Important**: `CORS_ORIGINS` is a plain comma-separated string, **not** a JSON array.
> Single values work fine too: `https://app.example.com`

### Why Variables vs Secrets?

| Type | Use For | Editable? | Visible? |
|------|---------|-----------|----------|
| **Secrets** | Passwords, API keys, tokens | Must recreate | Masked in logs |
| **Variables** | Config, regions, service names | Edit anytime | Visible in UI |

### Step 3: Optional Secrets

| Secret | Description |
|--------|-------------|
| `SIGNAL_API_KEY` | Signal Gateway API key |
| `SENTRY_DSN` | Sentry error tracking DSN |

### Step 4: Enable GitHub Actions

- Go to **Settings > Actions > General**
- Ensure **"Allow all actions and reusable workflows"** is selected

---

## CI/CD Workflows

Three workflow files drive the pipeline. All are in `.github/workflows/` and are the source of truth — refer to them directly for implementation details.

### CI: Lint & Test on Every Push

**File**: [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml)

Triggers on pushes and PRs to `main`. Runs four parallel jobs:

| Job | What it does |
|-----|-------------|
| **lint-python** | Ruff lint + format check, mypy type checking across `packages/` |
| **lint-frontend** | ESLint + TypeScript check on `frontend/` |
| **test-server** | pytest against a PostgreSQL 16 + Redis service container |
| **test-frontend** | Frontend test suite |

A final **build** job runs after all four pass, building Python packages and the frontend.

### Deploy: Build & Ship to Lightsail

**File**: [`.github/workflows/deploy.yml`](../../.github/workflows/deploy.yml)

Triggers on pushes to `main`, PRs to `main`, and manual dispatch. Two jobs:

1. **test** — Runs server tests against a PostgreSQL service container (same as CI)
2. **build-and-deploy** — Only runs on `main` branch after tests pass:
   - Builds Docker image using the repo-root [`Dockerfile`](../../Dockerfile)
   - Installs `lightsailctl` plugin and pushes image to Lightsail
   - Creates a deployment with the `app` container (FastAPI) and a `redis` sidecar
   - Polls the service state until `RUNNING`/`READY` (up to 10 minutes)

Environment variables injected into the Lightsail container at deploy time:

| Env var | Source |
|---------|--------|
| `MC_DATABASE_URL` | `secrets.DATABASE_URL` |
| `MC_SECRET_KEY` | `secrets.SECRET_KEY` |
| `MC_CORS_ORIGINS` | `vars.CORS_ORIGINS` |
| `MC_REDIS_URL` | `redis://localhost:6379/0` (sidecar) |
| `MC_DEBUG` | `false` |

### Database Migration: Manual Trigger

**File**: [`.github/workflows/db-migrate.yaml`](../../.github/workflows/db-migrate.yaml)

A `workflow_dispatch` workflow — trigger it manually from the GitHub **Actions** tab.

Runs `alembic upgrade head` against the production database using `secrets.DATABASE_URL`. Use this to initialize a fresh database or apply new migrations after deploying schema changes.

---

## Database Setup

### Option A: GitHub Actions (Recommended)

1. Ensure `DATABASE_URL` secret is set (see above)
2. Go to **Actions** tab in GitHub
3. Select **"Database Migration"** workflow
4. Click **"Run workflow"**

This runs `alembic upgrade head` against your production database.

### Option B: Local Machine

If you need to run migrations from your local machine (e.g., against a Lightsail database with public access enabled):

```bash
MC_DATABASE_URL="postgresql+asyncpg://postgres:PASSWORD@DB_ENDPOINT:5432/mission_control" \
  uv run --directory packages/server alembic upgrade head
```

---

## First Deployment

### Step 1: Push to Main

1. Ensure all GitHub secrets and variables are configured (see above)
2. Push to `main` — this triggers both `ci.yml` and `deploy.yml`
3. Monitor the **Actions** tab for progress

### Step 2: Initialize the Database

After the first deployment completes:

1. **Run database migrations** via the `db-migrate` workflow (see Database Setup above)

2. **Create admin user** (run locally with the production DB URL):
   ```bash
   MC_DATABASE_URL="your-db-url" \
     uv run python -m app.scripts.create_local_admin \
     --email admin@yourdomain.com \
     --password secure-password
   ```

3. **Access the application**:
   - API docs: `https://your-lightsail-url/docs`
   - Health check: `https://your-lightsail-url/health`

---

## Environment Variables & Secrets Reference

### Application Configuration (`MC_` prefix)

All application settings are loaded via Pydantic in `packages/server/app/core/config.py` with the `MC_` prefix.

| Env var | Type | Default | Description |
|---------|------|---------|-------------|
| `MC_DATABASE_URL` | string | `postgresql+asyncpg://...localhost.../mission_control` | Async PostgreSQL connection string |
| `MC_REDIS_URL` | string | `redis://localhost:6379/0` | Redis connection string |
| `MC_SECRET_KEY` | string | `CHANGE_ME_IN_PRODUCTION` | JWT signing key |
| `MC_CORS_ORIGINS` | string | `http://localhost:5173` | Comma-separated allowed origins |
| `MC_DEBUG` | bool | `false` | Enable debug mode |
| `MC_HOST` | string | `0.0.0.0` | Server bind host |
| `MC_PORT` | int | `8000` | Server bind port |

### GitHub Secrets (set in repo settings)

| Secret | Used by |
|--------|---------|
| `AWS_ACCESS_KEY_ID` | `deploy.yml` |
| `AWS_SECRET_ACCESS_KEY` | `deploy.yml` |
| `DATABASE_URL` | `deploy.yml`, `db-migrate.yaml` |
| `SECRET_KEY` | `deploy.yml`, `ci.yml` (tests) |

### GitHub Variables (set in repo settings)

| Variable | Used by |
|----------|---------|
| `AWS_REGION` | `deploy.yml` |
| `LIGHTSAIL_SERVICE_NAME` | `deploy.yml` |
| `CORS_ORIGINS` | `deploy.yml` |

---

## Troubleshooting

### Deployment Fails

**`Container image not found`**
- Check the "Push to Lightsail" step succeeded in the deploy workflow

**`Health check failed`**
- Verify `/health` endpoint returns 200
- Check database is accessible from the container
- Verify environment variables are set correctly in `deploy.yml`

**`Database connection refused`**
- Lightsail DB must allow traffic from the container service
- Check `DATABASE_URL` format uses the public endpoint

**`pydantic SettingsError / JSONDecodeError on cors_origins`**
- `MC_CORS_ORIGINS` must be a plain comma-separated string (e.g., `https://a.com,https://b.com`), not a JSON array

### GitHub Actions Fails

**`Credentials not found`**
- Verify all secrets/variables are added in GitHub repo settings

**`Group 'dev' is not defined`**
- Root `pyproject.toml` must have a `[dependency-groups]` section with `dev`
- Workflows must use `uv sync --all-packages --group dev`

**`lightsailctl plugin not found`**
- The deploy workflow installs it automatically; check the "Install lightsailctl" step

### Application Issues

**`502 Bad Gateway`**
- Container crashed — check Lightsail container logs in the AWS console

**CORS errors in browser**
- Update the `CORS_ORIGINS` variable in GitHub with the correct frontend URL

---

## Cost Summary

| Component | Service | Monthly Cost |
|-----------|---------|-------------|
| Container Service | Lightsail Nano | **$7** |
| Database | Lightsail PostgreSQL (micro) | **$15** |
| Redis | In-container sidecar | **$0** |
| GitHub Actions | Free tier (2000 min) | **$0** |
| **Total** | | **~$22/month** |

---

## Running CI Locally

You can run the Python CI steps (lint + test) locally without GitHub Actions:

```bash
./scripts/ci-local.sh
```

This runs ruff, mypy, and pytest using the same commands as the CI workflows. See the script for required environment variables (PostgreSQL and Redis must be running).
