# Reviewer memory

## Ownership

Independent review of the finished task-scoped candidate. The reviewer does not implement product features and records actionable findings for the owning developers. The current repository has no HEAD, so final review covers the source tree rather than a diff.

## Review checklist

- Current MVP scope includes optional explicit AI and authorized n8n-scheduled Telegram delivery; Bitrix24 remains excluded.
- API contract alignment between browser, proxy, and backend.
- Auth, Origin/CSRF policy, session-cookie flags, validation, rate limits, and unauthorized behavior.
- Idempotent public submission and complete status history.
- Migration safety and real PostgreSQL behavior.
- Responsive UI, keyboard/focus behavior, readable states, error and empty states.
- No committed secrets or generated runtime data.
- Reproducible setup and truthful verification notes.

## Current status

2026-10-25: user explicitly authorized one final pre-publication review by GPT-6 Astra and prohibited publication. `/root/final_reviewer` completed that review; [FINAL_REVIEW](../FINAL_REVIEW.md) is the authoritative current report. **Passed for the local portfolio package, no remaining actionable P0/P1/P2 findings.** F1 (QA harness environment contamination) and F2 (AI harness missing database bootstrap) were fixed by infrastructure and independently source-rechecked. Reviewer independently ran the three-harness success/failure environment regression: PASS. Infra ran the AI fixture from an absent dedicated database: PASS, shared lead count14 unchanged; this is terminal evidence only. Independent offline backend subset32, frontend24/build1604, workflow validator2 and final131-file candidate hygiene checks passed. Infrastructure reran full backend54 on disposable `leadflow_test_final_review`, preserving the shared database. All five curated images and raw conflict/focus evidence were inspected. No live AI/Telegram calls, Docker runtime claim, hosting approval, Git staging/commit/remote or publication. See the report for performed versus historical evidence, model/delivery limitations and separate publication decisions.

All entries below are historical development/review records; their approvals do not independently approve the current final candidate.

Independent review closed on 2026-10-24: approved for the current MVP with no remaining actionable findings. All six initial findings and the subsequent local-start lifecycle finding are resolved. Docker runtime remains unverified because Docker is unavailable. The workspace currently has no Git repository, so review covered the available source tree rather than a Git diff.

## Actionable findings sent to owners

- P1 — `frontend/src/api.ts:60`: default list serializes `status=`; backend optional enum rejects it with 422. Omit an empty status query parameter. Reproduced with FastAPI TestClient and a current-manager dependency override; no database access was needed.
- P2 — `frontend/src/api.ts:37`: catch-all fetch error conversion changes AbortError to a network ApiError. List cancellation handlers consequently display stale errors after filter/search changes and development StrictMode cleanup. Preserve cancellation or suppress all aborted responses in the consumer.
- P2 — `frontend/src/auth.tsx:38` and `frontend/src/components/ManagerShell.tsx:14`: failed logout clears local auth and does not render a retryable failure, although the server session cookie remains valid. An offline logout followed by reconnection/reload restores access. Clear auth only after confirmed logout or an already-unauthorized response; retain and explain other failures.
- P2 — `frontend/src/auth.tsx` and protected API error handling: expired/revoked sessions leave a truthy user in context; protected requests show 401 errors while `/login` redirects back to the manager page. Invalidate local authentication on protected API 401 and permit login again.
- P2 — `compose.yaml:24` and `docker/nginx.conf:21`: no configured proxy trust means all production requests share the nginx peer's rate bucket. Configure coherent proxy trust and replace incoming X-Forwarded-For before trusting it; merely trusting the current appended header introduces spoofing.
- P2 — `compose.yaml:26`: raw password interpolation into DATABASE_URL breaks connection parsing for valid passwords containing URL-reserved characters. Encode/build the URL safely or explicitly constrain the documented setup to generated URL-safe credentials.

## Evidence and remaining checks

- Inspected backend routes, models, schemas, sessions, Origin enforcement, password hashing, row locking, PostgreSQL idempotency insert, Alembic migration, frontend routing/API/state, Compose, nginx, and setup scripts.
- Isolated command from `backend/`: piped a Python script into `.venv/Scripts/python.exe -`, overrode `get_current_manager`, requested `/api/leads?search=&status=&page=1&page_size=20` using TestClient. Actual result: 422, enum validation error at query status.
- No direct authentication bypass, raw session-token persistence, SQL injection, or public lead-detail leakage found in inspected source.
- PostgreSQL tests are deliberately destructive to their disposable test schema; reviewer did not run them against the shared runtime database.
- Docker runtime is unavailable in this environment; deployment cannot be described as Docker-verified.
- Final closeout must verify owner fixes, successful PostgreSQL workflow/persistence, browser auth/logout/expired-session behavior, retry behavior, and narrow-viewport visual inspection. Infrastructure owner is arranging this evidence.

