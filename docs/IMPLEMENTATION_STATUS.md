# Implementation status vs plan

What is implemented and what is still missing from the original plan.

---

## Implemented

- **Phase 0:** Repo structure, config, logging (structlog), security (session, idempotency), exceptions, DB init, all Beanie models, storage (local + GCS), healthcheck, request ID middleware, CORS.
- **Phase 1:** Google Auth (ID token verify, cookie session), `POST /v1/auth/google`, `GET /v1/auth/me`, `get_current_user` dependency.
- **Phase 2:** Gmail OAuth (connect, callback, verify, disconnect), token encrypt/decrypt, refresh, Gmail profile verify.
- **Phase 3:** Credits ledger, atomic `apply_ledger_entry`, idempotency, `CreditBalance`, `/v1/credits/balance`, `/v1/credits/ledger`, pricing constants.
- **Phase 4:** Resume upload (storage + parse PDF/DOCX), free scan quota, AI analysis placeholder, `/v1/resume/upload`, `/v1/resume/analyze`, `/v1/resume/latest`.
- **Phase 5:** Lists upload (CSV/XLSX), ARQ job `process_recipient_list_upload`, `/v1/recipients/lists/upload`, list get, list items.
- **Phase 6:** Verification (syntax, MX, disposable list), single and bulk verify with credits, `/v1/verify/email`, `/v1/verify/bulk`.
- **Phase 7:** Enrichment (role-based emails), `/v1/enrich/bulk`.
- **Phase 8:** Templates CRUD, unsubscribe footer, AI generate placeholder, `/v1/templates` and `/v1/templates/generate`.
- **Phase 9:** Campaign create/list, preview, schedule (Gmail drafts, ScheduledEmail, credit charge with idempotency), `/v1/campaigns`, preview, schedule.
- **Phase 10:** `send_due_emails` cron (ARQ), Gmail API `users.drafts.send` at scheduled time, revoked Gmail handling.
- **Phase 11:** Admin system recipients import/refresh, `/v1/admin/recipients/import`, `/v1/admin/recipients/refresh`.
- **Phase 12:** Razorpay order create, webhook HMAC verify, idempotent credit apply, first-purchase bonus, `PaymentOrder` for attribution, `/v1/payments/orders`, `/v1/payments/webhook`.
- **Phase 13:** Idempotency on ledger/schedule/onboarding/payments, `FailedJob` model for DLQ, audit log helper, pagination helper, tests (health + credits), Ruff, pre-commit, CI (GitHub Actions with MongoDB).
- **Extras:** Request logging (method, path, status, duration, request_id), service/worker logging, launch.json for local run/debug, docs (SETUP, API, this status).
- **Gap fixes (implemented):**
  - **Suppression list:** `SuppressionEntry` model, `app/services/suppression.py` (add_suppression, is_suppressed, list_suppressed_emails, list_suppressions). Verification adds to suppression on invalid/disposable. Campaign preview and schedule filter recipients by suppression. Optional API: `GET/POST/DELETE /v1/suppressions`.
  - **Gmail daily cap:** Redis counters in `app/services/rate_limit.py`; `send_due_emails` enforces per-account daily cap (250), skips when at cap, increments after send.
  - **Audit log wiring:** `log_event()` called on auth login/created, Gmail connect/disconnect, campaign schedule, payment webhook, admin recipients import.
  - **RBAC for admin:** `User.role` (`"user"` | `"admin"`), `require_admin` dependency in `app/deps.py`, admin routes use `Depends(require_admin)`.
  - **Dead-letter:** ARQ job wrapper `_run_with_dlq` in `app/worker/tasks.py`; on exception persists to `FailedJob` then re-raises. Worker startup calls `init_db()`.
  - **Sentry:** `sentry_sdk.init()` in `app/main.py` startup when `SENTRY_DSN` is set.
- **LangGraph workflows:** `app/workflows/onboarding_agent.py`, `outreach_agent.py`, `verify_agent.py`, `enrich_agent.py` (StateGraph, async nodes calling existing services). `GET /v1/onboarding/status`, `GET /v1/campaigns/{id}/outreach-plan` expose onboarding and outreach agents.
- **Referral system:** `User.referral_code` (unique), `User.referred_by` (Link). Service: get_or_create_referral_code, apply_referral_code, grant_referral_reward_if_eligible (on first purchase or schedule), referral_stats. `GET/POST /v1/referrals/me`, `POST /v1/referrals/apply`, `GET /v1/referrals/stats`. Reward: 25 credits per referred user (idempotent).

---

## Not implemented (gaps)

1. **Prometheus metrics**
   - Plan: “prometheus-client (optional)”.
   - Missing: No `/metrics` or Prometheus instrumentation. Optional for production.

---

## Summary

Core flows, gap fixes, LangGraph workflows (onboarding, outreach, verify, enrich), and referral system are implemented. Remaining optional: Prometheus metrics.
