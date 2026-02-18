# AWS Infrastructure Setup (Staging + Prod)

Step-by-step guide to bring up the FINDMYJOB backend on AWS for ~1000 users: ECS (API + worker), ElastiCache Redis, S3, Secrets Manager, ALB, and optional MongoDB Atlas + CI/CD.

**Domains (from plan):**
- Prod: `api.findmyjob.com`
- Staging: `api-staging.findmyjob.com`

**Isolation:** Prefer 2 AWS accounts (staging + prod). Otherwise use 1 account with 2 VPCs and strict IAM.

---

## Prerequisites

- AWS CLI installed and configured (`aws configure`)
- Domain in Route53 (or ability to create hosted zone and NS records at your registrar)
- MongoDB Atlas account (recommended) or self-hosted Mongo
- Docker (for building images)

---

## 1. Choose account strategy

| Option | Staging | Prod | Notes |
|--------|---------|------|--------|
| **A: Two accounts** | `findmyjob-staging` | `findmyjob-prod` | Best isolation; use AWS Organizations |
| **B: One account** | VPC `findmyjob-staging` | VPC `findmyjob-prod` | Simpler; separate VPCs + IAM |

Repeat the steps below **per environment** (staging first, then prod). Replace `ENV` with `staging` or `prod` in names.

---

## 2. VPC and networking (per environment)

### 2.1 Create VPC

- **Console:** VPC → Create VPC → “VPC and more”.
- **Settings:**
  - Name: `findmyjob-ENV-vpc`
  - IPv4 CIDR: e.g. `10.0.0.0/16`
  - 2 AZs, 2 public + 2 private subnets
  - Enable “NAT gateway” (1 for cost efficiency, or 2 for multi-AZ)
  - VPC endpoint for S3 (optional; saves NAT traffic for S3)

- **CLI (conceptual):** Use the same wizard output or create subnets manually:
  - Public: `10.0.1.0/24`, `10.0.2.0/24`
  - Private: `10.0.11.0/24`, `10.0.12.0/24`

### 2.2 Note subnet IDs

You will need:

- **Private subnets** (for ECS tasks + Redis): e.g. `subnet-private-1`, `subnet-private-2`
- **Public subnets** (for ALB only): e.g. `subnet-public-1`, `subnet-public-2`

---

## 3. ElastiCache Redis (per environment)

Redis is used for: ARQ queue, session store, rate limiting. Use key prefixes: `prod:*` / `staging:*`.

### 3.1 Create subnet group

1. ElastiCache → Subnet groups → Create.
2. Name: `findmyjob-ENV-redis-subnets`.
3. VPC: `findmyjob-ENV-vpc`.
4. Add **private subnets** (both AZs).

### 3.2 Create Redis cluster

1. ElastiCache → Redis → Create.
2. **Cluster mode:** Disabled.
3. **Name:** `findmyjob-ENV-redis`.
4. **Engine:** Redis 7.x.
5. **Node type:**
   - Staging: `cache.t4g.micro` or `cache.t4g.small`.
   - Prod: `cache.t4g.small` or `cache.t4g.medium` (single node to start).
6. **Replicas:** 0 (single node); later for prod you can add replicas for HA.
7. **Subnet group:** `findmyjob-ENV-redis-subnets`.
8. **Security group:** Create new, e.g. `findmyjob-ENV-redis-sg` (no public access).
   - Inbound: TCP 6379 from **API and Worker security groups** (create those in step 6 and come back to add them here, or use a single “app” SG for both API and worker).
9. **Encryption:** At-rest and in-transit recommended for prod.
10. **Parameter group (optional):** Create one with `maxmemory-policy volatile-lru`.

### 3.3 Get Redis endpoint

After creation, copy the **Primary endpoint** (e.g. `findmyjob-env-redis.xxxxx.cache.amazonaws.com:6379`).

**REDIS_URL format:**

```text
redis://[:password@]findmyjob-env-redis.xxxxx.cache.amazonaws.com:6379/0
```

If you enabled in-transit encryption, use `rediss://` and ensure your Redis client supports TLS. Store this in Secrets Manager (see step 5).

---

## 4. S3 buckets (per environment)

### 4.1 Create bucket

- **Name:** `findmyjob-ENV-assets` (globally unique).
- **Region:** Same as ECS/VPC.
- **Block all public access** (use presigned URLs only).

### 4.2 Object structure (convention)

- `resumes/{user_id}/{file_id}`
- `lists/{user_id}/{list_id}`
- `exports/{user_id}/{job_id}.csv`

### 4.3 Lifecycle (optional)

- **Staging:** Lifecycle rule to delete objects after 14–30 days.
- **Prod:** e.g. 90 days or your retention policy.

### 4.4 IAM

- API and Worker task roles need S3 access (see step 6). Prefer:
  - `s3:GetObject`, `s3:PutObject`, `s3:DeleteObject` on `arn:aws:s3:::findmyjob-ENV-assets/*`
  - No public read; app uses presigned URLs.

