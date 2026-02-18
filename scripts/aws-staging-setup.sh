#!/usr/bin/env bash
# Staging infra for FINDMYJOB: VPC, Redis, S3, Secrets, IAM, ECR, ECS, ALB.
# Usage: ./scripts/aws-staging-setup.sh
# Requires: AWS CLI configured, jq optional for parsing.

set -e
REGION="${AWS_REGION:-ap-south-1}"
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
PREFIX="findmyjob-staging"
VPC_CIDR="10.0.0.0/16"
PUB1_CIDR="10.0.1.0/24"
PUB2_CIDR="10.0.2.0/24"
PRIV1_CIDR="10.0.11.0/24"
PRIV2_CIDR="10.0.12.0/24"

echo "Region: $REGION Account: $ACCOUNT"

# --- 1. VPC ---
echo "Creating VPC..."
VPC_ID=$(aws ec2 create-vpc --cidr-block "$VPC_CIDR" --tag-specifications "ResourceType=vpc,Tags=[{Key=Name,Value=${PREFIX}-vpc}]" --query Vpc.VpcId --output text)
aws ec2 modify-vpc-attribute --vpc-id "$VPC_ID" --enable-dns-hostnames
aws ec2 modify-vpc-attribute --vpc-id "$VPC_ID" --enable-dns-support

# Subnets (ap-south-1a, ap-south-1b - adjust if different region)
AZ1="${REGION}a"
AZ2="${REGION}b"
PUB_SUBNET1=$(aws ec2 create-subnet --vpc-id "$VPC_ID" --cidr-block "$PUB1_CIDR" --availability-zone "$AZ1" --tag-specifications "ResourceType=subnet,Tags=[{Key=Name,Value=${PREFIX}-pub1}]" --query Subnet.SubnetId --output text)
PUB_SUBNET2=$(aws ec2 create-subnet --vpc-id "$VPC_ID" --cidr-block "$PUB2_CIDR" --availability-zone "$AZ2" --tag-specifications "ResourceType=subnet,Tags=[{Key=Name,Value=${PREFIX}-pub2}]" --query Subnet.SubnetId --output text)
PRIV_SUBNET1=$(aws ec2 create-subnet --vpc-id "$VPC_ID" --cidr-block "$PRIV1_CIDR" --availability-zone "$AZ1" --tag-specifications "ResourceType=subnet,Tags=[{Key=Name,Value=${PREFIX}-priv1}]" --query Subnet.SubnetId --output text)
PRIV_SUBNET2=$(aws ec2 create-subnet --vpc-id "$VPC_ID" --cidr-block "$PRIV2_CIDR" --availability-zone "$AZ2" --tag-specifications "ResourceType=subnet,Tags=[{Key=Name,Value=${PREFIX}-priv2}]" --query Subnet.SubnetId --output text)

# Internet Gateway
IGW_ID=$(aws ec2 create-internet-gateway --tag-specifications "ResourceType=internet-gateway,Tags=[{Key=Name,Value=${PREFIX}-igw}]" --query InternetGateway.InternetGatewayId --output text)
aws ec2 attach-internet-gateway --vpc-id "$VPC_ID" --internet-gateway-id "$IGW_ID"

# NAT Gateway (need EIP in public subnet)
EIP_ALLOC=$(aws ec2 allocate-address --domain vpc --query AllocationId --output text)
NAT_ID=$(aws ec2 create-nat-gateway --subnet-id "$PUB_SUBNET1" --allocation-id "$EIP_ALLOC" --tag-specifications "ResourceType=natgateway,Tags=[{Key=Name,Value=${PREFIX}-nat}]" --query NatGateway.NatGatewayId --output text)
echo "Waiting for NAT Gateway to be available..."
aws ec2 wait nat-gateway-available --nat-gateway-ids "$NAT_ID"

# Route tables
PUB_RT=$(aws ec2 create-route-table --vpc-id "$VPC_ID" --tag-specifications "ResourceType=route-table,Tags=[{Key=Name,Value=${PREFIX}-pub-rt}]" --query RouteTable.RouteTableId --output text)
aws ec2 create-route --route-table-id "$PUB_RT" --destination-cidr-block 0.0.0.0/0 --gateway-id "$IGW_ID"
aws ec2 associate-route-table --route-table-id "$PUB_RT" --subnet-id "$PUB_SUBNET1"
aws ec2 associate-route-table --route-table-id "$PUB_RT" --subnet-id "$PUB_SUBNET2"

PRIV_RT=$(aws ec2 create-route-table --vpc-id "$VPC_ID" --tag-specifications "ResourceType=route-table,Tags=[{Key=Name,Value=${PREFIX}-priv-rt}]" --query RouteTable.RouteTableId --output text)
aws ec2 create-route --route-table-id "$PRIV_RT" --destination-cidr-block 0.0.0.0/0 --nat-gateway-id "$NAT_ID"
aws ec2 associate-route-table --route-table-id "$PRIV_RT" --subnet-id "$PRIV_SUBNET1"
aws ec2 associate-route-table --route-table-id "$PRIV_RT" --subnet-id "$PRIV_SUBNET2"

