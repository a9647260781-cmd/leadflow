# LeadFlow backend

FastAPI + SQLAlchemy 2 API backed by PostgreSQL. Database schema changes are managed only
through Alembic; the application does not create tables on startup.

## Local setup

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
Copy-Item .env.example .env
alembic upgrade head
python -m app.cli create-manager
uvicorn app.main:app --reload --port 8000
```

The manager command prompts for email, name, and a password of at least 12 characters. For
non-interactive deployment, pass `MANAGER_EMAIL`, `MANAGER_NAME`, and `MANAGER_PASSWORD` only
in the process environment. There is no default manager or committed password.

Every unsafe `/api` request requires an exact allowed `Origin`. `APP_ORIGIN` defaults to
`http://localhost:8080`; add Vite development with
`ADDITIONAL_ALLOWED_ORIGINS=http://127.0.0.1:5173`. An HTTP proxy should preserve the browser's
`Origin`. Set `SESSION_COOKIE_SECURE=true` behind production HTTPS.

Prefer `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, and `DB_PASSWORD`; SQLAlchemy constructs and
escapes the connection URL safely. `DATABASE_URL` is available as an explicit override.

Only set `TRUSTED_PROXY_IPS` to proxy IPs/CIDRs that replace, rather than append untrusted data
to, `X-Forwarded-For`. Forwarded headers from any other peer are ignored by rate limiting.

## Yandex AI Studio extraction

Extraction is safe to deploy before credentials exist. With `AI_ENABLED=false`, new leads get a
terminal `not_configured` state and can still be corrected manually. To enable automatic
extraction, set these only in the runtime environment:

```text
AI_ENABLED=true
YANDEX_API_KEY=<secret API key>
YANDEX_MODEL_URI=gpt://<folder-id>/yandexgpt-5.1
```

After migrations succeed, run the durable worker separately:

```powershell
python -m app.worker
```

The worker does not run migrations. It commits an atomic PostgreSQL claim before calling Yandex,
then conditionally writes the result using a lease token and revision. Retries are bounded and
manual edits fence stale jobs. Only the lead description is sent as user data; contact name and
phone are excluded. There is no production fake or regex fallback. The adapter uses Yandex's
synchronous Completion API with structured `jsonSchema`; provider data logging defaults off.

## n8n-scheduled Telegram notifications

Notifications remain disabled until every canonical runtime setting is present:

```text
NOTIFICATIONS_ENABLED=true
TELEGRAM_BOT_TOKEN=<secret bot token>
TELEGRAM_CHAT_ID=<fixed destination chat>
NOTIFICATIONS_SERVICE_TOKEN=<long random n8n-to-backend token>
NOTIFICATION_REMINDER_MINUTES=30
MANAGER_PUBLIC_URL=https://<manager-reachable-host>
```

`MANAGER_PUBLIC_URL=http://localhost:8080` is useful for the local demo, but that link only works
on the same machine; set an accessible HTTPS host for real manager notifications. No existing
leads are backfilled when notification settings are enabled later.

n8n is the only scheduler. Its two workflows call the same scoped endpoint with different kinds:

```http
POST /api/internal/notifications/dispatch
Authorization: Bearer <NOTIFICATIONS_SERVICE_TOKEN>
Content-Type: application/json

{"kind":"new_lead","limit":1}
{"kind":"reminder","limit":1}
```

The endpoint is exempt from browser `Origin` checks only on this exact path and does not accept a
manager cookie as authorization. It returns aggregate counters only. Missing/invalid service
credentials return 401; a valid service token with disabled/incomplete Telegram configuration
returns 503. n8n must not retry the HTTP call itself.

