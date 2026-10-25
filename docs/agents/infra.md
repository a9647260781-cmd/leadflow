# Infra / QA memory

## Ownership

Root deployment files, `docker/`, integration scripts/tests, Russian setup documentation, and end-to-end verification.

## Stable decisions

- Compose exposes only nginx on `localhost:8080`; PostgreSQL and FastAPI stay on the internal network.
- PostgreSQL data uses the named `postgres_data` volume.
- Backend waits for healthy PostgreSQL, runs `alembic upgrade head`, then starts Uvicorn.
- Nginx serves the Vite SPA and proxies `/api/` to backend without rewriting the path.
- Nginx replaces (does not append) `X-Forwarded-For`; backend trusts only nginx's fixed Compose IP `172.30.0.10`.
- Compose passes database credentials as separate DB component variables so reserved URL characters remain valid.
- `.env` is ignored. `.env.example` contains placeholders only.
- No SQLite fallback is permitted. When Docker is absent, QA may use project-local PostgreSQL binaries under ignored `.runtime/` without installing a Windows service.
- Optional Yandex extraction uses only `AI_ENABLED`, `YANDEX_API_KEY`, and `YANDEX_MODEL_URI` as the canonical enablement contract. `.runtime/ai.env` is ignored and may keep blank placeholders; no secret may be printed or committed.
- The extraction worker is a separate process. Compose starts it after backend health; the Windows launcher runs migrations, waits for backend health, then starts/tracks worker and frontend.
- Notification automation pins n8n 2.44.6. Compose keeps it in the optional `notifications` profile with its own PostgreSQL service/user/database and persistent data/encryption key. n8n calls only the guarded backend dispatch endpoint; backend owns the durable outbox and Telegram delivery.
- Independent GPT-6 Astra final pre-publication review was explicitly authorized and completed once for the local portfolio package. Developer checks and functional QA continue without per-feature review gates; the later public-source authorization was obtained separately.

## Initial environment (2026-10-24)

- Windows, PowerShell; Node 20.19.0; npm 10.8.2; Python 3.12.2; Git 2.53.0.
- Docker/Compose and PostgreSQL executables were not initially installed or on PATH.
- Chrome and Edge are installed. Ports 5173, 8000, 8080, and 5432 had no detected listener at the initial check.
- Official EDB PostgreSQL 17.11 portable binaries are used for local QA. Because PostgreSQL's Windows bootstrap cannot initialize below the repository's Cyrillic path, binaries/data live per-project at `%LOCALAPPDATA%\LeadFlowRuntime`; no Windows service is installed. Ignored secrets/config remain in repository `.runtime/`.

## Verified 2026-10-24

- Real PostgreSQL 17.11: backend migration/integration suite `10 passed`; persistence survived server stop/start.
- Frontend: `13 passed`, production build succeeded.
- API smoke: unauthorized, Origin enforcement, idempotency, login, list, detail, status history, logout passed.
- Chrome E2E: submit → login → list/search/filter → detail → status/history → logout → route guard → detail return path passed.
- Failed logout with backend offline kept the manager in the cabinet and displayed a retry action; normal logout passed after recovery.
- 390×844 detail screenshots inspected: readable, no clipping; localized history confirmed in `artifacts/lead-detail-history-narrow.png`.
- Compose/nginx/backend proxy and credential fixes passed independent static review. Docker execution remains unverified because Docker is absent.

## Redesign browser QA (2026-10-24)

- Product Design source truth: `docs/design/reference-service-docket.png`, `1487×1058` px at 96 DPI.
- Final public implementation capture: CSS/client viewport `1487×1058`, DPR 1, fonts loaded, document `scrollHeight=1058` with no desktop scrollbar; `artifacts/redesign-qa/public-desktop-1487x1058-final.png`.
- Final combined comparison (source left, implementation right): `artifacts/redesign-qa/comparison-final-source-left-current-right.png`.
- Exact `390×844` captures: public, login, manager list, and detail in `artifacts/redesign-qa/`. Detail was additionally checked at `320×844`.
- Browser flow passed on real PostgreSQL: public submit, login, list search/filter/empty state, detail, status/history, logout, protected route guard, and direct-route return after login.
- At 390 px, the detail page and UUID line have no horizontal overflow; at 320 px, page/body width stays within the viewport and the UUID control reports equal client/scroll widths.
- Clean final-tab browser console warning/error list was empty. IAB was unavailable, so the authorized Chrome fallback was used through CUA browser controls. Earlier comparison iterations remain in `artifacts/redesign-qa/` for the design-QA history.
- Independent `design-qa.md` final result is `passed` after three comparison iterations with no remaining P0/P1/P2 findings. Residual P3 differences and tablet/zoom/screen-reader coverage gaps are documented there.

## Yandex extraction QA (2026-10-24)

