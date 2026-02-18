# Staging infra – next steps

Staging infrastructure on AWS (ap-south-1) is created. Do the following to get the API and worker running.

---

## What’s already created

| Resource | Value |
|----------|--------|
| **Region** | ap-south-1 |
| **VPC** | findmyjob-staging-vpc (vpc-06a6c0b18f05d7bc8) |
| **Redis** | findmyjob-staging-redis (ElastiCache, single node) |
| **S3 bucket** | findmyjob-staging-assets-690637085216 |
| **Secrets Manager** | findmyjob/staging/app |
| **ECS cluster** | findmyjob-staging-cluster |
| **ALB** | findmyjob-staging-alb |
| **ALB DNS** | findmyjob-staging-alb-1315898380.ap-south-1.elb.amazonaws.com |
| **ECR repo** | 690637085216.dkr.ecr.ap-south-1.amazonaws.com/findmyjob-api |
| **API service** | 1 task (will run after image is pushed) |
| **Worker service** | 1 task (will run after image is pushed) |

---

## 1. Get Redis endpoint

Redis can take a few minutes to become available. When ready:

```bash
aws elasticache describe-cache-clusters --cache-cluster-id findmyjob-staging-redis --show-cache-node-info --region ap-south-1 --query 'CacheClusters[0].CacheNodes[0].Endpoint'
```

Use the **Address** and **Port** to form:

```text
REDIS_URL=redis://<Address>:<Port>/0
```

Example: `redis://findmyjob-staging-redis.xxxxx.cache.amazonaws.com:6379/0`

---

## 2. Update Secrets Manager

In **AWS Console → Secrets Manager → findmyjob/staging/app → Retrieve secret value → Edit**, set real values for:

- **MONGODB_URI** – your MongoDB Atlas connection string
- **MONGODB_DB_NAME** – e.g. `findmyjob`
- **REDIS_URL** – from step 1 (e.g. `redis://findmyjob-staging-redis.xxxxx.cache.amazonaws.com:6379/0`)
- **SECRET_KEY** – at least 32 random characters
- **GOOGLE_CLIENT_ID** / **GOOGLE_CLIENT_SECRET** – from Google Cloud Console
- **GMAIL_OAUTH_REDIRECT_URI** – `https://api-staging.findmyjob.com/v1/gmail/oauth/callback` (or your staging domain)

Optional: **TOKEN_ENCRYPTION_KEY** (44-char base64), **RAZORPAY_***, **OPENAI_API_KEY**.

Leave **STORAGE_BACKEND** as `s3` only if your app supports S3; otherwise set to `local` and ensure uploads path is writable in the container.

---

## 3. Build and push Docker image

From the project root:

```bash
# Login to ECR
aws ecr get-login-password --region ap-south-1 | docker login --username AWS --password-stdin 690637085216.dkr.ecr.ap-south-1.amazonaws.com

# Build and push
docker build -t findmyjob-api:staging .
docker tag findmyjob-api:staging 690637085216.dkr.ecr.ap-south-1.amazonaws.com/findmyjob-api:staging
docker push 690637085216.dkr.ecr.ap-south-1.amazonaws.com/findmyjob-api:staging
```

After the push, ECS will pull the image and start the API and Worker tasks (may take 1–2 minutes).

---

## 4. Point your domain to the ALB (optional)

To use `https://api-staging.findmyjob.com`:

1. **ACM (Certificate Manager)**  
   Request a certificate for `api-staging.findmyjob.com` (in **us-east-1** if the ALB is in another region, then attach to the ALB in ap-south-1 via cross-region or create cert in ap-south-1). Validate via DNS.

2. **ALB listener**  
   Add an HTTPS:443 listener on the ALB with the certificate and forward to the same target group (findmyjob-staging-api-tg). Optionally remove or redirect HTTP:80.

3. **Route53**  
   Create an A record (alias) for `api-staging.findmyjob.com` pointing to the ALB:  
   `findmyjob-staging-alb-1315898380.ap-south-1.elb.amazonaws.com`

Until then, you can call the API at:

```text
http://findmyjob-staging-alb-1315898380.ap-south-1.elb.amazonaws.com
```

(e.g. `http://findmyjob-staging-alb-1315898380.ap-south-1.elb.amazonaws.com/health`)

---

## 5. Verify

- **Health:** `curl http://findmyjob-staging-alb-1315898380.ap-south-1.elb.amazonaws.com/health`
- **ECS:** In the ECS console, check cluster **findmyjob-staging-cluster** → Services → **api** and **worker** → Tasks. Tasks should be RUNNING after the image is pushed and secrets are set.
- **Logs:** CloudWatch Logs → log groups **findmyjob-staging-api**, **findmyjob-staging-worker**.

If tasks stay in PENDING or stop, check: (1) Redis is available and REDIS_URL is correct in the secret, (2) MONGODB_URI is reachable from the VPC (NAT egress or VPC peering), (3) task logs in CloudWatch for errors.
