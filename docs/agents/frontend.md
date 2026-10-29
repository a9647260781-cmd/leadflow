# Frontend: durable context

## Ownership

Frontend implementation lives in `frontend/`. Product and visual direction are captured in root `PRODUCT.md` and `DESIGN.md`.

## Stack and routes

- React 19, TypeScript 5.7, Vite 6, React Router 7, Lucide icons.
- `/` — public repair lead form.
- `/login` — manager login.
- `/manager` — protected searchable, status-filtered, paginated lead list.
- `/manager/leads/:id` — protected lead detail, history, and status update.

## Stable decisions

- Browser API calls are relative `/api` URLs with `credentials: 'include'`; no frontend environment variables are required.
- Vite development proxy sends `/api` to `http://127.0.0.1:8000`; the dev server is strict on `127.0.0.1:5173`.
- Backend development must allow the exact origin `http://127.0.0.1:5173`, normally via `ADDITIONAL_ALLOWED_ORIGINS`.
- Production output is `frontend/dist`; production hosting must provide SPA fallback and same-origin `/api` reverse proxying.
- Public lead retries reuse one UUID only while the payload is unchanged. Editing any field generates a new UUID; a successful submission also resets it.
- Auth state is checked with `GET /api/auth/me` at app start. Protected API calls centrally invalidate local auth on `401`, allowing protected routes to redirect to `/login` while preserving the requested path.
- Logout clears local auth only after backend confirmation or a `401` that proves the server session is already absent. Network/server failures keep the manager signed in and expose an inline retry action.
- Empty lead status filters are omitted from query serialization because FastAPI rejects `status=` for an optional enum. Request cancellation preserves `AbortError`, so superseded searches never render as network failures.
- Status values are `new`, `in_progress`, `won`, and `lost`; UI labels are Russian.
- Known backend history events are localized at render time: `created` becomes «Заявка создана», and `status_changed` parses the backend transition into Russian status labels. Unknown future event types retain their backend message.
- A direct protected detail URL is preserved through auth bootstrap and login. The login screen suppresses its generic already-authenticated redirect while its own sign-in attempt is completing, avoiding a race that previously sent users to `/manager`.
- UI is a restrained, light, high-contrast work surface using OKLCH tokens. Mobile lead rows become structured records instead of horizontal-scroll tables.
- Lead detail always expects an `extraction` object. Only `pending` and `processing` trigger polling; each poll uses an `AbortSignal`, stops on terminal state, and is aborted on route change/unmount. Poll responses update only the extraction snapshot, so they cannot overwrite an unsaved manual draft.
- Extraction states map to honest Russian UI: `not_requested` «Нет разбора», `pending` «В очереди», `processing` «Разбираем», `succeeded` «Готово», `failed` «Не удалось», `not_configured` «Не подключено». Production never fabricates an AI result. `not_configured` offers manual entry plus an explicit «Проверить подключение» action so an existing lead can be queued after server credentials are added; a still-unconfigured `409` is translated to stable Russian copy.
- Completed extraction shows service, budget and timeframe beside exact evidence quotes. Null values are rendered as «Не указано». Budget is formatted as exact/range/«до»/«от» and appends currency only when the backend provides it. Provider error text is never shown; known safe codes get Russian copy and all others use a generic safe message.
- Manual extraction edits use full-replacement `PATCH /api/leads/{id}/extraction` with `expected_revision` captured when editing begins. Changing a semantic value clears its now-stale evidence quote; unchanged evidence is preserved. A `409` keeps the draft intact and asks the manager to explicitly load the latest server version, then choose between rebasing their draft or taking the fresh values. The UI states that saved manual edits are protected from background extraction. Retry uses `POST /api/leads/{id}/extraction/retry` for failed, not-yet-requested, and not-configured states. Both endpoints are same-origin, cookie-authenticated, and participate in central `401` invalidation.
- Status updates merge only status, history, and `updated_at` from their response; delayed status success or rollback cannot overwrite a newer extraction/manual save.

## Commands

From `frontend/`:

```powershell
npm ci
npm run dev
npm test
npm run build
```

## Verified status

- `npm install --no-audit --no-fund` completed and created `package-lock.json`.
- `npm test` passed on 2026-10-24: 6 files and 24 regression tests cover status query serialization, cancellation, protected `401` invalidation (including extraction writes), logout behavior, history localization, the direct protected-detail login return path, extraction budget/unknown/failure states, honest not-configured recovery, revision-conflict draft preservation/rebase, manual corrections, retry, active-only polling, abort cleanup, and delayed status success/error isolation from newer extraction state.
- `npm run build` passed on 2026-10-24 after the extraction UI implementation: TypeScript project build and Vite production bundle completed successfully (1604 transformed modules, including self-hosted Manrope Cyrillic assets).
- `impeccable detect frontend/src` returned no findings after the redesign and again after the extraction extension.
- Infra completed the live PostgreSQL-backed browser flow: submit → login → list/search/filter/empty → detail → status/history → logout → route guard → direct-detail login return. The fresh-tab console was clean, and 320 px / 390 px detail views had no horizontal overflow.
- Final public evidence is under `artifacts/redesign-qa/`. At the exact 1487 × 1058 / DPR1 source viewport, `public-desktop-1487x1058-final.png` has `clientHeight === scrollHeight === 1058`: the footer remains visible, the CTA and form rhythm align with the selected reference, and the first benefit remains on one line. The paired artifact is `comparison-final-source-left-current-right.png`.
- Extraction UI browser QA against the live no-key backend is complete; only a real Yandex call/model-quality check remains conditional on credentials.