- Credentials intentionally absent by user choice. `.runtime/ai.env` exists with blank key/model placeholders; no live Yandex request was made and model quality is unverified.
- Backend reports PostgreSQL 17.11 suite `38 passed` and Ruff clean. Current frontend reports `24 passed` and a successful production build. Independent focused provider/worker review tests passed.
- `scripts/run-ai-mock-integration.ps1` passed on dedicated `leadflow_test_ai_integration` and cleaned ports 18000/18081. It covers pending, transient retry, official response envelope, structured fields/evidence, auth/Origin, manual revision/protection, explicit overwrite rerun, permanent failure and retry. The fixture is loopback-only and is not production behavior or model-quality evidence.
- Main database migration preserved five old leads as `not_requested`. A new browser-created lead became `not_configured`; connection check showed the safe Russian explanation. Manual service/budget/timeframe saved with revision protection and survived reload plus full app/PostgreSQL restart.
- Local demo repeat-start is idempotent and currently tracks healthy backend, idle no-key worker, and frontend behind `http://localhost:8080`.
- At the original AI stage, the first database-outage harness hung before creating its recovery lead. That historical gap was closed by the later isolated recovery drill recorded below; only the later result is live outage evidence.
- At the original AI stage, no exact 390×844 AI-panel screenshot was produced. That historical visual gap was closed by the later exact DPR 1 capture recorded below.

## Telegram / n8n QA (2026-10-25)

- User chose prepare-without-bot. `.runtime/notifications.env` has blank bot/chat fields and nonprinted random service-token, n8n DB password and encryption key. Main backend reports notifications disabled; valid service auth returns 503 and no Telegram call occurs.
- Docker remains unavailable. Official portable Node 24.22.1 was downloaded and SHA-256 verified against nodejs.org; project-local n8n 2.44.6 CLI reports the pinned version. Node 20.19 matched the docs' broad range but the 2.44.6 package itself requires Node >=24, so runtime uses portable Node 24.
- n8n metadata lives in separate PostgreSQL databases under the dedicated `leadflow_n8n` role. Main readiness `/healthz/readiness` returns 200; repeat start is idempotent; the two canonical workflows and Header Auth credential imported successfully and workflows remain inactive.
- `scripts/run-notification-n8n-integration.ps1` passed against dedicated backend/n8n databases and loopback Telegram. Real n8n CLI executions covered service-token auth, idempotent outbox, new lead, due reminder, cancellation/reopen, 429 retry then success, and timeout delivery-unknown without resend. An active test n8n server also executed both 30-second and one-minute schedules.
- Main migration `20261025_0003` preserved existing leads. Backend health and the prior API smoke remained green. No live Telegram message was sent and no bot delivery claim is made.
- Start prepared inactive n8n: `scripts/start-local-n8n.ps1`. Stop it: `scripts/stop-local-n8n.ps1`. After securely filling bot/chat and setting `NOTIFICATIONS_ENABLED=true`, run `scripts/enable-local-notifications.ps1`. No tunnel is created; localhost manager links do not work from a phone.

## Portfolio release inventory (2026-10-25)

- Added `docs/RELEASE_CHECKLIST.md` as the ordered source of truth for work remaining before a portfolio release; `docs/HANDOFF.md` links to it.
- This inventory did not rerun tests, restart services, invoke the independent reviewer, create commits, configure a remote, deploy or publish anything.
- Git metadata at inventory time: branch `main`, no valid `HEAD`, 0 commits, no remote names and 16 untracked top-level entries. `.env`, `.runtime/` and `node_modules/` are covered by `.gitignore`.
- Principal open gates are a target/release-mode decision, a credentials-safe initial commit, clean deployment on the chosen target, production HTTPS/origin/cookie/proxy configuration, demo-data cleanup, backup/restore and live worker-outage verification, and a final mobile/keyboard regression.
- Live Yandex and Telegram are conditional gates: credentials and measured live acceptance are required only if the portfolio claims those integrations are connected. Otherwise they remain deliberately disabled and described as prepared/tested with isolated fixtures.
- GPT-6 Astra remains reserved for one final pre-publication review after explicit user agreement. Publication requires a separate explicit authorization.

## Recovery, backup and demo-data QA (2026-10-25)

