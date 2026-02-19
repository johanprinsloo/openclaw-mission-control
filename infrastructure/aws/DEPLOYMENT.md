# AWS Deployment Guide

This guide covers deploying Mission Control to AWS. We offer two deployment options:

1. **AWS Lightsail** (Recommended for getting started) - Simple, cost-effective, managed containers with **in-container Redis**
2. **AWS CDK/ECS** (Recommended for production) - Full infrastructure as code, auto-scaling, managed databases

## Option 1: AWS Lightsail (Easiest & Cheapest)

AWS Lightsail provides a simple container service that's perfect for getting started. It handles load balancing, SSL, and container orchestration automatically.

### Architecture

This deployment uses a **sidecar pattern** with Redis running in the same container service as the application:

```
┌─────────────────────────────────────────────────────────┐
│          Lightsail Container Service                      │
│  ┌──────────────────┐  ┌──────────────────┐             │
│  │   Mission Control │  │   Redis (sidecar) │             │
│  │   (FastAPI app)   │  │   (localhost:6379)│             │
│  └──────────────────┘  └──────────────────┘             │
└─────────────────────────────────────────────────────────┘
         │
    ┌────┴────┐
Lightsail    Lightsail
PostgreSQL   Managed SSL/ALB
```

**Why in-container Redis?**
- ✅ **Saves ~$15/month** (no separate Redis service)
- ✅ **Zero latency** (same network namespace)
- ✅ **Sufficient for light usage** (ARQ tasks, WebSocket pub/sub)
- ⚠️ **Data not persisted** across container restarts (cache rebuilds - acceptable for dev)

### Prerequisites

- AWS CLI installed and configured
- Docker installed locally
- PostgreSQL database (Lightsail managed or external)
- Environment variables set:
  ```bash
  export MC_DATABASE_URL="postgresql+asyncpg://..."
  export MC_SECRET_KEY="your-production-secret"
  ```

### External Database

For Lightsail deployment, you'll need an external PostgreSQL service:

**Option A: AWS Lightsail Databases** (Recommended)
- Create a Lightsail PostgreSQL database (~$15/month)
- Automatic backups and managed updates

**Option B: RDS PostgreSQL**
- More features but higher cost (~$13/month + data transfer)

### Deploy

```bash
cd infrastructure/aws

# Deploy to Lightsail (includes in-container Redis)
./deploy-lightsail.sh
```

The script will:
1. Build your Docker image
2. Push it to Lightsail Container Registry
3. Deploy the container service with **both app and Redis containers**
4. Configure public endpoint with SSL

### Costs (approximate)

| Component | Service | Cost |
|-----------|---------|------|
| **Container Service** | Lightsail Nano | **$7/month** |
| **PostgreSQL** | Lightsail Database | **$15/month** |
| **Redis** | In-container (sidecar) | **$0/month** ✅ |
| **Total** | | **~$22/month** |

**Savings vs external Redis:** ~$15/month

### When to Upgrade to External Redis

The in-container Redis is perfect for:
- ✅ Development/testing
- ✅ Light production usage (< 100 concurrent users)
- ✅ ARQ task queue and WebSocket pub/sub

**Upgrade to Lightsail Redis or ElastiCache when:**
- 🚀 High availability requirements (99.9% uptime SLA)
- 📊 Large cache datasets (> 500MB)
- 🔄 Zero-downtime deployments (in-container Redis restarts with app)
- 🌐 Multi-AZ deployment needs

**Upgrade path:** Simply change `MC_REDIS_URL` from `redis://localhost:6379/0` to your external Redis endpoint.

## Option 2: AWS CDK (Full Infrastructure)

For production deployments with auto-scaling, managed services, and infrastructure as code.

### Architecture

```
┌─────────────────────────────────────────────────────────┐
│                     VPC                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │
│  │   ECS        │  │   RDS        │  │ ElastiCache  │ │
│  │   Fargate    │  │   PostgreSQL │  │   Redis      │ │
│  └──────────────┘  └──────────────┘  └──────────────┘ │
└─────────────────────────────────────────────────────────┘
```

### Prerequisites

