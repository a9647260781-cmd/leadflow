# LeadFlow — final pre-publication review

Date: 2026-10-25. Reviewer: GPT-6 Astra (`/root/final_reviewer`).

The owner explicitly authorized this final review and instructed the team not to publish. Scope is the current local portfolio package: application, scripts, deployment configuration, case and screenshots. Git has no HEAD, staging or remote, so this is a source-tree review rather than a commit diff. Older entries in the reviewer memory are historical evidence, not approval of this candidate.

## Verdict

**Passed for the local portfolio package.** Both actionable P2 findings were corrected and rechecked; no remaining actionable P0/P1/P2 finding was identified in the reviewed scope. No publication, staging, commit, remote creation or deployment is authorized by this report. The hosting/live-provider limitations below remain explicit.

## Findings

### F1 — P2: fixture harnesses contaminate the calling PowerShell environment

The original `scripts/run-ai-mock-integration.ps1` lines 54–68 set process environment variables including `DATABASE_URL`, `AI_ENABLED`, fixture credentials and `YANDEX_API_URL`; its finalizer at lines 118–120 only stops processes. The notification and recovery harnesses have the same lifetime problem. Ordinary PowerShell script invocation shares process environment with its caller.

Reproduction path: run a documented QA harness in a PowerShell session, then cold-start the local demo in that same session. `start-local-demo.ps1` loads `local.env`, which resets database/origin/cookie settings but not AI provider variables. With no `ai.env`, the app therefore inherits enabled fixture AI configuration and sends new jobs to the stopped loopback fixture instead of showing `not_configured`. Even a real `ai.env` containing only the documented key/model settings retains the fixture API URL. Early harness failure can leave the same contamination.

Requested fix: isolate all three harnesses in child processes, or restore every environment mutation in an outer finalizer, including failures before the old cleanup block. Verify preservation of existing values and absence of newly introduced variables after success and failure. This is a local reproducibility blocker; it does not require live providers or hosting to reproduce.

### F2 — P2: AI integration harness assumes its dedicated database already exists

The original `scripts/run-ai-mock-integration.ps1` declares `leadflow_test_ai_integration` at line 10, changes the connection URL at line 54 and runs `alembic downgrade base` at line 73, without creating that database. The documented fresh Windows setup and `portable-postgres.ps1` create only the main `leadflow` database. Consequently the documented AI QA command fails with a missing-database error on a fresh setup, before starting its fixture; existing evidence depended on a previously provisioned test database.

Requested fix: bootstrap/verify the exact dedicated loopback test database before migrations, with explicit target guards, and verify the path when that test database is initially absent. Never reset the shared application database.

## Fix recheck and closure

- **F1 resolved:** all three ordinary script entry points now launch a child PowerShell process before any environment mutation and propagate a nonzero child result as failure. Independent source inspection confirms both normal completion and early failure are isolated. Reviewer ran `tests\test-harness-env-isolation.ps1`: **PASS** for all three harnesses after successful probes and injected failures, comparing the complete parent environment without printing values.
- **F2 resolved:** the AI harness now queries/creates the fixed `leadflow_test_ai_integration` database on loopback port `55432` and verifies `current_database()` before migrations. Infrastructure removed only that exact disposable database, then ran `powershell -NoProfile -NonInteractive -File .\scripts\run-ai-mock-integration.ps1`: **PASS**, absent database recreated and full loopback fixture integration completed. Main lead count remained **14 → 14**, shared API health remained `ok`, and parent environment remained unchanged. This execution is owner-run terminal evidence, not an independently rerun reviewer integration test or a persisted log artifact.
- Reviewer reran `scripts\check-repository.ps1` after the script fixes, regression and report: **PASS for 131 candidate files**. Infra owns final status-document synchronization and a final hygiene rerun after those documentation edits.

## Independent checks performed

- Read auth/session hashing and expiry, Origin enforcement, trusted proxy handling, public idempotency, manager routes, extraction schema/provider/queue/worker/revision fencing, notification outbox/transport/dispatch, migrations, seed/reset ownership, frontend auth/polling/conflicts, startup scripts, Compose/nginx, workflow exports, recovery assertions and portfolio documentation.
- From `backend/`: `..\.runtime\venv\Scripts\python.exe -m pytest -q tests/test_security.py tests/test_worker.py tests/test_extraction_provider.py tests/test_notifications.py` — **32 passed**. Offline transports; no shared database reset or external provider calls.
- From `frontend/`: `npm test` — **24 passed** across six files; `npm run build` — passed, **1604 modules**.
- From repository root: `node automation/n8n/validate-workflows.mjs` — two workflows valid; `scripts\check-repository.ps1` — passed for the original **129** Git-visible candidate files before this report/fixes were added. This is a heuristic hygiene check, not a guarantee that secrets cannot exist.
- Independently opened all five curated images, including public mobile `390×844`, no-key extraction mobile `390×844`, and manual extraction desktop, plus raw conflict-preserved and narrow keyboard-focus screenshots. Text/actions are readable without visible horizontal clipping; the manual result is explicitly labeled as seeded manual data.
- Inspected recovery test assertions and existing ignored PASS logs for processing, recovery after outage/lease expiry, app restore and n8n workflow metadata restore. Did not rerun the outage drill during this review.

## Fresh owner-run evidence requested by reviewer

Infra ran the full backend suite with process-only `TEST_DATABASE_URL` targeting the exact disposable database `leadflow_test_final_review`: `..\.runtime\venv\Scripts\python.exe -m pytest -q` — **54 passed**, one Starlette/httpx deprecation warning. The disposable database was removed afterward; shared application lead count remained **14 before and after**. Tests cover authorization/Origin, public-to-manager flow, logout/expiry, concurrent submissions, migrations, claim/revision fencing, bounded retry, notification cancellation/ambiguity and seed/reset scope.

Earlier developer/integration evidence in [HANDOFF](HANDOFF.md) covers real-browser submit/login/search/status/manual conflict/logout guards, keyboard focus and narrow UI, isolated AI and n8n fixture pipelines, actual PostgreSQL outage recovery, and app/n8n backup/restore with restart persistence. Those workflows are supporting historical evidence, not claimed as newly executed by this reviewer.

## Limits and publication boundary

- No live Yandex or Telegram call was made. Fixture success does not establish live model accuracy, account configuration or delivery availability. Only the description is sent to AI; contacts written inside that description would also be sent.
- Notification claims and terminal `delivery_unknown` handling do not promise exactly-once external delivery. A status change racing an already-started request cannot guarantee cancellation at Telegram.
- Docker was unavailable. Compose/nginx received source review; clean container startup remains unverified. Public hosting/HTTPS is outside this local portfolio verdict.
- Native Chrome text zoom at 200% and screen-reader audit remain unverified; earlier deterministic reflow coverage is not a substitute.
- License/asset-rights decisions, final staged-content/secret review and explicit publication permission remain separate publication steps. No Git history exists to scan yet.
