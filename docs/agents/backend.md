# Backend assistant memory

## Ownership and stack

- Backend source lives in `backend/` and uses Python 3.12, FastAPI, SQLAlchemy 2, psycopg 3,
  Alembic, PostgreSQL, Pydantic Settings, and pwdlib Argon2.
- Start: from `backend/`, run `uvicorn app.main:app --host 0.0.0.0 --port 8000`.
- Migrate: `alembic upgrade head`.
- Create manager: `python -m app.cli create-manager` (interactive) or pass `MANAGER_EMAIL`,
  `MANAGER_NAME`, and `MANAGER_PASSWORD` in the process environment. Never commit credentials.

## Stable decisions

- All routes use `/api`. Statuses are `new`, `in_progress`, `won`, and `lost`.
- Public submission uses a client UUID plus a canonical payload hash. PostgreSQL uniqueness and
  `ON CONFLICT DO NOTHING` make identical retries return 200 and changed-payload reuse return 409.
- Manager passwords use Argon2. Auth uses a random opaque HttpOnly cookie while only SHA-256 of
  the token is stored. Sessions have DB expiry and revocation; logout revokes then clears cookie.
- Every unsafe API request, including login and public submission, requires an exact configured
  Origin. Browser CORS uses the same allowlist. Same-origin `/api` proxying is preferred.
- Login and public submission have in-process IP limits for the single-process MVP. Forwarded IP
  is accepted only from explicit `TRUSTED_PROXY_IPS`; multi-instance deployment needs Redis/etc.
- List/detail/status mutation are authenticated. Lead creation returns only ID and creation time.
- Status changes lock the lead row and append history in the same transaction.
- Yandex extraction uses a durable one-row-per-lead PostgreSQL queue. New configured leads are
  `pending`, unconfigured leads are `not_configured`, and pre-migration leads are
  `not_requested` without automatic backfill.
- Claims use `FOR UPDATE SKIP LOCKED`, leases, bounded exponential retries, and claim-token plus
  revision fencing. The claim commits before provider I/O. Manual writes increment the revision,
  clear the claim, and cannot be overwritten by stale work.
- Manual PATCH requires `expected_revision`; stale tabs or drafts opened before worker completion
  receive 409. Successful worker completion also increments revision.
- Only description is provider user data. The adapter uses Yandex synchronous Completion with
  `jsonSchema`, no tools, disabled reasoning, exact evidence checks, and safe error codes. It
  accepts both documented bare and `result.alternatives` response envelopes. There is no
  production fake fallback.
- Supported budget currencies are RUB, USD, and EUR. PostgreSQL `numeric(16,2)` is exact; excess
  precision/range is rejected rather than silently rounded. Numeric amount, explicit currency,
  range, and lower/upper direction are deterministically checked against the verbatim quote;
  this is validation, not a heuristic extraction fallback or a claim of semantic perfection.
- A disabled worker converts unfinished pending/processing jobs to stable `not_configured`, keeps
  existing values/manual provenance, and increments revision to fence active work. Configured
  workers recover from transient SQLAlchemy failures with sanitized logs and capped backoff.
- Telegram delivery is a PostgreSQL outbox scheduled only by two n8n workflows. Configured new
  leads atomically receive unique `new_lead` and `reminder` rows; disabled leads and old leads are
  never backfilled. The initial alert is independent of AI.
- Reminders are due from lead creation time, require a sent initial alert, and require the lead to
  remain `new`. The first transition out of `new` permanently cancels the reminder, including if
  the lead is later reopened.
- Dispatch locks the lead before its notification row, commits `sending` before Telegram I/O, and
  fences completion by claim token. Expired/ambiguous sends become terminal `delivery_unknown`;
  only pre-connection failures and explicit 429 responses retry with bounded attempts. Delivery
  is intentionally not described as exactly once.
- Telegram messages are unformatted plain text with lead UUID, name, a 500-character description,
  and the authenticated manager URL. Phone/passwords are excluded. The fixed chat and bot token
  come only from trusted runtime settings, and httpx request-URL INFO logging is suppressed because
  Telegram embeds the bot token in its API path.
- Demo data is backend-owned and schema-free. `python -m app.cli seed-demo` adds six fixed-UUID,
  explicitly labelled synthetic Russian leads under a PostgreSQL advisory transaction lock. It
  refuses to run while either integration enable flag is true, performs no external calls, creates
  no outbox rows, and never overwrites an existing owned demo lead.
- Demo ownership requires an exact fixed lead UUID, fixed submission UUID, and reserved SHA-256
  marker. Any collision aborts the transaction. `python -m app.cli reset-demo --confirm` deletes
  only records passing that ownership check; history/extraction cleanup uses their existing FK
  cascades and unrelated rows remain untouched.
- Demo extraction is either honestly `not_configured` or a manager-authored `succeeded` result
  with `manually_edited=true`, revision 1, and evidence copied exactly from the description. No
  seeded value is represented as Yandex output.

## Configuration