- Docker remains unavailable and was not installed. Shared runtime on `:8080`, PostgreSQL `:55432` and n8n `:5678` stayed live throughout the isolated work.
- Added `scripts/run-recovery-backup-integration.ps1`, `tests/integration_recovery_backup.py` and a bounded delay/port option to the loopback Yandex fixture. PowerShell syntax, Python compileall and Ruff passed.
- The drill uses a dedicated PostgreSQL cluster under `%LOCALAPPDATA%\LeadFlowRuntime\release-recovery-postgres-data` on `:55433`, isolated app/n8n source and restore databases, loopback provider `:18181`, API `:18100` and n8n `:15678`.
- The final drill passed twice. Worker state was observed as `processing`; PostgreSQL was stopped for six seconds while the same worker stayed alive and logged its bounded DB retry. After restart, the expired lease was reclaimed and produced exactly one extraction row with `attempts=2`, `revision=1`, status `succeeded`.
- Custom-format app and n8n dumps restored into new databases. App history, extraction and outbox plus metadata for two inactive five-node workflows matched before/after restore and after PostgreSQL restart. Backend, worker and n8n processes were then restarted on restored databases; API health/readiness and persistence passed.
- This establishes clean empty-database migrations/runtime health and process restart, not a clean dependency installation and not Docker execution. No Yandex or Telegram host was contacted.
- Added `docs/BACKUP_RESTORE.md`. n8n database dumps must be paired with the original encryption key stored separately as a secret; the key must never be logged or committed.
- Added `scripts/manage-local-demo-data.ps1`; process-local flags are restored after use and reset requires `-ConfirmReset`. Shared seed is six synthetic owned rows; idempotent wrapper rerun returned `created=0 existing=6`. Shared reset was not run.
- Fresh frontend evidence closed the earlier AI-panel mobile gap: exact `390×844`, DPR 1, no overflow, keyboard focus visible. The 200% artifact is a deterministic reflow emulation, not native Chrome zoom; native zoom and screen-reader coverage remain open.
- Read-only hygiene scan checked 117 Git-visible files (112 text and two visible images) with no confirmed secret/private-key/dump/archive/real-PII finding. It was heuristic and Git history does not yet exist; run a dedicated final scan before first commit/publication.

## Portfolio repository packaging (2026-10-25)

- Replaced the long root README with a concise portfolio-facing overview, primary curated hero, architecture, recorded evidence (`54` backend / `24` frontend), demo-data command, minimal launch and honest integration limits. Detailed setup moved to `docs/LOCAL_SETUP.md`.
- Added `docs/REPOSITORY_PREPARATION.md` with future, authorization-gated Git steps. No staging, commit, remote, push, deploy or publication occurred; no license was selected or added.
- Curated tracked set: five JPEGs under `docs/portfolio/images/`, with provenance/captions in `docs/portfolio/README.md`. Raw QA remains ignored under `artifacts/`.
- Added `.gitattributes` for stable text EOL and binary image handling. `.gitignore`/`.dockerignore` exclude runtime, logs, dumps, database files, coverage and raw test output; curated docs remain Git-visible and docs/tests are excluded from Docker build context.
- Added scoped `scripts/check-repository.ps1`. The packaging-stage run passed for 129 Git-visible candidate files, checking required portfolio files, forbidden paths, ignore rules, strict UTF-8, final newline/trailing whitespace, local Markdown links/images and common credential signatures without printing values. The post-review candidate grew to 131 files and passed the same check.
- The repository check is a packaging heuristic, not final security review. A dedicated working-tree scan and later history scan remain required before a public push.
- `docs/RELEASE_CHECKLIST.md` now separates the completed local portfolio package from an optional future hosted release. Docker runtime, HTTPS, live Yandex/Telegram and video are not blockers for the honest local case.

## Final pre-publication review support (2026-10-25)

- GPT-6 Astra completed the authorized final review with PASS for the local portfolio package and no remaining actionable P0/P1/P2; publication was not authorized.
- Reviewer-requested fresh backend run used exact disposable `leadflow_test_final_review`: `54 passed`, one Starlette/httpx deprecation warning; the DB was removed afterward and main lead count stayed `14 → 14`.
- Fixed F1 by executing all three mutable integration harness bodies in child PowerShell processes. `tests/test-harness-env-isolation.ps1` passed for success and injected-failure probes across all three scripts, comparing the complete parent environment without printing values; reviewer independently repeated this regression.
- Fixed F2 by making the AI harness validate/create only `leadflow_test_ai_integration` and verify `current_database()` before migrations. Owner-run fresh missing-DB execution recreated it and passed the loopback fixture; parent environment stayed unchanged, shared health stayed healthy and main lead count stayed `14 → 14`. Evidence was terminal output only, not a persisted log artifact.
- Final review report: `docs/FINAL_REVIEW.md`. Repository publication, commit, staging and remote operations remain unauthorized and were not performed.

## Public source release preparation (2026-10-25)

- The owner subsequently authorized publication of the source in a public GitHub repository with the planned slug `leadflow`; this supersedes the earlier publication boundary but does not change the historical scope of `docs/FINAL_REVIEW.md`.
- Infra owns the credentials-safe local initial commit only. The coordinator owns GitHub repository creation, remote configuration and push; infra must not add a remote or publish.
- The release remains an honest local demo: Yandex AI Studio and Telegram are not connected live, their credentials stay absent, and fixture/runtime evidence must not be described as live-provider success.
- No license was selected, so no `LICENSE` is added. Public visibility does not grant reuse rights by itself.
- Final candidate check passed for 131 Git-visible files; staged path denylist, `git diff --cached --check`, and a separate high-confidence secret-signature scan passed without exposing values. Application code was unchanged, so the already-passed functional/integration suites were not repeated.
