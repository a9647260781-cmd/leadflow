# Automation / n8n memory

## Ownership

`automation/n8n/` workflow exports, their focused documentation, and the offline workflow validator.

## Stable decisions

- Runtime is pinned by infrastructure to n8n 2.44.6. Workflow node versions match that tag: Schedule Trigger 1.4, HTTP Request 4.5, If 2.4, No Operation 1.
- There are two independent, inactive-by-default workflows: new-lead dispatch every 30 seconds and reminder dispatch every 60 seconds (represented as one minute because n8n seconds intervals accept only 1–59).
- Workflow timezone is `Europe/Moscow`; missed schedule executions are skipped.
- n8n calls only `POST http://backend:8000/api/internal/notifications/dispatch` with `{kind, limit: 1}`. The one-item bound, 30-second HTTP timeout, and 45-second workflow timeout accommodate the backend's bounded database/Telegram calls without allowing unbounded execution. FastAPI owns eligibility, durable outbox claims, Telegram transport, result persistence, and retry decisions.
- Internal authentication uses the shared n8n Header Auth reference `leadflow-backend-dispatch-auth` / `LeadFlow Backend Dispatch Auth`. Its value is `Authorization: Bearer <NOTIFICATIONS_SERVICE_TOKEN>` and is never embedded in an export.
- Telegram token/chat ID remain backend-only. The workflows contain no Telegram or Code nodes, customer payloads, pinned data, or fake results.
- HTTP non-2xx responses fail execution. A 200 response with `claimed: 0` is an explicit successful no-op branch. n8n HTTP retries are disabled because backend owns durable retry state.
- Successful and manual execution data is not retained. Failed execution data is redacted; its static request and response contract contains no lead data.

## Verification

- Offline contract validator: `node automation/n8n/validate-workflows.mjs`.
- n8n 2.44.6 reports the pinned version; local liveness and PostgreSQL-backed readiness both returned HTTP 200.
- A read-only PostgreSQL query after the real CLI import found both canonical workflow IDs/names inactive with exactly five nodes each.
- The validator is deliberately not described as an n8n runtime test. Infrastructure owns the isolated n8n 2.44.6 import/execution harness and rewrites only the backend host in an ignored runtime copy to reach its loopback fixture.
- End-to-end node execution and scheduled firing have not yet been claimed here; infrastructure is completing that separate runtime gate.
