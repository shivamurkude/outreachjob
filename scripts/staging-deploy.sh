#!/usr/bin/env bash
# Build, push staging image to ECR, then verify ECS and health.
# Run from project root: ./scripts/staging-deploy.sh
# Requires: Docker running, AWS CLI configured.

set -e
REGION="ap-south-1"
ECR_URI="690637085216.dkr.ecr.ap-south-1.amazonaws.com/findmyjob-api"
ALB_DNS="findmyjob-staging-alb-1315898380.ap-south-1.elb.amazonaws.com"

echo "1. Logging in to ECR..."
aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin 690637085216.dkr.ecr.ap-south-1.amazonaws.com

echo "2. Building Docker image..."
docker build -t findmyjob-api:staging .

echo "3. Tagging and pushing..."
docker tag findmyjob-api:staging "$ECR_URI:staging"
docker push "$ECR_URI:staging"

echo "4. Image pushed. ECS will pull and start tasks (wait ~1–2 min)."
echo "   Checking task status in 30s..."
sleep 30

aws ecs describe-services --cluster findmyjob-staging-cluster --services api worker --region "$REGION" \
  --query 'services[*].{Service:serviceName, Running:runningCount, Desired:desiredCount}' --output table

echo ""
echo "5. Testing /health..."
for i in 1 2 3 4 5; do
  if curl -sf "http://${ALB_DNS}/health" >/dev/null 2>&1; then
    echo "   OK: API is responding at http://${ALB_DNS}/health"
    curl -s "http://${ALB_DNS}/health" | head -1
    exit 0
  fi
  echo "   Attempt $i: waiting 15s..."
  sleep 15
done

echo "   API not responding yet. Check ECS tasks and CloudWatch logs: findmyjob-staging-api, findmyjob-staging-worker"
exit 1