echo "VPC_ID=$VPC_ID PUB_SUBNET1=$PUB_SUBNET1 PUB_SUBNET2=$PUB_SUBNET2 PRIV_SUBNET1=$PRIV_SUBNET1 PRIV_SUBNET2=$PRIV_SUBNET2"

# --- 2. Security groups ---
echo "Creating security groups..."
ALB_SG=$(aws ec2 create-security-group --group-name "${PREFIX}-alb-sg" --description "ALB" --vpc-id "$VPC_ID" --query GroupId --output text)
aws ec2 authorize-security-group-ingress --group-id "$ALB_SG" --protocol tcp --port 443 --cidr 0.0.0.0/0
aws ec2 authorize-security-group-ingress --group-id "$ALB_SG" --protocol tcp --port 80 --cidr 0.0.0.0/0

API_SG=$(aws ec2 create-security-group --group-name "${PREFIX}-api-sg" --description "API tasks" --vpc-id "$VPC_ID" --query GroupId --output text)
aws ec2 authorize-security-group-ingress --group-id "$API_SG" --protocol tcp --port 8000 --source-group "$ALB_SG"

WORKER_SG=$(aws ec2 create-security-group --group-name "${PREFIX}-worker-sg" --description "Worker tasks" --vpc-id "$VPC_ID" --query GroupId --output text)

REDIS_SG=$(aws ec2 create-security-group --group-name "${PREFIX}-redis-sg" --description "Redis" --vpc-id "$VPC_ID" --query GroupId --output text)
aws ec2 authorize-security-group-ingress --group-id "$REDIS_SG" --protocol tcp --port 6379 --source-group "$API_SG"
aws ec2 authorize-security-group-ingress --group-id "$REDIS_SG" --protocol tcp --port 6379 --source-group "$WORKER_SG"

echo "ALB_SG=$ALB_SG API_SG=$API_SG WORKER_SG=$WORKER_SG REDIS_SG=$REDIS_SG"

# --- 3. ElastiCache Redis ---
echo "Creating Redis subnet group and cluster..."
aws elasticache create-cache-subnet-group \
  --cache-subnet-group-name "${PREFIX}-redis-subnets" \
  --cache-subnet-group-description "Staging Redis" \
  --subnet-ids "$PRIV_SUBNET1" "$PRIV_SUBNET2"

aws elasticache create-cache-cluster \
  --cache-cluster-id "${PREFIX}-redis" \
  --cache-node-type cache.t4g.micro \
  --engine redis \
  --num-cache-nodes 1 \
  --cache-subnet-group-name "${PREFIX}-redis-subnets" \
  --security-group-ids "$REDIS_SG" \
  --tags Key=Name,Value="${PREFIX}-redis"

echo "Redis cluster creating (takes ~3–5 min). Get endpoint later: aws elasticache describe-cache-clusters --cache-cluster-id ${PREFIX}-redis --show-cache-node-info"

# --- 4. S3 ---
BUCKET="${PREFIX}-assets-${ACCOUNT}"
if ! aws s3api head-bucket --bucket "$BUCKET" 2>/dev/null; then
  if [ "$REGION" = "us-east-1" ]; then
    aws s3api create-bucket --bucket "$BUCKET" --region "$REGION"
  else
    aws s3api create-bucket --bucket "$BUCKET" --region "$REGION" --create-bucket-configuration LocationConstraint="$REGION"
  fi
fi
aws s3api put-public-access-block --bucket "$BUCKET" --public-access-block-configuration BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
echo "S3 bucket: $BUCKET"

# --- 5. Secrets Manager (placeholders; update in console) ---
SECRET_JSON=$(cat <<'EOF'
{
  "MONGODB_URI": "REPLACE_ME",
  "MONGODB_DB_NAME": "findmyjob",
  "REDIS_URL": "REPLACE_AFTER_REDIS_READY",
  "SECRET_KEY": "REPLACE_ME_MIN_32_CHARS",
  "TOKEN_ENCRYPTION_KEY": "",
  "GOOGLE_CLIENT_ID": "REPLACE_ME",
  "GOOGLE_CLIENT_SECRET": "REPLACE_ME",
  "GMAIL_OAUTH_REDIRECT_URI": "https://api-staging.findmyjob.com/v1/gmail/oauth/callback",
  "RAZORPAY_KEY_ID": "",
  "RAZORPAY_KEY_SECRET": "",
  "RAZORPAY_WEBHOOK_SECRET": "",
  "OPENAI_API_KEY": "",
  "STORAGE_BACKEND": "s3",
  "CORS_ORIGINS": "https://api-staging.findmyjob.com"
}
EOF
)
SECRET_ARN=$(aws secretsmanager create-secret --name "findmyjob/staging/app" --secret-string "$SECRET_JSON" --region "$REGION" --query ARN --output text 2>/dev/null || aws secretsmanager describe-secret --secret-id "findmyjob/staging/app" --query ARN --output text)
echo "Secret: findmyjob/staging/app ($SECRET_ARN)"