Transport behavior follows the official [Telegram Bot API](https://core.telegram.org/bots/api):
JSON `ok`/`result` responses, `message_id` audit storage, and `parameters.retry_after` for flood
control.

New-lead and reminder delivery use a durable PostgreSQL outbox. A reminder becomes eligible at
lead creation time plus the configured delay, only after the initial alert was sent, while the
lead is still `new`. Taking a lead into work permanently cancels its reminder even if the lead is
later reopened. Claims commit before Telegram I/O; timeouts, 5xx responses, and expired sending
leases become terminal `delivery_unknown` rather than risking a duplicate. Only definite
pre-connection failures and explicit 429 responses retry, with bounded attempts and delay. This is
at-most-once-oriented delivery, not an exactly-once guarantee; a status change racing an already
started Telegram request can still leave delivery unknown.

## Synthetic demo data

The backend owns an additive, repeatable demo seed with six clearly labelled Russian synthetic
leads. Names start with `Демо ·`, phone numbers use the intentionally non-contact `+7 000` range,
and no external integration is called. Extraction rows are either honestly `not_configured` or
contain a manager-authored result with `manually_edited=true`; no demo value is presented as AI
output. The seed creates no notification outbox rows.

`seed-demo` refuses to run whenever either integration enable flag is true, even if credentials
are incomplete. To override current runtime flags for this one shell operation without editing an
`.env` file, restore the caller environment immediately afterward:

```powershell
$previousAi = $env:AI_ENABLED
$previousNotifications = $env:NOTIFICATIONS_ENABLED
try {
  $env:AI_ENABLED = "false"
  $env:NOTIFICATIONS_ENABLED = "false"
  python -m app.cli seed-demo
} finally {
  $env:AI_ENABLED = $previousAi
  $env:NOTIFICATIONS_ENABLED = $previousNotifications
}
```

Successful output is `Demo seed complete: created=N existing=N`. Repeated runs create no
duplicates and do not overwrite manager changes to existing demo leads. Ownership is restricted to
the exact fixed lead UUID, submission UUID, and reserved SHA-256 demo marker. Any reserved-ID
collision aborts and rolls back the whole transaction.

Scoped cleanup requires explicit confirmation:

```powershell
python -m app.cli reset-demo --confirm
```

Successful output is `Demo reset complete: deleted=N`. Foreign-key cascades remove history and
extraction rows only for the owned fixed leads; unrelated records are never selected. Exit codes:
`0` success, `1` database failure, `2` unsafe invocation/missing confirmation, and `3` ownership
collision. Neither command changes schema or configuration files.

Fixed lead IDs for stable demo deep links:

| Scenario | Lead ID |
| --- | --- |
| Kitchen faucet | `e52d0c5e-146c-5fce-a5f7-fce7a9ab69c6` |
| Electrical outlets | `dfba17fc-3c72-5d11-99d1-e418c4829870` |
| Window adjustment | `b8953ad1-3018-5db3-901b-fabda8301535` |
| Apartment finish | `959013d5-7267-585a-9b3c-18e436906018` |
| Bathroom tile | `311b8dee-067f-5bc3-93a2-5abd80148ef9` |
| Air conditioner | `ae33186a-efae-5875-bb82-80029b4d1666` |

For an isolated extraction outage fixture, migrate the disposable database, create a
`LeadExtraction(status=pending, available_at<=now, attempts=0, revision=0)` tied to a synthetic
lead, configure only the loopback Yandex endpoint, and run the normal entrypoint:

```powershell
python -m app.worker
```

There is intentionally no second recovery worker or demo-only processing path. With AI disabled,
the normal worker converts unfinished automatic jobs to `not_configured`, so provider recovery
tests must use an isolated configured loopback fixture rather than the demo seed.

## Test

Unit tests run without a database. Integration tests deliberately require a disposable
PostgreSQL database and migrate it up/down:

```powershell
pytest
$env:TEST_DATABASE_URL = "postgresql+psycopg://leadflow:leadflow@localhost:5432/leadflow_test"
pytest
```

Never point `TEST_DATABASE_URL` at a database containing data you need; the test suite drops
the migrated schema.