---

## 5. Secrets Manager (per environment)

Create one secret “per app” or one secret per env containing a JSON of all keys. Option: **one secret per env** with key-value pairs.

### 5.1 Create secret

1. Secrets Manager → Store a new secret.
2. Type: **Other type of secret** (key/value).
3. Add keys (example; align with your `.env` and config):

| Key | Description |
|-----|-------------|
| `MONGODB_URI` | Atlas connection string (or your Mongo URI) |
| `MONGODB_DB_NAME` | e.g. `findmyjob` |
| `REDIS_URL` | From step 3.3 |
| `SECRET_KEY` | Min 32 chars (session signing) |
| `TOKEN_ENCRYPTION_KEY` | 44-char base64 (Fernet) or leave empty to derive from SECRET_KEY |
| `GOOGLE_CLIENT_ID` | OAuth 2.0 client ID |
| `GOOGLE_CLIENT_SECRET` | OAuth 2.0 client secret |
| `GMAIL_OAUTH_REDIRECT_URI` | e.g. `https://api.findmyjob.com/v1/gmail/oauth/callback` |
| `OPENAI_API_KEY` | If used |
| `RAZORPAY_KEY` / `RAZORPAY_SECRET` | Payment provider |
| Any other API keys (SendGrid, etc.) |

4. Secret name: `findmyjob/ENV/app` (or `findmyjob/ENV/config`).

### 5.2 IAM

- ECS task roles for API and Worker need `secretsmanager:GetSecretValue` on this secret’s ARN.

---

## 6. ECS cluster and task roles

### 6.1 ECS cluster

- ECS → Clusters → Create → **EC2 Linux + Fargate**.
- Name: `findmyjob-ENV-cluster`.

### 6.2 Task execution role

- IAM → Roles → Create role → AWS service → **ECS → ECS Task**.
- Attach: `AmazonECSTaskExecutionRolePolicy`.
- For private ECR + Secrets: ensure role can pull from ECR and read Secrets Manager (or add inline policy for `secretsmanager:GetSecretValue` on your secret).
- Name: `findmyjob-ENV-ecs-execution-role`.

### 6.3 Task role (for API and Worker)

- IAM → Create role → AWS service → **ECS Task**.
- Name: `findmyjob-ENV-ecs-task-role`.
- Attach policies (or custom policy):
  - S3: `GetObject`, `PutObject`, `DeleteObject` on `findmyjob-ENV-assets/*`.
  - Secrets Manager: `GetSecretValue` on `findmyjob/ENV/app`.
  - (No direct DynamoDB/RDS if you use only Mongo and Redis.)

### 6.4 Security groups

Create and note IDs:

1. **ALB SG** (`findmyjob-ENV-alb-sg`):
   - Inbound: 443 from `0.0.0.0/0` (or your WAF/CloudFront).
   - Outbound: all (or only to API SG).

2. **API SG** (`findmyjob-ENV-api-sg`):
   - Inbound: 80/8080 (or your app port) from **ALB SG**.
   - Outbound: all (Mongo, Redis, S3, Google, Razorpay, etc.).

3. **Worker SG** (`findmyjob-ENV-worker-sg`):
   - Inbound: none.
   - Outbound: all.

4. **Redis SG** (from step 3.2):
   - Inbound: 6379 from **API SG** and **Worker SG**.

---

## 7. ECR and Docker images

### 7.1 Create repositories

- ECR → Create repository: `findmyjob-api`, `findmyjob-worker` (or one repo with different tags).

### 7.2 Build and push

From project root (Dockerfile at root for API; worker can use same image with different command):

```bash
aws ecr get-login-password --region REGION | docker login --username AWS --password-stdin ACCOUNT_ID.dkr.ecr.REGION.amazonaws.com
docker build -t findmyjob-api:latest .
docker tag findmyjob-api:latest ACCOUNT_ID.dkr.ecr.REGION.amazonaws.com/findmyjob-api:latest
docker push ACCOUNT_ID.dkr.ecr.REGION.amazonaws.com/findmyjob-api:latest
```

Use the same image for worker with entrypoint override to run the ARQ worker.

---

## 8. ALB + TLS + Route53

### 8.1 ACM certificate

- Request certificate in **us-east-1** (for ALB) for:
  - `api.findmyjob.com` (prod)
  - `api-staging.findmyjob.com` (staging)
- Validate via DNS (Route53 or manual CNAME).

### 8.2 Application Load Balancer

- EC2 → Load Balancers → Application Load Balancer.
- Name: `findmyjob-ENV-alb`.
- Scheme: Internet-facing.
- VPC and **public subnets** (both AZs).
- Security group: **ALB SG**.
- Listeners:
  - HTTPS 443 → forward to target group (e.g. `findmyjob-ENV-api-tg`).
  - Optional: HTTP 80 → redirect to 443.

### 8.3 Target group

- Target type: IP (Fargate).
- VPC: same as ALB.
- Protocol: HTTP, port 8000 (or your API port).
- Health check: path `/health`, healthy threshold 2, unhealthy 3.

