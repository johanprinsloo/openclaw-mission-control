# AWS CDK Infrastructure for Mission Control

This directory contains AWS CDK code to deploy Mission Control infrastructure.

## Architecture

- **VPC**: Private subnet for database, public subnet for application
- **RDS PostgreSQL**: Managed database with automated backups
- **ElastiCache Redis**: Managed Redis for ARQ queue and WebSocket pub/sub
- **ECS Fargate**: Container orchestration for the application
- **Application Load Balancer**: HTTPS termination and routing
- **Secrets Manager**: Secure storage for database credentials and API keys

## Prerequisites

1. AWS CLI configured with appropriate credentials
2. AWS CDK installed: `npm install -g aws-cdk`
3. Python dependencies: `pip install -r requirements.txt`

## Deployment

1. **Bootstrap CDK** (first time only):
   ```bash
   cdk bootstrap aws://YOUR_ACCOUNT_ID/YOUR_REGION
   ```

2. **Deploy the stack**:
   ```bash
   cdk deploy
   ```

3. **Get outputs**:
   After deployment, CDK will output:
   - Load balancer URL
   - Database endpoint
   - Redis endpoint

## Environment Variables

Create a `.env` file in the project root with:

```
MC_DATABASE_URL=postgresql+asyncpg://postgres:PASSWORD@DB_ENDPOINT:5432/mission_control
MC_REDIS_URL=redis://REDIS_ENDPOINT:6379/0
MC_SECRET_KEY=your-production-secret-key
MC_DEBUG=false
```

## Cost Estimates (us-east-1)

- RDS PostgreSQL (db.t3.micro): ~$13/month
- ElastiCache Redis (cache.t3.micro): ~$13/month
- ECS Fargate (1 vCPU, 2 GB): ~$30/month
- Application Load Balancer: ~$16/month + data processing
- Data transfer: ~$5-20/month (depends on usage)

**Total: ~$75-100/month** for a small production deployment