Prefer `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, and `DB_PASSWORD`; `DATABASE_URL` optionally
overrides all five. `DB_CONNECT_TIMEOUT_SECONDS` bounds psycopg connection establishment so the
worker returns to its retry loop after network failure. Other settings: `APP_ORIGIN`,
`ADDITIONAL_ALLOWED_ORIGINS`, `TRUSTED_PROXY_IPS`,
`SESSION_COOKIE_SECURE`, `SESSION_COOKIE_SAMESITE`, `SESSION_TTL_HOURS`,
`SESSION_COOKIE_NAME`, `LOGIN_RATE_LIMIT`, `PUBLIC_LEAD_RATE_LIMIT`, and
`RATE_LIMIT_WINDOW_SECONDS`. Defaults are development-safe; set secure cookies under HTTPS.

AI settings: `AI_ENABLED`, `YANDEX_API_KEY`, and full `YANDEX_MODEL_URI` are canonical. Optional:
`YANDEX_API_URL`, `YANDEX_DATA_LOGGING_ENABLED`, `EXTRACTION_POLL_INTERVAL_SECONDS`,
`EXTRACTION_REQUEST_TIMEOUT_SECONDS`, `EXTRACTION_MAX_ATTEMPTS`, `EXTRACTION_LEASE_SECONDS`,
`EXTRACTION_RETRY_BASE_SECONDS`, and `EXTRACTION_RETRY_RATE_LIMIT`. The separate
`python -m app.worker` process depends on completed migrations and does not migrate itself.

Notification settings: `NOTIFICATIONS_ENABLED`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`,
`NOTIFICATIONS_SERVICE_TOKEN`, `NOTIFICATION_REMINDER_MINUTES` (default 30), and
`MANAGER_PUBLIC_URL` (local default `http://localhost:8080`). Optional bounds:
`TELEGRAM_API_BASE_URL` (official HTTPS default; override only for a controlled fixture),
`NOTIFICATION_REQUEST_TIMEOUT_SECONDS`, `NOTIFICATION_LEASE_SECONDS`,
`NOTIFICATION_MAX_ATTEMPTS`, `NOTIFICATION_RETRY_BASE_SECONDS`, and
`NOTIFICATION_RETRY_CAP_SECONDS`.

Internal API: `POST /api/internal/notifications/dispatch` with scoped Bearer authentication and
body `{"kind":"new_lead"|"reminder","limit":1}`. Limit defaults to 1 and accepts 1..20; n8n uses
1. Response is only `{kind,claimed,sent,retried,failed,delivery_unknown,skipped}`. Invalid auth is
401; valid service auth with disabled/incomplete Telegram configuration is 503. This exact route
is exempt from browser Origin enforcement; it has no manager-data read surface.

Demo CLI: temporarily set `AI_ENABLED=false` and `NOTIFICATIONS_ENABLED=false` only in the seed
process, then run `python -m app.cli seed-demo`. Output is
`Demo seed complete: created=N existing=N`. Reset is
`python -m app.cli reset-demo --confirm`, output `Demo reset complete: deleted=N`. Exit codes are
0 success, 1 database failure, 2 unsafe invocation/missing confirmation, and 3 ownership collision.
The full fixed-ID list and a PowerShell environment-restore example are in `backend/README.md`.

## Verification state

- Unit/security and PostgreSQL integration tests are under `backend/tests`.
- Ruff, import/OpenAPI generation, and compileall pass locally.
- Full test suite passes against a dedicated PostgreSQL 17.11 database: 54 passed. It includes
  migration downgrade/upgrade, auth, Origin enforcement, session revocation and expiry,
  idempotency/replay/conflict (including a concurrent retry), protected cabinet/history,
  special-character DB password encoding, and trusted/untrusted proxy IP handling.
- Extraction coverage includes 20 varied offline provider fixtures through `httpx.MockTransport`,
  request minimization, evidence/precision validation, timeout/429/5xx retry classification,
  permanent 401/403 handling, atomic claims, stale/manual fencing, lease recovery, protected
  manual/retry APIs, configured/unconfigured enqueue behavior, and old-data migration.
- Budget grounding normalizes all Unicode whitespace captured inside numbers (including narrow
  non-breaking space U+202F); Decimal conversion failures become safe retryable provider errors.
- Live Yandex calls and model accuracy are intentionally unverified because the user chose to
  prepare without a key. Production truthfully reports `not_configured`.
- PostgreSQL integration tests require disposable `TEST_DATABASE_URL` and migrate it down/up.
- Notification coverage includes no-backfill migration, submission deduplication, concurrent
  dispatch claims, exact reminder timing, initial-alert prerequisite, permanent cancellation,
  status/claim fencing, bounded 429 and connect retries, permanent 401/403 failure, ambiguous
  timeout/5xx behavior, stale-lease recovery, scoped API auth, and aggregate-only responses.
- Telegram transport tests use `httpx.MockTransport`; no real bot or chat is configured and no
  live Telegram message has been sent.
- Demo tests on real PostgreSQL cover first/repeated seed, preservation of manager edits, exact
  manual provenance/evidence, zero notification rows, scoped reset preserving an unrelated lead,
  and rollback on reserved-ID collision. Direct CLI smoke verified created `6/0`, repeated `0/6`,
  unconfirmed reset exit 2, confirmed deletion of 6, and integration-enabled refusal exit 2.
- With frontend approval, the shared local demo database was seeded additively using process-only
  disabled integration flags. First/repeat results were `created=6 existing=0` then
  `created=0 existing=6`; verification showed 14 total leads, 6 demo leads, 4 manual extraction
  rows, 2 `not_configured` rows, and zero demo outbox rows. The 8 pre-existing leads remained;
  shared reset was not run and runtime environment files were not changed.
