# Staging-only AWS setup

Minimal steps to run FINDMYJOB backend on AWS **staging** only. One VPC, Redis, S3, Secrets Manager, ECS (API + worker), ALB, and Route53 for `api-staging.findmyjob.com`.

**Sizing:** 1 NAT, small Redis, 1 API task, 1 worker task. For prod and scaling, see [INFRA_AWS.md](./INFRA_AWS.md).

---

## Prerequisites

- AWS CLI configured (`aws configure`)
- Domain in Route53 (or add NS at registrar)
- MongoDB Atlas URI (e.g. in `.env` or Secrets Manager)
- Docker (for building images)

---

## 1. VPC

1. **VPC** → Create VPC → **VPC and more**.
2. Name: `findmyjob-staging-vpc`, IPv4 CIDR `10.0.0.0/16`.
3. 2 AZs, 2 public + 2 private subnets, **1 NAT gateway** (to save cost).
4. Create. Note **private** and **public** subnet IDs for later.

---

## 2. Redis (ElastiCache)

1. **ElastiCache** → **Subnet groups** → Create: name `findmyjob-staging-redis-subnets`, VPC = staging VPC, add **both private subnets**.
2. **Redis** → **Create**:  
   - Name: `findmyjob-staging-redis`  
   - Node: `cache.t4g.micro`  
   - Subnet group: `findmyjob-staging-redis-subnets`  
   - **Security group:** Create new `findmyjob-staging-redis-sg`. Leave inbound empty for now; you’ll add API/Worker SGs in step 6.
3. Create cluster. Copy **Primary endpoint** (e.g. `findmyjob-staging-redis.xxxxx.cache.amazonaws.com:6379`).
4. **REDIS_URL:** `redis://findmyjob-staging-redis.xxxxx.cache.amazonaws.com:6379/0` (store for step 5).

---

## 3. S3

1. **S3** → Create bucket: `findmyjob-staging-assets` (unique name), same region as VPC.
2. **Block all public access** → Create.
3. (Optional) Lifecycle rule: delete objects after 14–30 days.

---

## 4. Secrets Manager

1. **Secrets Manager** → Store a new secret → **Other type of secret** (key/value).
2. Add keys (match your app’s config / `.env.example`), e.g.:

   - `MONGODB_URI` – your Atlas URI
   - `MONGODB_DB_NAME` – e.g. `findmyjob`
   - `REDIS_URL` – from step 2
   - `SECRET_KEY` – min 32 chars
   - `TOKEN_ENCRYPTION_KEY` – 44-char base64 or leave empty
   - `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`
   - `GMAIL_OAUTH_REDIRECT_URI` – `https://api-staging.findmyjob.com/v1/gmail/oauth/callback`
   - Any other keys (OpenAI, Razorpay, etc.)

3. Secret name: `findmyjob/staging/app`. Save and note the **secret ARN**.

---

## 5. IAM roles for ECS

**Execution role (pull images + read secrets):**