# --- 6. IAM roles ---
echo "Creating IAM roles..."
EXEC_TRUST='{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"ecs-tasks.amazonaws.com"},"Action":"sts:AssumeRole"}]}'
aws iam create-role --role-name "${PREFIX}-ecs-execution-role" --assume-role-policy-document "$EXEC_TRUST" 2>/dev/null || true
aws iam attach-role-policy --role-name "${PREFIX}-ecs-execution-role" --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy
EXEC_SECRETS_POLICY=$(cat <<EOF
{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Action":["secretsmanager:GetSecretValue"],"Resource":"arn:aws:secretsmanager:${REGION}:${ACCOUNT}:secret:findmyjob/staging/app*"}]}
EOF
)
aws iam put-role-policy --role-name "${PREFIX}-ecs-execution-role" --policy-name SecretsManagerRead --policy-document "$EXEC_SECRETS_POLICY"

aws iam create-role --role-name "${PREFIX}-ecs-task-role" --assume-role-policy-document "$EXEC_TRUST" 2>/dev/null || true
TASK_POLICY=$(cat <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {"Effect": "Allow", "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"], "Resource": "arn:aws:s3:::${BUCKET}/*"},
    {"Effect": "Allow", "Action": ["secretsmanager:GetSecretValue"], "Resource": "arn:aws:secretsmanager:${REGION}:${ACCOUNT}:secret:findmyjob/staging/app*"}
  ]
}
EOF
)
aws iam put-role-policy --role-name "${PREFIX}-ecs-task-role" --policy-name S3AndSecrets --policy-document "$TASK_POLICY"

# --- 7. ECR ---
aws ecr create-repository --repository-name findmyjob-api --region "$REGION" 2>/dev/null || true
ECR_URI="${ACCOUNT}.dkr.ecr.${REGION}.amazonaws.com/findmyjob-api"
echo "ECR: $ECR_URI"

# --- 8. ECS cluster ---
aws ecs create-cluster --cluster-name "${PREFIX}-cluster" --region "$REGION" 2>/dev/null || true

# --- 9. ALB + Target group ---
TG_ARN=$(aws elbv2 create-target-group --name "${PREFIX}-api-tg" --protocol HTTP --port 8000 --vpc-id "$VPC_ID" --target-type ip --health-check-path /health --query TargetGroups[0].TargetGroupArn --output text)
ALB_ARN=$(aws elbv2 create-load-balancer --name "${PREFIX}-alb" --subnets "$PUB_SUBNET1" "$PUB_SUBNET2" --security-groups "$ALB_SG" --scheme internet-facing --query LoadBalancers[0].LoadBalancerArn --output text)
aws elbv2 create-listener --load-balancer-arn "$ALB_ARN" --protocol HTTP --port 80 --default-actions Type=forward,TargetGroupArn="$TG_ARN"
echo "ALB created (HTTP:80). Add HTTPS later with ACM cert."

# --- 10. CloudWatch log groups ---
aws logs create-log-group --log-group-name "${PREFIX}-api" --region "$REGION" 2>/dev/null || true
aws logs create-log-group --log-group-name "${PREFIX}-worker" --region "$REGION" 2>/dev/null || true

# --- Output for task definition ---
echo ""
echo "=== Staging infra created. Next steps ==="
echo "1. Wait for Redis: aws elasticache describe-cache-clusters --cache-cluster-id ${PREFIX}-redis --show-cache-node-info --query 'CacheClusters[0].CacheNodes[0].Endpoint'"
echo "2. Update Secrets Manager 'findmyjob/staging/app': set REDIS_URL, MONGODB_URI, SECRET_KEY, Google OAuth, etc."
echo "3. Build and push image: docker build -t findmyjob-api:staging . && docker tag findmyjob-api:staging $ECR_URI:staging && aws ecr get-login-password --region $REGION | docker login --username AWS --password-stdin $ACCOUNT.dkr.ecr.$REGION.amazonaws.com && docker push $ECR_URI:staging"
echo "4. Run: ./scripts/aws-staging-ecs-services.sh  (creates task definitions and ECS services)"
echo ""
echo "Exported for next script: VPC_ID PRIV_SUBNET1 PRIV_SUBNET2 API_SG WORKER_SG TG_ARN ECR_URI REGION ACCOUNT PREFIX BUCKET SECRET_ARN"
