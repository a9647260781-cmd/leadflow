# Локальный запуск LeadFlow

## Docker Compose

Требования: Docker с Compose plugin и свободный порт `8080`.

```powershell
Copy-Item .env.example .env
# Замените все change-me значения длинными случайными секретами.
docker compose up --build -d
docker compose ps
docker compose exec backend python -m app.cli create-manager
```

Откройте `http://localhost:8080`.

- `http://localhost:8080/healthz` — nginx;
- `http://localhost:8080/api/health` — API и PostgreSQL;
- `docker compose down` — остановка с сохранением volumes;
- `docker compose down -v` — удаление данных, только осознанно.

Миграции выполняются до старта API. Внешнему миру открыт только nginx; `/api` работает на том же browser origin. На исходной QA-машине Docker отсутствовал, поэтому этот путь подготовлен, но фактически ещё не проверен.

## Проверенный Windows-контур без Docker

Проверенная среда использовала Python 3.12, Node.js и настоящую PostgreSQL 17.11 из [официального portable-архива EDB](https://www.enterprisedb.com/download-postgresql-binaries). SQLite fallback отсутствует.

Windows-сборка `initdb` не смогла создать cluster внутри кириллического пути репозитория, поэтому per-project binaries/data находятся в `%LOCALAPPDATA%\LeadFlowRuntime`. Windows-служба не устанавливается; секреты остаются в игнорируемой `.runtime/`.

После распаковки ожидается файл `%LOCALAPPDATA%\LeadFlowRuntime\postgresql\pgsql\bin\postgres.exe`.

```powershell
python -m venv .runtime\venv
.\.runtime\venv\Scripts\python.exe -m pip install -e '.\backend[dev]'

Push-Location frontend
npm ci
Pop-Location

.\scripts\portable-postgres.ps1 start
.\scripts\create-local-demo-credentials.ps1
. .\scripts\load-env.ps1 -Path .\.runtime\local.env
. .\scripts\load-env.ps1 -Path .\.runtime\demo-credentials.env

Push-Location backend
..\.runtime\venv\Scripts\python.exe -m alembic upgrade head
..\.runtime\venv\Scripts\python.exe -m app.cli create-manager
Pop-Location

.\scripts\start-local-demo.ps1
```

Приложение доступно на `http://localhost:8080`. Повторный `start-local-demo.ps1` использует только корректно отслеживаемые процессы и отказывается занимать чужой порт.

Остановка:

```powershell
.\scripts\stop-local-demo.ps1
```

Чтобы оставить PostgreSQL запущенной, добавьте `-KeepPostgres`. Удалять `%LOCALAPPDATA%\LeadFlowRuntime` можно только вручную после остановки и проверки точного пути.

## Менеджер и demo-данные

Credentials менеджера создаются локально и хранятся только в `.runtime/demo-credentials.env`.

```powershell
.\scripts\manage-local-demo-data.ps1 seed
```

Seed создаёт шесть фиксированных синтетических заявок и безопасно повторяется. Он отказывается работать при включённых AI/notifications. Удаление только этих owned rows:

```powershell
.\scripts\manage-local-demo-data.ps1 reset -ConfirmReset
```

## Yandex AI Studio — опционально

Без credentials приложение использует стабильное состояние `not_configured`; ручное заполнение доступно. Для live-подключения заполните игнорируемый `.runtime/ai.env`:

```dotenv
AI_ENABLED=true
YANDEX_API_KEY=
YANDEX_MODEL_URI=
```

API key и полный model URI берутся из вашего Yandex Cloud account. Ключ не передавайте в командной строке, логах, документации или Git. Во внешний сервис уходит описание заявки; отдельные поля имени и телефона не отправляются, но пользователь может сам написать контакты внутри описания. Старые заявки автоматически не обрабатываются.

После изменения локального файла:

```powershell
.\scripts\stop-local-demo.ps1 -KeepPostgres
.\scripts\start-local-demo.ps1
```

## Telegram/n8n — опционально

Подготовка локального PostgreSQL-backed n8n без бота:

```powershell
.\scripts\create-local-notification-config.ps1
.\scripts\install-local-n8n.ps1
.\scripts\start-local-n8n.ps1
```

Bot token и chat id остаются пустыми; production workflow неактивны. После создания отдельного тестового бота заполните `.runtime/notifications.env`, задайте доступный с телефона `MANAGER_PUBLIC_URL` и выполните:

```powershell
.\scripts\enable-local-notifications.ps1
```

Скрипт не принимает секреты аргументами. `localhost` в manager URL не откроется на телефоне; публичный tunnel автоматически не создаётся.

## Проверки

```powershell
Push-Location backend
..\.runtime\venv\Scripts\python.exe -m ruff check .
..\.runtime\venv\Scripts\python.exe -m pytest
Pop-Location

Push-Location frontend
npm ci
npm test
npm run build
Pop-Location

python .\tests\integration_api.py
.\scripts\run-ai-mock-integration.ps1
.\scripts\run-notification-n8n-integration.ps1
.\scripts\run-recovery-backup-integration.ps1
```

Интеграционные скрипты используют отдельные базы и loopback fixtures. Они не являются live-проверкой Yandex или Telegram. Backup/restore и upgrade/rollback описаны в [BACKUP_RESTORE.md](BACKUP_RESTORE.md).