### Technical QA refresh — 2026-10-25

- `npm test` reran successfully: 6 files, 24 tests. `npm run build` reran successfully: 1604 transformed modules.
- Real-browser regression on `http://127.0.0.1:8080` with the shared PostgreSQL passed: synthetic public submit, authenticated list, search, status filter, detail, status/history, manual extraction save, real two-tab revision conflict with draft preservation and explicit fresh-version choice, logout guard, direct-detail login return, and clean warn/error console.
- The additive fixed demo seed was checked after backend inserted it: list search showed the six `Демо · ...` records while preserving the existing records; `Демо · Анна, кухня` showed manually saved structured fields with exact evidence quotes, and `Демо · Марина, окна` showed honest `not_configured` plus manual entry and connection-check actions.
- Keyboard traversal passed on the public form and detail. Link/button focus uses a visible 3 px outline; focused inputs show the green border/ring. The captured detail order was logo → logout → back → «Исправить разбор».
- Fresh ignored screenshots are under `artifacts/portfolio-qa-2026-10-25/`. `04-ai-panel-390x844.jpg` and `05-keyboard-focus-390x844.jpg` are exactly 390×844 and were visually inspected; `window.innerWidth` was 390 at DPR 1 and document `scrollWidth === clientWidth`, so no horizontal overflow was present.
- `06-detail-200pct-zoom.jpg` records a deterministic 200% reflow emulation for a 1280×854 baseline (`innerWidth=640`, DPR 2). CSS mobile breakpoints activated, the detail grid collapsed to one column, and document `scrollWidth === clientWidth`. The tool could not safely drive Chrome's native zoom because its only targetable native window belonged to an unrelated user tab; no unrelated window was modified.
- No frontend defect was found, so no source/UI change was made during this QA pass. No independent reviewer, final review, commit, deployment, Yandex call, or Telegram call was performed.

## Integration QA checklist

- Submit a public request and confirm it appears in the manager list without duplicate creation on a same-payload network retry.
- Verify invalid login, valid login, direct protected-route refresh, logout, and post-logout route guard.
- Verify search, all four status filters, pagination, lead detail, status change, and history refresh.
- Capture wide and narrow viewport screenshots; check long Russian content, loading, error, empty, and success states.

## Product Design exploration

Three ImageGen redesign directions were generated from the captured current public form. The displayed order is authoritative:

1. «Сервисный бланк» — `C:\Users\Maboy\.codex\generated_images\01a16e21-efff-7da1-9f72-c3626ac83ec2\exec-6b77ee00-2859-4477-99ae-4c5fef947c57.png`
2. «Тихая мастерская» — `C:\Users\Maboy\.codex\generated_images\01a16e21-efff-7da1-9f72-c3626ac83ec2\exec-1eae8b54-2fc6-4106-9d8a-ee9063f4f583.png`
3. «Линия заявки» — `C:\Users\Maboy\.codex\generated_images\01a16e21-efff-7da1-9f72-c3626ac83ec2\exec-a194cd85-b488-4d32-aa00-2ba6820f339d.png`

Status: the user selected displayed option 1, «Сервисный бланк», and it is implemented. Its durable source is `docs/design/reference-service-docket.png`. The existing app was redesigned in place; it was not reinitialized. The public form uses `frontend/public/assets/service-tools.png`, a 3:1 transparent raster generated for the measured lower-left asset slot. The same open white surface, thin rules, Manrope typography, mineral green, and rare orange inspection accent extend through login, manager list, and lead detail without new routes or features. The decorative footer ruler from the mock was intentionally omitted rather than approximated with CSS art. Final Product Design QA evidence and verdict are recorded in root `design-qa.md`.

## Portfolio drafts

- `docs/PORTFOLIO_CASE.md` is now a recruiter-oriented finished local case: problem, user journey, engineering decisions, architecture, five real screenshots, latest recorded verification (`54` backend / `24` frontend), honest AI-assisted contribution, limitations, and résumé copy.
- `docs/DEMO_SCRIPT.md` defaults to the honest local/no-key branch. A hosted URL and live Yandex/Telegram remain optional; fixture output must never be presented as live. Notification wording promises bounded retries and explicit ambiguous-delivery handling, not exactly-once delivery.
- Curated captures and provenance are in `docs/portfolio/README.md` and `docs/portfolio/images/`: desktop/mobile public form, demo-only manager list, seeded manual extraction, and the real mobile `not_configured` state. `public-desktop.jpg` is the agreed primary README hero. All captures use the real local UI/PostgreSQL, synthetic `Демо · ...` records, and contain no external integration output or secrets.
- This portfolio packaging turn changed documentation and curated images only. It did not change UI/source, rerun tests/build, invoke the independent reviewer, connect external services, publish, commit, stage, or deploy.

### Editorial refresh — 2026-10-30

- `README.md` and `docs/PORTFOLIO_CASE.md` now explain the intended user, applicable small repair/service contexts, the operational problems LeadFlow addresses, and four concrete but explicitly illustrative workflows.
- The copy was checked against current docs and source: free-text intake and idempotency, server status history, optional Yandex extraction with manual fallback, and the exact Telegram rule (initial alert plus one 30-minute reminder only after the initial alert and while the lead remains `new`; the first transition out of `new` cancels that reminder permanently).
- The documentation explicitly avoids implying real clients, business effects, multi-manager assignment, live Yandex/Telegram use, or credential-free integrations. This was a documentation-only task; application code and tests were not changed or rerun.
