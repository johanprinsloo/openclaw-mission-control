# Mission Control: AWS Lightsail Manual Deployment Guide

This guide provides step-by-step instructions for manually deploying Mission Control to AWS Lightsail, including GitHub CI/CD setup for automated builds and deployments.

## Table of Contents
1. [AWS Lightsail Setup](#aws-lightsail-setup)
2. [GitHub Repository Configuration](#github-repository-configuration)
3. [CI/CD Pipeline Setup](#cicd-pipeline-setup)
4. [Environment Variables & Secrets](#environment-variables--secrets)
5. [Database Setup](#database-setup)
6. [First Deployment](#first-deployment)
7. [Troubleshooting](#troubleshooting)

---

## AWS Lightsail Setup

### Step 1: Create AWS Account & Access Keys

1. **Sign up for AWS** (if not already done):
   - Go to https://aws.amazon.com
   - Create a new account or sign in
   - Complete the registration process

2. **Create an IAM User** (recommended over using root account):
   - Navigate to **IAM > Users > Add User**
   - User name: `mission-control-deployer`
   - Access type: **Programmatic access** (for CI/CD)
   - Permissions: Attach policies directly:
     - `AmazonLightsailFullAccess`
     - `AmazonRDSFullAccess` (if using RDS instead of Lightsail DB)
     - `AmazonEC2ContainerRegistryFullAccess` (optional, for ECR)
   - Tags: Add `Project=MissionControl` (optional)
   - **Save the Access Key ID and Secret Access Key** - you'll need these for GitHub

### Step 2: Create Lightsail Container Service

1. **Navigate to Lightsail**:
   - Go to https://lightsail.aws.amazon.com
   - Select your region (recommend `us-west-2` for cost/performance)

2. **Create Container Service**:
   - Click **"Containers"** tab
   - Click **"Create container service"**
   - **Service name**: `mission-control-prod` (or `mission-control-dev`)
   - **Deployment**: Choose **"Create a deployment"**
   - **Power**: Select **"Nano"** ($7/month) for dev, or **"Micro"** ($12/month) for light production
   - **Scale**: Set to 1 container for dev, 2 for production
   - Click **"Next"**

3. **Configure Container**:
   - **Container name**: `app`
   - **Image**: Leave blank for now (we'll push from GitHub)
   - **Ports**: Add `8000` (HTTP)
   - **Environment variables**: (we'll set these in deployment, leave empty for now)
   - Click **"Next"**

4. **Public Endpoint**:
   - Enable **"Public endpoint"**
   - **Health check path**: `/health`
   - Click **"Next"**
   - Review and click **"Create container service"**

5. **Get the Service URL**:
   - After creation, note the **Container service URL** (e.g., `https://mission-control-prod.abc123xyz.us-west-2.cs.amazonlightsail.com`)
   - You'll need this for DNS/GitHub

### Step 3: Create Lightsail Database

1. **Navigate to Databases**:
   - In Lightsail, click **"Databases"** tab
   - Click **"Create database"**

2. **Database Configuration**:
   - **Database name**: `mission-control-db`
   - **Database engine**: PostgreSQL 16
   - **Database plan**: 
     - Dev: `db.t2.micro` ($15/month)
     - Prod: `db.t2.small` ($25/month)
   - **Master username**: `postgres`
   - **Master password**: Generate a strong password and **SAVE IT** (you'll need it for GitHub secrets)

3. **Create Database**:
   - Click **"Create database"**
   - Wait for status to show **"Available"** (this takes a few minutes)

4. **Get Database Endpoint**:
   - Click on your database
   - Note the **Endpoint** (e.g., `mission-control-db.xyz.us-west-2.rds.amazonaws.com`)
   - Note the **Port** (usually `5432`)

---

## GitHub Repository Configuration

### Step 1: Add GitHub Secrets

1. **Navigate to Repository Settings**:
   - Go to your GitHub repo: `https://github.com/johanprinsloo/openclaw-mission-control`
   - Click **Settings > Secrets and variables > Actions**
   - Click **"New repository secret"**

2. **Add AWS Credentials** (for Lightsail deployment):
   - Name: `AWS_ACCESS_KEY_ID`
   - Value: Your IAM user's Access Key ID from Step 1
   
   - Name: `AWS_SECRET_ACCESS_KEY`
   - Value: Your IAM user's Secret Access Key from Step 1
   
   - Name: `AWS_REGION`
   - Value: `us-west-2` (or your chosen region)
   
   - Name: `LIGHTSAIL_SERVICE_NAME`
   - Value: `mission-control-prod` (or your service name)

3. **Add Database Secrets**:
   - Name: `DATABASE_URL`
   - Value: `postgresql+asyncpg://postgres:YOUR_PASSWORD@mission-control-db.xyz.us-west-2.rds.amazonaws.com:5432/mission_control`
   - **IMPORTANT**: Replace `YOUR_PASSWORD` with the actual database password
   
   - Name: `DATABASE_PASSWORD`
   - Value: Just the password (for backup/reference)

4. **Add Application Secrets**:
   - Name: `SECRET_KEY`
   - Value: Generate a secure random string (e.g., `openssl rand -base64 32`)
   
   - Name: `CORS_ORIGINS`
   - Value: `["https://your-domain.com", "https://your-app.lightsailapp.com"]`

5. **Add Optional Secrets** (for notifications):
   - Name: `SIGNAL_API_KEY` (if using Signal notifications)
   - Name: `DISCORD_WEBHOOK` (if using Discord notifications)

### Step 2: Enable GitHub Actions

1. **Verify Actions are enabled**:
   - Go to **Settings > Actions > General**
   - Ensure **"Allow all actions and reusable workflows"** is selected
   - Click **Save**

---

## CI/CD Pipeline Setup

### Step 1: Create GitHub Actions Workflow

1. **Create Workflow Directory**:
   ```bash
   mkdir -p .github/workflows
   ```

2. **Create Deployment Workflow** (`.github/workflows/deploy.yml`):

```yaml
name: Deploy to AWS Lightsail

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

env:
  AWS_REGION: ${{ secrets.AWS_REGION }}
  LIGHTSAIL_SERVICE_NAME: ${{ secrets.LIGHTSAIL_SERVICE_NAME }}

jobs:
  test:
    runs-on: ubuntu-latest
    name: Run Tests
    
    steps:
    - name: Checkout code
      uses: actions/checkout@v4

    - name: Set up Python
      uses: actions/setup-python@v5
      with:
        python-version: '3.12'

    - name: Install uv
      uses: astral-sh/setup-uv@v3
      with:
        version: 'latest'

    - name: Install dependencies
      run: |
        cd packages/server
        uv sync --dev

    - name: Run tests
      run: |
        cd packages/server
        uv run pytest tests/ -v --tb=short
      env:
        MC_DATABASE_URL: ${{ secrets.DATABASE_URL }}
        MC_SECRET_KEY: ${{ secrets.SECRET_KEY }}
        MC_DEBUG: 'true'

  build-and-deploy:
    needs: test
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'
    name: Build and Deploy to Lightsail
    
    steps:
    - name: Checkout code
      uses: actions/checkout@v4

    - name: Configure AWS credentials
      uses: aws-actions/configure-aws-credentials@v4
      with:
        aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
        aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
        aws-region: ${{ secrets.AWS_REGION }}

    - name: Set up Docker Buildx
      uses: docker/setup-buildx-action@v3

    - name: Build Docker image
      run: |
        docker build -t mission-control:${{ github.sha }} .
        docker tag mission-control:${{ github.sha }} mission-control:latest

    - name: Push to Lightsail Container Registry
      run: |
        # Install Lightsail plugin
        aws lightsail push-container-image \
          --service-name ${{ secrets.LIGHTSAIL_SERVICE_NAME }} \
          --label app \
          --image mission-control:latest \
          --region ${{ secrets.AWS_REGION }}

    - name: Get container image digest
      id: get-image
      run: |
        IMAGE_DIGEST=$(aws lightsail get-container-images \
          --service-name ${{ secrets.LIGHTSAIL_SERVICE_NAME }} \
          --region ${{ secrets.AWS_REGION }} \
          --query 'containerImages[0].image' \
          --output text)
        echo "image=$IMAGE_DIGEST" >> $GITHUB_OUTPUT

    - name: Deploy to Lightsail
      run: |
        aws lightsail create-container-service-deployment \
          --service-name ${{ secrets.LIGHTSAIL_SERVICE_NAME }} \
          --region ${{ secrets.AWS_REGION }} \
          --containers "{
            \"app\": {
              \"image\": \"${{ steps.get-image.outputs.image }}\",
              \"ports\": {\"8000\": \"HTTP\"},
              \"environment\": {
                \"MC_DEBUG\": \"false\",
                \"MC_DATABASE_URL\": \"${{ secrets.DATABASE_URL }}\",
                \"MC_SECRET_KEY\": \"${{ secrets.SECRET_KEY }}\",
                \"MC_CORS_ORIGINS\": \"${{ secrets.CORS_ORIGINS }}\",
                \"MC_REDIS_URL\": \"redis://localhost:6379/0\"
              }
            },
            \"redis\": {
              \"image\": \"redis:7-alpine\",
              \"environment\": {
                \"REDIS_ARGS\": \"--maxmemory 128mb --maxmemory-policy allkeys-lru\"
              }
            }
          }" \
          --public-endpoint "{
            \"containerName\": \"app\",
            \"containerPort\": 8000,
            \"healthCheck\": {
              \"path\": \"/health\",
              \"intervalSeconds\": 30,
              \"timeoutSeconds\": 5,
              \"healthyThreshold\": 2,
              \"unhealthyThreshold\": 3
            }
          }"

    - name: Wait for deployment
      run: |
        echo "Waiting for deployment to complete..."
        aws lightsail wait container-service-deployment-complete \
          --service-name ${{ secrets.LIGHTSAIL_SERVICE_NAME }} \
          --region ${{ secrets.AWS_REGION }}
        echo "Deployment complete!"

    - name: Get deployment URL
      run: |
        URL=$(aws lightsail get-container-services \
          --service-name ${{ secrets.LIGHTSAIL_SERVICE_NAME }} \
          --region ${{ secrets.AWS_REGION }} \
          --query 'containerServices[0].url' \
          --output text)
        echo "Deployed to: $URL"
        echo "DEPLOYMENT_URL=$URL" >> $GITHUB_ENV

    - name: Notify on success
      if: success()
      run: |
        echo "✅ Deployment successful!"
        echo "🌐 Application URL: ${{ env.DEPLOYMENT_URL }}"
        # Add Slack/Discord notification here if desired

    - name: Notify on failure
      if: failure()
      run: |
        echo "❌ Deployment failed!"
        # Add Slack/Discord notification here if desired
```

### Step 2: Create Pull Request Workflow (Optional)

Create `.github/workflows/pr-checks.yml`:

```yaml
name: PR Checks

on:
  pull_request:
    branches: [main, develop]

jobs:
  lint-and-test:
    runs-on: ubuntu-latest
    name: Lint and Test
    
    steps:
    - name: Checkout code
      uses: actions/checkout@v4

    - name: Set up Python
      uses: actions/setup-python@v5
      with:
        python-version: '3.12'

    - name: Install uv
      uses: astral-sh/setup-uv@v3

    - name: Install dependencies
      run: |
        cd packages/server
        uv sync --dev

    - name: Run linter
      run: |
        cd packages/server
        uv run ruff check .
        uv run ruff format --check .

    - name: Run type checker
      run: |
        cd packages/server
        uv run mypy app/

    - name: Run tests
      run: |
        cd packages/server
        uv run pytest tests/ -v
```

---

## Database Setup

### Step 1: Run Migrations

After the first deployment, you need to run database migrations:

**Option A: Local Machine (with SSH tunnel)**
```bash
# Install AWS Session Manager plugin if needed
# https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-working-with-install-plugin.html

# Port forward to the database
aws lightsail open-instance-public-ports \
  --instance-name mission-control-db \
  --port-info fromPort=5432,toPort=5432,protocol=tcp

# Run migrations
MC_DATABASE_URL="postgresql+asyncpg://postgres:PASSWORD@DB_ENDPOINT:5432/mission_control" \
  uv run alembic upgrade head
```

**Option B: GitHub Actions (One-time setup)**
Add a manual workflow (`.github/workflows/db-migrate.yml`):

```yaml
name: Database Migration

on:
  workflow_dispatch:

jobs:
  migrate:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v4
    
    - name: Setup Python & uv
      uses: astral-sh/setup-uv@v3
      
    - name: Install dependencies
      run: |
        cd packages/server
        uv sync --dev
        
    - name: Run migrations
      run: |
        cd packages/server
        uv run alembic upgrade head
      env:
        MC_DATABASE_URL: ${{ secrets.DATABASE_URL }}
```

Then trigger manually from GitHub Actions tab.

---

## First Deployment

### Step 1: Initial Commit

1. **Commit the workflow files**:
   ```bash
   git add .github/workflows/
   git commit -m "Add GitHub Actions CI/CD for Lightsail deployment"
   git push origin main
   ```

2. **Verify Actions are running**:
   - Go to **Actions** tab in GitHub
   - You should see the "Deploy to AWS Lightsail" workflow running
   - Monitor the logs

### Step 2: First-Time Setup

After the first deployment completes:

1. **Run database migrations** (see Database Setup section)

2. **Create admin user**:
   ```bash
   # SSH into the container or run locally with DB URL
   MC_DATABASE_URL="your-db-url" \
     uv run python -m app.scripts.create_local_admin \
     --email admin@yourdomain.com \
     --password secure-password
   ```

3. **Access the application**:
   - Get the URL from Lightsail console or GitHub Actions logs
   - Navigate to `https://your-url.com/docs` for API docs
   - Login at `https://your-url.com/login`

---

## Environment Variables & Secrets Reference

### Required Secrets

| Secret | Description | Example |
|--------|-------------|---------|
| `AWS_ACCESS_KEY_ID` | IAM user access key | `AKIAIOSFODNN7EXAMPLE` |
| `AWS_SECRET_ACCESS_KEY` | IAM user secret key | `wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY` |
| `AWS_REGION` | AWS region | `us-west-2` |
| `LIGHTSAIL_SERVICE_NAME` | Container service name | `mission-control-prod` |
| `DATABASE_URL` | Full PostgreSQL connection string | `postgresql+asyncpg://user:pass@host:5432/db` |
| `SECRET_KEY` | App secret for JWT/crypto | `random-base64-string` |
| `CORS_ORIGINS` | Allowed frontend origins | `["https://app.example.com"]` |

### Optional Secrets

| Secret | Description | When Needed |
|--------|-------------|-------------|
| `SIGNAL_API_KEY` | Signal Gateway API key | For Signal notifications |
| `DISCORD_WEBHOOK` | Discord webhook URL | For Discord notifications |
| `SENTRY_DSN` | Sentry error tracking | For production monitoring |

---

## Troubleshooting

### Deployment Fails

**Issue**: `Container image not found`
- **Solution**: Ensure the image was pushed successfully in the "Push to Lightsail" step

**Issue**: `Health check failed`
- **Solution**: 
  - Check that `/health` endpoint returns 200
  - Verify database is accessible from container
  - Check environment variables are set correctly

**Issue**: `Database connection refused`
- **Solution**: 
  - Verify Lightsail DB security group allows traffic from container service
  - Check DATABASE_URL format (should use public endpoint)

### GitHub Actions Fails

**Issue**: `Credentials not found`
- **Solution**: Verify all secrets are added to GitHub repository settings

**Issue**: `Tests fail`
- **Solution**: Check test logs, may need to adjust test database configuration

### Application Issues

**Issue**: `502 Bad Gateway`
- **Solution**: Container crashed, check CloudWatch logs or Lightsail container logs

**Issue**: `CORS errors`
- **Solution**: Update `CORS_ORIGINS` secret with correct frontend URL

---

## Cost Summary

| Component | Service | Monthly Cost |
|-----------|---------|-------------|
| Container Service | Lightsail Nano | **$7** |
| Database | Lightsail PostgreSQL (micro) | **$15** |
| Redis | In-container (sidecar) | **$0** |
| GitHub Actions | Free tier (2000 minutes) | **$0** |
| **Total** | | **~$22/month** |

---

## Next Steps

1. ✅ Set up AWS Lightsail services (container + database)
2. ✅ Configure GitHub secrets
3. ✅ Push workflow files to trigger first deployment
4. ✅ Run database migrations
5. ✅ Create initial admin user
6. ✅ Set up custom domain (optional)
7. ✅ Configure monitoring/alerts (CloudWatch)

---

## Support

For issues with:
- **AWS Lightsail**: https://lightsail.aws.amazon.com/docs
- **GitHub Actions**: https://docs.github.com/en/actions
- **Mission Control**: Check the project README or open an issue