## Fix re-review (2026-10-24)

All six initial findings are resolved by independent source inspection:

- Empty filters are omitted; cancellation errors retain their identity.
- Logout clears authentication only after success or an already-unauthorized response, and the manager shell renders a retryable error for other failures.
- Protected list/detail/status 401 responses notify the auth provider, clearing local auth and allowing the protected-route redirect.
- Compose provides separate DB credential components. SQLAlchemy constructs the URL safely; Alembic escapes percent signs for configuration interpolation.
- Nginx overwrites X-Forwarded-For and has a fixed internal IP, which is the backend's sole trusted proxy IP.

Regression evidence reviewed: frontend `api.test.ts` and `auth.test.tsx` cover eight tests reported passing by the frontend owner, together with `npm run build`. Backend owner reports `.venv/Scripts/python.exe -m pytest` against a dedicated PostgreSQL 17.11 database: ten tests passed, including migration downgrade/upgrade, concurrent identical submission (201 + 200, same ID), auth/Origin, history, logout revocation, and expired sessions; Ruff passed. Reviewer inspected those test cases and did not reset the shared database.

No additional blocking source finding identified in this pass. Final integration approval is still pending browser workflow, PostgreSQL restart persistence, and narrow-viewport visual evidence. Docker runtime remains explicitly unverified.

## Integration review follow-up

- Independently opened `artifacts/lead-detail-narrow.png`: the mobile detail screen is readable, with UUID, status, contact metadata, description, and history fitting the viewport without visible clipping. The English history text is being localized by the frontend owner.
- Inspected `tests/integration_api.py`; its live assertions exercise anonymous denial, missing Origin denial, identical replay, login, default list, detail, status/history, logout, and post-logout denial through the same-origin proxy.
- New P2 sent to infra: repeated `scripts/start-local-demo.ps1` execution launches duplicates, replaces the process registry with failed child PIDs, and can report ready against the original listeners. Require an already-running/occupied-port preflight and child liveness checks; otherwise the documented stop command loses ownership of the original processes. This new script issue remains pending owner correction.
- Infrastructure reports successful live API smoke and PostgreSQL restart persistence (lead count remained one, health returned ok); final browser guards/search/filter evidence is pending.

## Final closeout — approved

- Independently re-read the final startup script: tracked PID/start-time reuse, occupied-port refusal, closed-port probe handling, child failure cleanup, and health through the 8080 proxy address resolve the lifecycle finding. Infra executed stop (8000/8080 closed), cold start, and repeated start (existing processes reused); PostgreSQL retained two leads after restart.
- Independently reviewed the localized history formatter and direct-detail login return-path fix, including its App-level regression test. Frontend owner reports the final `npm test` result as thirteen passing tests across four files and a successful `npm run build`.
- Backend final evidence: ten tests passed against real PostgreSQL 17.11 using a dedicated disposable database, including migration downgrade/upgrade, concurrent same-ID retry, auth, Origin, history, expiry and revocation; Ruff clean.
- Infra ran `python tests/integration_api.py` successfully through the live 8080 proxy. Chrome verified submit, login, default list, search/filter, detail, status/history, logout, protected-route guards, and return to the requested detail after login. Failed logout with the API offline retained authentication and displayed retry; logout worked after recovery.
- Reviewer independently opened both the initial narrow detail screenshot and `artifacts/lead-detail-history-narrow.png`; the final history is Russian, wraps correctly, and remains readable at the tested 390×844 viewport. No visible horizontal clipping was found.
- Reviewed final README, handoff, Compose/nginx, backend configuration and relevant tests. No remaining actionable finding in the implemented MVP scope. No Docker runtime verification is claimed; local E2E uses PostgreSQL/FastAPI/Vite, while Docker/nginx received source review only.
- `docs/HANDOFF.md` contains the final integrated status and commands, maintained by the infrastructure owner to avoid concurrent edits.

## Selected Service Docket redesign — 2026-10-24

