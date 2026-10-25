# Команда LeadFlow

Этот файл хранит роли, а не обещание постоянно запущенных агентов. Новый агент начинает с `AGENTS.md`, `docs/PROJECT_CONTEXT.md`, `docs/HANDOFF.md` и памяти своей роли.

| Роль | Текущий путь агента | Ответственность | Запрошенная модель |
| --- | --- | --- | --- |
| Координатор | `/root` | Контракт продукта, делегирование, сведение результатов, независимый review | текущая модель координатора |
| Backend-разработчик | `/root/backend` | FastAPI, SQLAlchemy, Alembic, PostgreSQL, auth и API-тесты | GPT-5.6 Sol |
| Frontend-разработчик | `/root/frontend` | React/TypeScript/Vite, публичная форма и кабинет менеджера | GPT-5.6 Sol |
| Infra/QA-разработчик | `/root/infra` | Compose, reverse proxy, документация запуска, PostgreSQL и browser E2E | GPT-5.6 Sol |
| Automation-разработчик | `/root/automation` | n8n workflow exports, validator и automation-документация | GPT-5.6 Sol |
| Независимый reviewer | `/root/reviewer` только после согласования пользователя | Один общий review перед публикацией проекта; не review каждой функции | GPT-6 Astra |

Файлы памяти ролей: `docs/agents/backend.md`, `docs/agents/frontend.md`, `docs/agents/infra.md`, `docs/agents/automation.md`, `docs/agents/reviewer.md`. Обновляйте их в конце работы, если появились новые устойчивые решения, команды или ограничения. Developer tests и функциональная QA выполняются по ходу работы; Astra подключается только к финальному pre-publication review после отдельного согласования пользователя.