### 8.4 Route53

- Create A record (alias): `api.findmyjob.com` or `api-staging.findmyjob.com` → ALB alias.

---

## 9. ECS services (API and Worker)

### 9.1 Task definition – API

- ECS → Task definitions → Create.
- Launch type: Fargate.
- Task size (prod): 0.5 vCPU, 1 GB (or 1 vCPU / 2 GB if needed).
- Task role: `findmyjob-ENV-ecs-task-role`.
- Task execution role: `findmyjob-ENV-ecs-execution-role`.
- Container:
  - Image: `ACCOUNT_ID.dkr.ecr.REGION.amazonaws.com/findmyjob-api:latest`.
  - Port: 8000.
  - Environment: none (use Secrets Manager or inject env from secret in task def).
  - Log: awslogs, group `findmyjob-ENV-api`, region.
- **Secrets:** Add all keys from Secrets Manager as environment variables (reference by ARN and key name).

### 9.2 Task definition – Worker

- Same as API except:
  - Command/entrypoint: run ARQ worker (e.g. `python -m app.worker.run_worker`).
  - Task size (prod): 1 vCPU, 2 GB.
  - Log: `findmyjob-ENV-worker`.

### 9.3 Create API service

- Cluster: `findmyjob-ENV-cluster`.
- Service name: `api`.
- Task definition: API task def (latest revision).
- Desired count: prod 2, staging 1.
- Deployment: Rolling update.
- VPC and **private subnets**; **API SG**.
- Load balancer: attach to existing ALB, target group `findmyjob-ENV-api-tg`, container: API container, port 8000.

### 9.4 Create Worker service

- No load balancer.
- Same cluster, private subnets, **Worker SG**.
- Desired count: prod 2, staging 1.

---

## 10. MongoDB Atlas (if used)

- Create cluster per env (e.g. M10 prod, free/shared staging).
- **Network:** VPC peering to `findmyjob-ENV-vpc` (recommended) or IP allowlist (NAT gateway egress IPs from private subnets).
- **Database user** and connection string → put `MONGODB_URI` (and `MONGODB_DB_NAME`) into Secrets Manager.
- Indexes (from your plan): `scheduled_emails (status, scheduled_at)`, `sent_history (user_id, recipient_email)`, `recipient_items (list_id, email)`, `campaigns (user_id, status)`.

---

## 11. WAF (optional)

- Create Web ACL in WAFv2; attach to ALB.
- Add rules: rate limit per IP, managed rule set (e.g. AWSManagedRulesCommonRuleSet), and optionally allow only your frontend origins for API.

---

## 12. Monitoring and alarms

- **CloudWatch Logs:** ECS task definitions already use `awslogs`; ensure log groups exist (`findmyjob-ENV-api`, `findmyjob-ENV-worker`).
- **Alarms (prod):**
  - ALB 5xx count > threshold.
  - ECS API/Worker CPU or memory.
  - ECS task restart (metric from ECS).
  - Redis memory (ElastiCache metrics) > 75%.
- **Sentry:** Separate project per env; set `SENTRY_DSN` in Secrets Manager and inject into API/Worker.

---

## 13. Checklist (per environment)

Use this to track what you’ve created.

- [ ] VPC (2 public + 2 private subnets, NAT gateway)
- [ ] ElastiCache Redis (subnet group, cluster, security group, **REDIS_URL** in Secrets Manager)
- [ ] S3 bucket `findmyjob-ENV-assets` (private, lifecycle if desired)
- [ ] Secrets Manager secret with all app env vars (including REDIS_URL, MONGODB_URI, etc.)
- [ ] ECS cluster
- [ ] ECS task execution role + task role (S3, Secrets Manager)
- [ ] Security groups: ALB, API, Worker, Redis
- [ ] ECR repos; Docker build and push
- [ ] ACM certificate (us-east-1); Route53 A record
- [ ] ALB + target group; listener 443
- [ ] ECS API service (Fargate, private subnets, ALB)
- [ ] ECS Worker service (Fargate, private subnets)
- [ ] MongoDB Atlas cluster + peering/allowlist; connection string in secret
- [ ] CloudWatch log groups + alarms (prod)
- [ ] WAF (optional)

---

## 14. Quick reference – Redis only

If you only want the minimal steps for **Redis on AWS**:

1. VPC with private subnets (or use default VPC and a private subnet).
2. ElastiCache → Subnet group (those subnets) → Create Redis cluster (e.g. `cache.t4g.micro` for dev/staging).
3. Security group: allow TCP 6379 from your API/Worker (or your IP for testing).
4. Copy Primary endpoint → `REDIS_URL=redis://host:6379/0`.
5. Put `REDIS_URL` into `.env` or Secrets Manager and restart API + Worker.

Once the rest of the infra (ECS, Secrets Manager, ALB) is in place, point the ECS task definitions to the same secret so both API and Worker use this Redis URL.
