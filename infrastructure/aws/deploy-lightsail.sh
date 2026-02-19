#!/bin/bash
# Deploy Mission Control to AWS Lightsail

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

echo "🚀 Deploying Mission Control to AWS Lightsail"

# Configuration
INSTANCE_NAME="${INSTANCE_NAME:-mission-control}"
INSTANCE_PLAN="${INSTANCE_PLAN:-2_0gb}"  # 2 CPU, 0.5GB RAM (smallest)
REGION="${REGION:-us-west-2}"

cd "${PROJECT_ROOT}"

# Build and push Docker image
echo "📦 Building Docker image..."
aws lightsail push-container-image \
    --service-name "${INSTANCE_NAME}" \
    --label app \
    --image mission-control:latest \
    --region "${REGION}"

# Get image reference
IMAGE_REF=$(aws lightsail get-container-images \
    --service-name "${INSTANCE_NAME}" \
    --region "${REGION}" \
    --query 'containerImages[0].image' \
    --output text)

echo "📝 Creating Lightsail container service..."
# Create container service if it doesn't exist
aws lightsail create-container-service \
    --service-name "${INSTANCE_NAME}" \
    --power nano \
    --scale 1 \
    --region "${REGION}" \
    --public-domain-names "{}" 2>/dev/null || true

# Create deployment
echo "🚀 Deploying containers..."
aws lightsail create-container-service-deployment \
    --service-name "${INSTANCE_NAME}" \
    --region "${REGION}" \
    --containers "{
        \"app\": {
            \"image\": \"${IMAGE_REF}\",
            \"ports\": {\"8000\": \"HTTP\"},
            \"environment\": {
                \"MC_DEBUG\": \"false\",
                \"MC_DATABASE_URL\": \"${MC_DATABASE_URL}\",
                \"MC_REDIS_URL\": \"${MC_REDIS_URL}\",
                \"MC_SECRET_KEY\": \"${MC_SECRET_KEY}\"
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

echo "⏳ Waiting for deployment to complete..."
aws lightsail wait container-service-deployment-complete \
    --service-name "${INSTANCE_NAME}" \
    --region "${REGION}"

# Get URL
URL=$(aws lightsail get-container-services \
    --service-name "${INSTANCE_NAME}" \
    --region "${REGION}" \
    --query 'containerServices[0].url' \
    --output text)

echo "✅ Deployment complete!"
echo "🌐 Application URL: ${URL}"
echo "📊 Lightsail Console: https://${REGION}.console.aws.amazon.com/lightsail/home?region=${REGION}#/containers"
