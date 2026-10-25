# LeadFlow agent workflow

Read this file, `docs/PROJECT_CONTEXT.md`, `docs/TEAM.md`, `docs/HANDOFF.md`, and the relevant `docs/agents/*.md` before changing the project.

## Scope and decisions

- Current scope is the LeadFlow MVP described in `docs/PROJECT_CONTEXT.md`, including Yandex AI Studio extraction and the authorized n8n-scheduled Telegram notifications for a new lead plus one 30-minute reminder. Do not add Bitrix24 features yet.
- AI integration must remain optional and explicit: no committed credentials, no automatic backfill of old leads, only the lead description may be sent to the provider, and missing credentials must produce a stable `not_configured` state rather than a fake result or endless loading state.
- Preserve PostgreSQL as the only application database. Do not add a SQLite fallback.
- Never commit secrets. `.env` and `.runtime/` are local-only.
- Keep the public web app and API on one browser origin in production: `http://localhost:8080`, with `/api` proxied to the backend.
- Treat migrations as required startup work. A deployment is not healthy until migrations and the API health check succeed.

## Durable collaboration

The user explicitly authorizes multi-agent work on this repository. The coordinating agent only delegates, coordinates, and reports; implementation and review remain delegated unless the user changes that instruction.

- Developer model requested by the user: GPT-5.6 Sol.
- Independent reviewer model requested by the user: GPT-6 Astra.
- Backend owner maintains `backend/` and `docs/agents/backend.md`.
- Frontend owner maintains `frontend/` and `docs/agents/frontend.md`.
- Infrastructure owner maintains root deployment files, `docker/`, integration tests/scripts, and `docs/agents/infra.md`.
- The coordinator maintains product direction and resolves cross-area contracts.
- The independent reviewer maintains `docs/agents/reviewer.md` with review scope, findings, and verified outcome. GPT-6 Astra is reserved for one final pre-publication review only, after the user explicitly agrees to start that review; feature-by-feature review is not an approval gate.

At task start, read the durable files instead of assuming access to previous agent chats. At task end, update the relevant agent memory plus `docs/HANDOFF.md` when commands or verified status changed. Record stable facts and decisions, not hidden reasoning or raw chat transcripts.

Before editing another owner's area, coordinate the requested change with that owner when an active team exists. Preserve unrelated user changes.

## Quality bar

- Run checks relevant to every changed area.
- Developer tests and functional QA continue during implementation. Do not invoke the independent Astra reviewer until the user agrees to the final pre-publication review.
- For integration changes, verify authorization failures, the public submit-to-manager workflow, logout guards, and persistence against real PostgreSQL.
- Browser-facing changes require a narrow-viewport visual check.
- Report exact commands, what passed, and any environment limitation honestly.

Reference for durable Codex workflows: https://developers.openai.com/cookbook/examples/codex/iterating-development-workflows-with-codex
