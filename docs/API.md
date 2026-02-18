# API reference (v1)

Base URL: `http://localhost:8000` (or your host).

All authenticated endpoints require the session cookie set by `POST /v1/auth/google`. Send credentials (cookies) with each request.

---

## Auth

| Method | Path | Description |
|--------|------|-------------|
| POST | `/v1/auth/google` | Body: `{"id_token": "..."}`. Verifies Google ID token, creates/updates user, sets httpOnly session cookie. |
| GET | `/v1/auth/me` | Returns current user (requires cookie). |

---

## Gmail

| Method | Path | Description |
|--------|------|-------------|
| GET | `/v1/gmail/connect` | Returns `authorization_url` for Google OAuth. Optional query: `redirect_uri`. |
| GET | `/v1/gmail/oauth/callback` | Callback for Google OAuth (`code`, `state`, optional `redirect`). Exchange code and store tokens. |
| POST | `/v1/gmail/verify` | Verifies stored Gmail token (calls Gmail profile). |
| DELETE | `/v1/gmail/disconnect` | Revokes Gmail connection for current user. |

---

## Credits

| Method | Path | Description |
|--------|------|-------------|
| GET | `/v1/credits/balance` | Returns `{"balance": <int>}`. |
| GET | `/v1/credits/ledger` | Query: `limit`, `offset`. Returns ledger entries (newest first). |

---

## Resume

| Method | Path | Description |
|--------|------|-------------|
| POST | `/v1/resume/upload` | Form: `file` (PDF/DOCX). Uploads and parses; returns doc id and extracted fields. |
| POST | `/v1/resume/analyze` | Body: optional `resume_id`. Runs AI analysis; uses free quota then charges credits. |
| GET | `/v1/resume/latest` | Returns latest resume document for current user. |

---

## Recipients (lists)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/v1/recipients/lists/upload` | Form: `file` (CSV/XLSX), optional `name`. Creates list and enqueues processing. |
| GET | `/v1/recipients/lists/{list_id}` | Returns list metadata and counts. |
| GET | `/v1/recipients/lists/{list_id}/items` | Query: `limit`, `offset`. Returns recipient items. |

---

## Verify

| Method | Path | Description |
|--------|------|-------------|
| POST | `/v1/verify/email` | Body: `{"email": "...", "recipient_item_id": null}`. Single email verify (1 credit). |
| POST | `/v1/verify/bulk` | Body: `{"emails": [...], "idempotency_key": null}`. Optional header: `Idempotency-Key`. Charges upfront. |

---

## Enrich

| Method | Path | Description |
|--------|------|-------------|
| POST | `/v1/enrich/bulk` | Body: `{"recipient_item_ids": ["..."]}`. Role-based email enrichment (careers@, hr@, etc.). |

---

## Suppressions

| Method | Path | Description |
|--------|------|-------------|
| GET | `/v1/suppressions` | Query: `limit`, `offset`. List current user's suppression entries. |
| POST | `/v1/suppressions` | Body: `{"email": "..."}`. Add email to user's suppression list (manual). |
| DELETE | `/v1/suppressions` | Query: `email=...`. Remove email from user's suppression list. |

Invalid/disposable results from verification are automatically added to the user's suppression list. Campaign scheduling excludes suppressed emails (global + per-user).

---

## Templates

| Method | Path | Description |
|--------|------|-------------|
| GET | `/v1/templates` | List templates. |
| POST | `/v1/templates` | Body: `name`, `subject`, `body_html`, `body_text?`, `unsubscribe_footer?`. Create. |
| GET | `/v1/templates/{template_id}` | Get one template. |
| PUT | `/v1/templates/{template_id}` | Update (partial). |
| DELETE | `/v1/templates/{template_id}` | Delete. |
| POST | `/v1/templates/generate` | Body: `job_title`, `resume_profile_summary?`. Returns generated subject/body (placeholder AI). |

---

## Campaigns

| Method | Path | Description |
|--------|------|-------------|
| GET | `/v1/campaigns` | List campaigns. |
| POST | `/v1/campaigns` | Body: `name`, `template_id`, `recipient_source`, `recipient_list_id?`. Create. |
| GET | `/v1/campaigns/{id}/preview` | Recipient count and credit estimate. |
| GET | `/v1/campaigns/{id}/outreach-plan` | Outreach agent: schedule_plan and credits_required (suppression applied). |
| POST | `/v1/campaigns/{id}/schedule` | Creates Gmail drafts, ScheduledEmail records, charges credits. Optional header: `Idempotency-Key`. |

---

## Payments

| Method | Path | Description |
|--------|------|-------------|
| POST | `/v1/payments/orders` | Body: `{"amount_paise": 25000, "currency": "INR"}`. Creates Razorpay order; returns `order_id`, `key_id`. |
| POST | `/v1/payments/webhook` | Razorpay webhook (signature in `X-Razorpay-Signature`). Idempotent credit apply. |

---

## Admin

| Method | Path | Description |
|--------|------|-------------|
| POST | `/v1/admin/recipients/import` | Form: `file` (CSV). Import system recipients. (RBAC stub.) |
| POST | `/v1/admin/recipients/refresh` | Trigger system recipients refresh. |

---

## Onboarding

| Method | Path | Description |
|--------|------|-------------|
| GET | `/v1/onboarding/status` | Onboarding agent: next_step, has_gmail, has_list, has_template. |
| POST | `/v1/onboarding/complete` | Grant onboarding bonus credits once per user (idempotent). |

---

## Referrals

| Method | Path | Description |
|--------|------|-------------|
| GET | `/v1/referrals/me` | Get or create my referral code. |
| POST | `/v1/referrals/apply` | Body: `{"code": "..."}`. Apply referral code (set referred_by). |
| GET | `/v1/referrals/stats` | referred_count, total_referral_credits. |

Referrer earns 25 credits when a referred user completes first purchase or first campaign schedule (once per referee).

---

## Health

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Returns `{"status": "ok"}`. No auth. |

---

## Errors

Responses use a consistent shape:

```json
{
  "error": {
    "message": "Human-readable message",
    "code": "ERROR_CODE",
    "details": {}
  },
  "request_id": "uuid"
}
```

Common codes: `UNAUTHORIZED`, `FORBIDDEN`, `NOT_FOUND`, `BAD_REQUEST`, `CONFLICT`, `VALIDATION_ERROR`, `INTERNAL_ERROR`.
