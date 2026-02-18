# Staging Secrets Manager – checklist and next steps

Use this to confirm **findmyjob/staging/app** is correct and what to do next.

---

## 1. Verify keys (no values shown)

From the project root run:

```bash
chmod +x scripts/verify-staging-secret.sh
./scripts/verify-staging-secret.sh
```

This checks that every key ECS expects exists in the secret and does a minimal length check on important fields. It does **not** print secret values.

---

## 2. Required keys and what they should be

| Key | Required | Format / rules |
|-----|----------|-----------------|
| **MONGODB_URI** | Yes | Full Atlas URI, e.g. `mongodb+srv://user:pass@cluster....mongodb.net/` |
| **MONGODB_DB_NAME** | Yes | Database name, e.g. `findmyjob` |
| **REDIS_URL** | Yes | `redis://findmyjob-staging-redis.bj8btl.0001.aps1.cache.amazonaws.com:6379/0` (no trailing slash) |
| **SECRET_KEY** | Yes | At least 32 characters (random string for sessions) |
| **GOOGLE_CLIENT_ID** | Yes for auth/Gmail | From Google Cloud Console OAuth client |
| **GOOGLE_CLIENT_SECRET** | Yes for auth/Gmail | From same OAuth client |
| **GMAIL_OAUTH_REDIRECT_URI** | Yes for Gmail OAuth | Must **exactly** match the redirect URI in Google Console, e.g. `https://api-staging.findmyjob.com/v1/gmail/oauth/callback` or `http://findmyjob-staging-alb-....elb.amazonaws.com/v1/gmail/oauth/callback` |
| **TOKEN_ENCRYPTION_KEY** | No | Empty string OK (key derived from SECRET_KEY); or 44-char base64 Fernet key |
| **RAZORPAY_KEY_ID** | No (for payments) | Can be empty if not using payments yet |
| **RAZORPAY_KEY_SECRET** | No | Can be empty |
| **RAZORPAY_WEBHOOK_SECRET** | No | Can be empty |
| **OPENAI_API_KEY** | No | Can be empty |
| **STORAGE_BACKEND** | Yes | Use `local` for now (app uses local/GCS in code). If you use `s3`, the app must support it. |
| **CORS_ORIGINS** | Yes | Comma-separated origins, e.g. `https://api-staging.findmyjob.com,http://localhost:3000` |

**Common mistakes**

- **GMAIL_OAUTH_REDIRECT_URI** different from the URI in Google Cloud Console → OAuth will fail.
- **REDIS_URL** with `https://` or missing `/0` → use `redis://host:6379/0`.
- **MONGODB_URI** missing database name or options → e.g. `...mongodb.net/` or `...mongodb.net/?retryWrites=true`.
- **SECRET_KEY** shorter than 32 chars → session/security issues.

---

## 3. Next steps after secrets are correct

1. **Run the verification script** (step 1 above). Fix any missing or wrong keys in Secrets Manager.

2. **Build and push the Docker image** (if not done yet):
   ```bash
   aws ecr get-login-password --region ap-south-1 | docker login --username AWS --password-stdin 690637085216.dkr.ecr.ap-south-1.amazonaws.com
   docker build -t findmyjob-api:staging .
   docker tag findmyjob-api:staging 690637085216.dkr.ecr.ap-south-1.amazonaws.com/findmyjob-api:staging
   docker push 690637085216.dkr.ecr.ap-south-1.amazonaws.com/findmyjob-api:staging
   ```

3. **Wait for ECS** (1–2 minutes). In AWS Console: ECS → cluster **findmyjob-staging-cluster** → Services → **api** and **worker** → Tasks. Status should become RUNNING.

4. **Hit the API**:
   ```bash
   curl http://findmyjob-staging-alb-1315898380.ap-south-1.elb.amazonaws.com/health
   ```
   You should get a 200 response.

5. **If tasks fail**: CloudWatch Logs → **findmyjob-staging-api** and **findmyjob-staging-worker**. Look for connection errors (Mongo, Redis) or missing env.

6. **Optional – custom domain**: Add Route53 A record for `api-staging.findmyjob.com` (alias to the ALB). Add HTTPS listener on the ALB with an ACM certificate for that domain.

---

## 4. Summary

- **Check:** Run `./scripts/verify-staging-secret.sh` to confirm all keys exist and lengths are sane.
- **Fix:** In Secrets Manager, add or correct any key from the table above.
- **Then:** Build/push image → check ECS tasks → call `/health` → check logs if something fails.