1. **IAM** → Roles → Create → **ECS** → **ECS Task**.
2. Attach `AmazonECSTaskExecutionRolePolicy`.
3. Add inline policy so tasks can read the secret (replace `ACCOUNT` and `REGION`):

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": ["secretsmanager:GetSecretValue"],
    "Resource": "arn:aws:secretsmanager:REGION:ACCOUNT:secret:findmyjob/staging/app*"
  }]
}
```

4. Name: `findmyjob-staging-ecs-execution-role`.

**Task role (app permissions):**

1. Create role → **ECS Task** → Name: `findmyjob-staging-ecs-task-role`.
2. Attach or add inline policy:
   - **S3:** `GetObject`, `PutObject`, `DeleteObject` on `arn:aws:s3:::findmyjob-staging-assets/*`
   - **Secrets:** `GetSecretValue` on `arn:aws:secretsmanager:REGION:ACCOUNT:secret:findmyjob/staging/app*`

---

## 6. Security groups

Create in the staging VPC:

| Name | Inbound | Use |
|------|---------|-----|
| `findmyjob-staging-alb-sg` | 443 from 0.0.0.0/0 | ALB |
| `findmyjob-staging-api-sg` | 8000 from ALB SG | API tasks |
| `findmyjob-staging-worker-sg` | None | Worker tasks |
| `findmyjob-staging-redis-sg` | 6379 from API SG + Worker SG | Redis (edit the one from step 2) |

---

## 7. ECR + Docker

1. **ECR** → Create repository: `findmyjob-api` (one image can run API or worker via command).
2. From project root:

```bash
aws ecr get-login-password --region REGION | docker login --username AWS --password-stdin ACCOUNT.dkr.ecr.REGION.amazonaws.com
docker build -t findmyjob-api:staging .
docker tag findmyjob-api:staging ACCOUNT.dkr.ecr.REGION.amazonaws.com/findmyjob-api:staging
docker push ACCOUNT.dkr.ecr.REGION.amazonaws.com/findmyjob-api:staging
```

Use your AWS account ID and region for `ACCOUNT` and `REGION`.

---

## 8. ACM + Route53

1. **ACM** (us-east-1 if ALB is in us-east-1) → Request certificate for `api-staging.findmyjob.com`, DNS validation.
2. **Route53** → Create A record (alias): `api-staging.findmyjob.com` → you’ll point this to the ALB in step 9 (or create ALB first and then set the alias target).

---

## 9. ALB + target group

1. **EC2** → Load balancers → **Application Load Balancer**: name `findmyjob-staging-alb`, Internet-facing, **public subnets**, SG = `findmyjob-staging-alb-sg`.
2. **Target group**: type IP, protocol HTTP, port 8000, VPC = staging VPC. Health check path `/health`. Name e.g. `findmyjob-staging-api-tg`.
3. **ALB listener**: HTTPS 443, certificate from step 8, forward to `findmyjob-staging-api-tg`. (Optional: HTTP 80 → redirect 443.)
4. **Route53**: Set the A record for `api-staging.findmyjob.com` to alias to this ALB.

---

## 10. ECS cluster + services

**Cluster:** ECS → Create cluster → **EC2 Linux + Fargate** → name `findmyjob-staging-cluster`.

**Task definition – API:**

1. Task definitions → Create: Fargate, 0.5 vCPU / 1 GB.
2. Task role: `findmyjob-staging-ecs-task-role`; execution role: `findmyjob-staging-ecs-execution-role`.
3. Container: image = `ACCOUNT.dkr.ecr.REGION.amazonaws.com/findmyjob-api:staging`, port 8000.
4. **Secrets:** Add env vars from Secrets Manager (reference secret ARN, map keys to env names like `MONGODB_URI`, `REDIS_URL`, etc.).
5. Log group: create `findmyjob-staging-api` in CloudWatch Logs; use awslogs in container config.

**Task definition – Worker:**

- Same as API, but command override: e.g. `["python", "-m", "app.worker.run_worker"]`, 1 vCPU / 2 GB, log group `findmyjob-staging-worker`. Same secrets.

**API service:**

1. ECS → Cluster → Create service: Fargate, 1 task, **private subnets**, SG = `findmyjob-staging-api-sg`.
2. Load balancer: attach to `findmyjob-staging-alb`, target group `findmyjob-staging-api-tg`, container port 8000.

**Worker service:**

1. Same cluster, Fargate, 1 task, **private subnets**, SG = `findmyjob-staging-worker-sg`. No load balancer.

---

## 11. MongoDB Atlas (staging)

- Use a free/shared cluster or a small dedicated one.
- **Network access:** Add the egress IPs of your NAT (or the private subnet CIDRs if using peering). Easiest for staging: allow **0.0.0.0/0** temporarily, then restrict to NAT IP(s).
- Put the connection string in Secrets Manager as `MONGODB_URI` (step 4).

---

## Staging checklist

- [ ] VPC (2 public + 2 private subnets, 1 NAT)
- [ ] ElastiCache Redis + subnet group; **REDIS_URL** in Secrets Manager
- [ ] S3 bucket `findmyjob-staging-assets` (private)
- [ ] Secrets Manager `findmyjob/staging/app` (Mongo, Redis, OAuth, etc.)
- [ ] IAM: execution role + task role (Secrets + S3)
- [ ] Security groups: ALB, API, Worker, Redis
- [ ] ECR repo; image pushed as `findmyjob-api:staging`
- [ ] ACM cert for `api-staging.findmyjob.com`; Route53 A → ALB
- [ ] ALB + target group (port 8000, `/health`)
- [ ] ECS cluster; API + Worker task definitions; API + Worker services

When you’re ready for production, follow [INFRA_AWS.md](./INFRA_AWS.md) and use `ENV=prod` with the prod domain and larger sizing.
