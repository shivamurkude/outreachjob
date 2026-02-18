# CI/CD pipeline setup (GitHub → AWS staging)

This guide gets you from **no repo** to **push to main → tests run → Docker image pushed to ECR → ECS staging updated**.

---

## 1. Create a Git repository

### Option A: GitHub (recommended)

1. Go to [github.com/new](https://github.com/new).
2. Create a **new repository** (e.g. `findmyjob-backend`). Do **not** add a README, .gitignore, or license (we already have them).
3. Copy the repo URL (e.g. `https://github.com/YOUR_USER/findmyjob-backend.git`).

### Option B: GitLab / Bitbucket

Same idea: create an empty repo and use its clone URL. The workflow file is for GitHub Actions; for GitLab use `.gitlab-ci.yml`, for Bitbucket use `bitbucket-pipelines.yml` (we can add those later if you need).

---

## 2. Initialise Git and push (first time)

**Already done for you:** The repo has one commit on `main` with all code and CI/CD. The remote is set to `https://github.com/shivamurkude/Money.git`; if your repo is different, run the script below with your URL.

**Create the repo on GitHub** (if you haven’t):

1. [github.com/new](https://github.com/new) → name it (e.g. `Money` or `findmyjob-backend`) → **Create repository** (no README).
2. Copy the repo URL (e.g. `https://github.com/YOUR_USERNAME/Money.git`).

**Push from your machine:**

```bash
cd /Users/shivamurkude/Documents/Money
./scripts/push-to-github.sh https://github.com/YOUR_USERNAME/YOUR_REPO.git
```

If `origin` is already correct, just run:

```bash
./scripts/push-to-github.sh
git push -u origin main
```

After a successful push, the **Deploy to Staging** workflow runs. It will **fail** until you add AWS secrets (step 3).

---

## 3. Add GitHub secrets (required for deploy)

The workflow needs AWS credentials so it can push to ECR and update ECS.

1. In GitHub: open your repo → **Settings** → **Secrets and variables** → **Actions**.
2. Click **New repository secret** and add:

| Secret name              | Value                                      | Where to get it |
|--------------------------|--------------------------------------------|------------------|
| `AWS_ACCESS_KEY_ID`      | Your AWS access key                        | IAM → Users → your user → Security credentials → Create access key |
| `AWS_SECRET_ACCESS_KEY`  | Your AWS secret key                        | Same as above (shown once) |

**IAM permissions:** The user (or role) for this key must be allowed to:

- **ECR:** `ecr:GetAuthorizationToken` (account); and for the repo `findmyjob-api`: `ecr:BatchCheckLayerAvailability`, `ecr:GetDownloadUrlForLayer`, `ecr:BatchGetImage`, `ecr:PutImage`, `ecr:InitiateLayerUpload`, `ecr:UploadLayerPart`, `ecr:CompleteLayerUpload`.
- **ECS:** `ecs:UpdateService`, `ecs:DescribeServices`, `ecs:DescribeTaskDefinition`, `ecs:RegisterTaskDefinition` (or use managed policy `AmazonECS_FullAccess` for the cluster only).

**Easiest:** Create an IAM user **for CI only** and attach:

1. **AWS managed:** `AmazonEC2ContainerRegistryPowerUser` (ECR push/pull).
2. **Inline policy** for ECS (replace `690637085216` and `ap-south-1` if different):

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["ecs:UpdateService", "ecs:DescribeServices", "ecs:DescribeTaskDefinition"],
      "Resource": [
        "arn:aws:ecs:ap-south-1:690637085216:service/findmyjob-staging-cluster/api",
        "arn:aws:ecs:ap-south-1:690637085216:service/findmyjob-staging-cluster/worker"
      ]
    }
  ]
}
```

Then create an **Access key** for this user and put the key and secret in GitHub as above.

---

## 4. What runs when you push

| Branch    | Workflows that run |
|----------|---------------------|
| **main** | **CI** (lint + test on 3.11 and 3.12) and **Deploy to Staging** (test → build → push ECR → update ECS api + worker). |
| **develop** | **CI** only (no deploy). |
| **PR into main** | **CI** only. |

**Deploy to Staging** does:

1. **test** job: checkout → install deps → `ruff check app tests` → `pytest tests`.
2. **deploy** job (only if test passes): configure AWS → login ECR → `docker build` → push image as `:staging` and `:<git-sha>` → `aws ecs update-service --force-new-deployment` for **api** and **worker** in cluster **findmyjob-staging-cluster**.

Your ECS task definition uses the image tag **staging**, so the new image is used on the next deployment.

---

## 5. After the first successful run

- **GitHub Actions:** Repo → **Actions** → **Deploy to Staging** (or **CI**). Check the run and the **Deployment summary** step.
- **AWS:** ECS → **findmyjob-staging-cluster** → **api** / **worker** → **Tasks** should show new tasks with **RUNNING**.
- **API:**  
  `curl http://findmyjob-staging-alb-1315898380.ap-south-1.elb.amazonaws.com/health`

---

## 6. Optional: deploy only from a specific branch

To deploy only when pushing to a branch named **staging** (and keep **main** for production later):

1. In `.github/workflows/deploy-staging.yml`, change:
   ```yaml
   on:
     push:
       branches: [staging]
   ```
2. Push your code to **staging** (e.g. `git push origin staging`) to trigger the deploy.

---

## 7. Summary checklist

- [ ] Create GitHub (or other) repo.
- [ ] `git init`, `git remote add origin ...`, `git add .`, `git commit`, `git push -u origin main`.
- [ ] Add **AWS_ACCESS_KEY_ID** and **AWS_SECRET_ACCESS_KEY** in repo **Settings → Secrets and variables → Actions**.
- [ ] Push again or re-run **Deploy to Staging** from the **Actions** tab; confirm green run and ECS tasks running.
- [ ] Call staging health URL to confirm the API is up.