- AWS CLI configured
- AWS CDK installed: `npm install -g aws-cdk`
- Python dependencies: `pip install -r requirements.txt`
- CDK bootstrapped: `cdk bootstrap aws://ACCOUNT_ID/REGION`

### Deploy

```bash
cd infrastructure/aws

# Install dependencies
pip install -r requirements.txt

# Deploy development stack
cdk deploy MissionControlDev

# Or deploy production stack
ck deploy MissionControlProd -c environment=prod
```

### What Gets Created

- **VPC** with public and private subnets
- **RDS PostgreSQL** with automated backups
- **ElastiCache Redis** for ARQ and WebSocket pub/sub
- **ECS Fargate** for container orchestration
- **Application Load Balancer** with health checks
- **Secrets Manager** for credentials
- **CloudWatch Logs** for centralized logging

### Costs (approximate, us-east-1)

**Development:**
- RDS (db.t3.micro): ~$13/month
- ElastiCache (cache.t3.micro): ~$13/month
- ECS Fargate (0.25 vCPU, 0.5 GB): ~$15/month
- ALB: ~$16/month
- **Total: ~$60/month**

**Production:**
- RDS (db.t3.small): ~$25/month
- ElastiCache (cache.t3.small): ~$25/month
- ECS Fargate (1 vCPU, 2 GB) × 2: ~$60/month
- ALB: ~$16/month
- Data transfer: ~$10-30/month
- **Total: ~$140-160/month**

## Database Migration

After deploying, you'll need to run migrations:

```bash
# Get the database endpoint from CDK outputs or Lightsail console
# Then run migrations locally (with appropriate security group rules)
MC_DATABASE_URL="postgresql+asyncpg://postgres:PASSWORD@DB_ENDPOINT:5432/mission_control" \
  uv run alembic upgrade head
```

Or use AWS Systems Manager Session Manager to connect securely.

## SSL/HTTPS

### Lightsail
Lightsail Container Service automatically provisions and manages SSL certificates.

### ECS/CDK
Enable HTTPS in the CDK stack:

```python
# In infrastructure_stack.py, modify the service:
service = ecs_patterns.ApplicationLoadBalancedFargateService(
    ...
    protocol=ecs_patterns.ApplicationLoadBalancedFargateServiceProtocol.HTTPS,
    domain_name="mission-control.yourdomain.com",
    domain_zone=route53.HostedZone.from_lookup(self, "Zone", domain_name="yourdomain.com")
)
```

## Monitoring

### CloudWatch Logs
Application logs are automatically sent to CloudWatch:

```bash
# View logs
aws logs tail /ecs/mission-control-dev --follow
```

### CloudWatch Alarms
Set up alarms for:
- High CPU/memory usage
- Database connection limits
- 5xx error rates
- Health check failures

### RDS Monitoring
Enable Performance Insights and Enhanced Monitoring for detailed database metrics.

## Backup & Recovery

### Database
- RDS automated backups (7-day retention default)
- Manual snapshots before major changes
- Point-in-time recovery available

### Configuration
All infrastructure is defined as code in CDK. State is stored in AWS CloudFormation.

## Security Considerations

1. **Secrets**: All credentials stored in AWS Secrets Manager
2. **Network**: Database and Redis in private subnets (ECS deployment)
3. **Encryption**: Data at rest (RDS storage, ElastiCache) and in transit (TLS)
4. **Access**: Use IAM roles instead of access keys where possible
5. **Updates**: Regularly update base Docker images and dependencies

## Troubleshooting

### Container won't start
```bash
# Check logs
aws logs tail /ecs/mission-control-dev --follow

# Check service events
aws ecs describe-services --cluster mission-control-dev --services mission-control-dev
```

### Database connection issues
- Verify security group rules allow traffic from ECS tasks
- Check database credentials in Secrets Manager
- Ensure database is in AVAILABLE state

### High latency
- Enable CloudWatch X-Ray tracing
- Check RDS Performance Insights for slow queries
- Review ECS task CPU/memory utilization

## Next Steps

1. Set up CI/CD pipeline (GitHub Actions → AWS)
2. Configure monitoring and alerting
3. Set up log aggregation and analysis
4. Implement blue/green deployments
5. Configure automated backups and disaster recovery