- Applied the Product Design internal `design-qa` skill to the user-selected option 1, using the exact source `exec-6b77ee00-2859-4477-99ae-4c5fef947c57.png` (durable copy `docs/design/reference-service-docket.png`).
- Root `design-qa.md` is the authoritative report; final result is `passed`. It records three source/implementation comparisons with both artifacts in the same input, matching 1487×1058 CSS/pixels at DPR1, and readable paired hero/form crops.
- Initial P1 typography and P2 form rhythm were corrected. A second capture revealed remaining below-fold overflow and benefit title wrapping; bounded spacing/column fixes restored scrollHeight1058, CTA around y803 and footer around y988. Mobile P2 manager entry was corrected from a small unlabeled arrow to visible «Вход» with a 44px target.
- Final reviewer inspected the full source/current pair, final focused pairs, 390px public and 320px detail evidence. Core typography, layout rhythm, palette, generated tool imagery and app copy meet the selected direction; remaining minor font/raster texture/tool geometry/footer decoration differences are explicitly P3.
- Frontend thirteen tests and build pass after final CSS; infra browser submit/login/search/filter/detail/status/history/logout/guards/return-path workflow passes, console warnings/errors empty, no horizontal overflow at320/390. Existing backend ten-test PostgreSQL baseline was not rerun for this presentation-only change and is not misrepresented as new evidence.
- Tablet/200% zoom and exhaustive screen-reader/keyboard audit were not performed. Docker runtime remains unverified. No remaining actionable P0/P1/P2 finding; coordinating agent owns final preview handoff and infra owns handoff verification notes.

## Optional Yandex extraction — initial review, 2026-10-24

Current extraction review remains open pending fixes and integrated verification. No production provider call was made; user requested preparation without a key. This review does not alter the prior redesign report.

Actionable findings sent to owners:

- P1/P2 lost-update protection: manual extraction full-replacement PATCH originally carried no expected revision; two stale drafts could overwrite each other or a newly completed worker result. Backend has added required `expected_revision`, 409 conflict and a revision increment on worker completion; frontend must capture the revision at edit start, preserve the dirty draft and expose conflict recovery. Backend reports 28 PostgreSQL tests after its fix; final review pending.
- P2 configuration recovery: UI originally excluded `not_configured` from retry actions even after credentials were later added/restarted. Explicit recovery is required; no automatic backfill. Frontend correction in progress.
- P1 provider envelope compatibility: `backend/app/extraction.py` initially parsed only top-level `alternatives`. Official operation examples for the configured completion endpoint return a `result.alternatives` envelope, while the REST schema depicts bare alternatives. Support both documented shapes with adapter tests; otherwise a valid result can become repeated `invalid_response` failures. Primary examples: [Yandex function-call operation](https://aistudio.yandex.ru/en/docs/ai-studio/operations/generation/function-call), [Yandex entity-recognition example](https://yandex.cloud/ru/docs/ai-studio/prompts/yandexgpt/automation-ner); [REST schema](https://aistudio.yandex.ru/en/docs/ai-studio/text-generation/api-ref/TextGeneration/completion).
- P2 unsupported numeric budget: pure `ExtractionResult` + `validate_evidence` reproduction accepted budget_max=999999 and currency=USD with exact quote `до 5000 рублей` from description `Ремонт, бюджет до 5000 рублей.`. Exact quote existence alone does not ground numeric amount, currency or min/max direction. Request conservative validation/clearing with explicit hostile-response regression cases; do not claim perfect semantic grounding or live model accuracy.
- P2 worker lifecycle: `worker.run` initially allowed transient SQLAlchemy errors to terminate the unsupervised Windows worker, leaving jobs queued indefinitely after a DB outage. Request sanitized recovery with session rollback/close and polling delay.
- P2 missing-key recovery: disabled worker initially only idled, leaving jobs queued before credential removal in pending/processing forever. Request safe reconciliation to a stable `not_configured` state without provider calls, backfill or overwriting manual edits.
- P2 frontend concurrent status writes: `LeadDetailPage.tsx` merges an entire status response and rolls back an entire prior lead, including extraction. A delayed status success/failure can erase a newer extraction snapshot from the UI. Apply/rollback only status-related fields and preserve current extraction; test delayed responses after manual save.

The creation-date prompt anchor was reviewed with the coordinator, who confirmed it was explicitly included in the original backend task. Its omission is an optional simplification because timeframe remains verbatim; it is not recorded as a separate blocker.

Positive source findings: enqueue shares the new-lead transaction; unique lead extraction prevents duplicate replay work; claim uses row locks/SKIP LOCKED; provider IO occurs after claim commit; completion/failure are fenced by claim token and revision; migration preserves old leads as `not_requested` without queueing; no-key new leads become `not_configured`; public responses do not expose extraction metadata; auth/Origin guards remain on manager writes; provider errors are safe codes rather than upstream text.

Initial evidence: inspected adapter, queue, worker, models, schema/migration, routes, frontend panel/polling, Compose and Windows scripts. Ran only the pure fabricated-budget validator reproduction; no shared DB reset or provider request. Backend and infra own dedicated PostgreSQL/worker/browser integration; reviewer will independently inspect their results and narrow UI evidence on closeout.

## Yandex extraction fix re-review

- Frontend fixes accepted by independent source/test inspection: edit-start `expected_revision` stays stable during polling; 409 preserves the draft and requires explicit reload followed by retain-draft/take-fresh choice; `not_configured` exposes a later connection check with honest Russian copy; delayed status success/failure changes only status-related fields and preserves extraction. Frontend reports 24 tests and build passing.
- Backend fixes accepted by source inspection: both official envelope shapes; exact quote amount/currency/direction checks; optimistic PATCH rejection and worker revision increment; sanitized/capped database recovery loop; disabled-worker reconciliation fences pending/processing jobs and preserves saved values/manual provenance.
- Provider prompt was simplified to static policy plus description only; no lead creation metadata is sent. No production fake-result fallback exists.
- Follow-up P2 found and fixed: numeric quote `5\u202f000 рублей` initially crashed the new parser with Decimal InvalidOperation. The parser now normalizes all matched Unicode whitespace and converts parsing errors into safe ProviderError. Regression covers narrow no-break space.
- Reviewer independently ran `.venv/Scripts/python.exe -m pytest tests/test_extraction_provider.py tests/test_worker.py -q` before the Unicode follow-up: 18 passed. After the fix ran `.venv/Scripts/python.exe -m pytest tests/test_extraction_provider.py -q`: 17 passed, including the new regression. These use offline transport fixtures; no provider network request or shared PostgreSQL reset was performed by reviewer.
- Backend owner reports final dedicated PostgreSQL suite: 38 passed, Ruff clean. Final live-main no-key/manual flow and isolated real-worker/mock-provider integration evidence are owned by infra; final visual/integration closeout remains pending.

## Yandex extraction final code-review closeout

Code review passed with no remaining actionable correctness finding. Visual coverage is incomplete: the new AI panel has not received the required narrow-viewport visual verification, so this is not an unconditional visual-QA approval.

- All eight actionable findings from this scope are resolved: optimistic manual concurrency, later configuration recovery, both documented response envelopes, conservative numeric budget grounding, transient DB retry loop, no-key queued-job reconciliation, status-response isolation, and Unicode thousands separator safety.
- Final timeout hardening was inspected: PostgreSQL engine and Alembic use a positive bounded connection timeout, default five seconds. Backend owner reran the dedicated PostgreSQL suite: **38 passed**; Ruff/compileall clean; explicit Alembic upgrade/downgrade succeeded.
- Independent reviewer checks: offline provider/worker subset **18 passed** before the last Unicode correction; final provider subset **17 passed**, including U+202F handling. Reviewer performed no shared database reset and no live Yandex request.
- Frontend owner final verification: **24 tests passed**, production build passed. Source review confirms conflict recovery preserves the draft, old revisions cannot silently overwrite newer records, saved manual values survive late worker responses, and status saves cannot replace the extraction snapshot.
- Infra's isolated real PostgreSQL/API/worker plus local HTTP provider-fixture pipeline passed: pending work, transient retry, structured result/evidence, authorization and Origin rejection, manual protection/edit, explicit rerun and eventual failure/retry. The fixture uses the documented `result.alternatives` envelope and rejects synthetic name/phone leakage or an enabled provider logging header. Isolated test services/ports were cleaned up. This is fixture evidence, not live Yandex accuracy or availability evidence.
- Main app verification reported by infra: new leads show stable `not_configured`; connection check gives the honest unconfigured response; manual extraction save/reload works and survives a full PostgreSQL/app restart; API, worker and frontend restart/repeated-start remain healthy. No key was added and no production model request occurred.
- **Outstanding narrow visual check:** IAB was unavailable. Chrome CUA functional/AX checks succeeded, but screenshot(path) did not persist an artifact and requested tab sizing was ignored. The native resize fallback was stopped by computer-use policy because the active Chrome URL could not be determined confidently. No further UI bypass was attempted. There is no new 390 px AI-panel screenshot, and old redesign screenshots do not verify this panel.
- **Outstanding forced-outage end-to-end check:** the separate outage harness hung before creating its recovery row, outside worker processing. Therefore actual end-to-end worker recovery from a forced database outage is not claimed; the sanitized retry loop is covered by source review and focused unit tests. This does not invalidate the completed normal fixture pipeline or restart persistence checks.
- Scope limitations remain explicit: extraction is optional, old leads are not auto-backfilled, only description is sent, unsupported/ambiguous values remain null/raw text rather than fabricated facts, semantic extraction accuracy needs a later authorized live-provider check, and Docker execution remains unavailable/unverified. The prior `design-qa.md` was preserved unchanged because it covers the earlier redesign.
