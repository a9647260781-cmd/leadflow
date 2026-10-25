# Backup, restore и безопасное обновление LeadFlow

Этот runbook относится к локальному Windows-контуру с portable PostgreSQL. Docker-развёртывание на текущей машине не проверено. Любой dump содержит пользовательские данные и должен храниться как секрет, вне публичного репозитория.

## Что нужно сохранять

Для полного восстановления нужны три независимых объекта:

1. PostgreSQL dump базы приложения `leadflow`.
2. PostgreSQL dump отдельной базы n8n.
3. Исходный `N8N_ENCRYPTION_KEY`, сохранённый отдельно в защищённом хранилище секретов.

Encryption key не входит в PostgreSQL dump. Без исходного ключа восстановленные n8n credentials нельзя расшифровать. Не помещайте ключ рядом с dump в незашифрованном архиве и не копируйте его в Git.

## Локальный backup

1. Остановите изменяющие данные процессы, оставив PostgreSQL запущенным:

   ```powershell
   .\scripts\stop-local-n8n.ps1
   .\scripts\stop-local-demo.ps1 -KeepPostgres
   .\scripts\portable-postgres.ps1 start
   ```

2. Создайте каталог вне публичного репозитория либо внутри игнорируемой `.runtime/`:

   ```powershell
   New-Item -ItemType Directory -Force .runtime\backups | Out-Null
   ```

3. Не выводя пароль, загрузите локальную конфигурацию и сделайте два custom-format dump:

   ```powershell
   $pgBin = Join-Path $env:LOCALAPPDATA 'LeadFlowRuntime\postgresql\pgsql\bin'
   $env:PGPASSWORD = [IO.File]::ReadAllText('.runtime\postgres-password.txt').Trim()
   . .\scripts\load-env.ps1 -Path .runtime\notifications.env

   & "$pgBin\pg_dump.exe" -h 127.0.0.1 -p 55432 -U leadflow -Fc `
     -f .runtime\backups\leadflow.dump leadflow
   & "$pgBin\pg_dump.exe" -h 127.0.0.1 -p 55432 -U leadflow -Fc `
     -f .runtime\backups\leadflow-n8n.dump $env:N8N_POSTGRES_DB

   Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue
   ```

4. Сохраните значение `N8N_ENCRYPTION_KEY` из `.runtime/notifications.env` в отдельное защищённое хранилище, не печатая его в терминал или лог.
5. Зафиксируйте рядом с backup только несекретные сведения: дату, версию приложения, Alembic revision и версию n8n.

## Restore drill

Сначала всегда восстанавливайте dump в новые базы. Не перезаписывайте рабочие базы до проверки результата.

Автоматизированный изолированный drill:

```powershell
.\scripts\run-recovery-backup-integration.ps1
```

Скрипт использует собственный PostgreSQL cluster и фиксированные QA-базы на порту `55433`, loopback AI fixture и ограниченные таймауты. Он проверяет:

- миграции и API health на пустой базе;
- реальный обрыв PostgreSQL при `processing` и восстановление того же worker;
- один итоговый extraction result без дубля;
- app history, extraction и notification outbox после `pg_dump`/`pg_restore`;
- metadata двух неактивных n8n workflow после restore;
- повторный запуск backend, worker и n8n с восстановленными базами;
- сохранность данных после отдельного restart PostgreSQL.

QA-dump сохраняются в игнорируемой `.runtime/backups/`. Скрипт не обращается к Yandex или Telegram и не изменяет общий PostgreSQL на порту `55432`.

Для ручного restore используйте новые, заранее проверенные имена баз и `pg_restore --exit-on-error --no-owner`. После restore укажите приложению новую базу только через process-local configuration, а n8n — новую базу и исходный `N8N_ENCRYPTION_KEY`. До переключения рабочего трафика проверьте:

```powershell
$pgBin = Join-Path $env:LOCALAPPDATA 'LeadFlowRuntime\postgresql\pgsql\bin'
. .\scripts\load-env.ps1 -Path .runtime\notifications.env
$appRestore = 'leadflow_restore_check'
$n8nRestore = 'leadflow_n8n_restore_check'

$env:PGPASSWORD = [IO.File]::ReadAllText('.runtime\postgres-password.txt').Trim()
& "$pgBin\createdb.exe" -h 127.0.0.1 -p 55432 -U leadflow -O leadflow $appRestore
& "$pgBin\createdb.exe" -h 127.0.0.1 -p 55432 -U leadflow `
  -O $env:N8N_POSTGRES_USER $n8nRestore
& "$pgBin\pg_restore.exe" -h 127.0.0.1 -p 55432 -U leadflow `
  --exit-on-error --no-owner -d $appRestore .runtime\backups\leadflow.dump

$env:PGPASSWORD = $env:N8N_POSTGRES_PASSWORD
& "$pgBin\pg_restore.exe" -h 127.0.0.1 -p 55432 -U $env:N8N_POSTGRES_USER `
  --exit-on-error --no-owner -d $n8nRestore .runtime\backups\leadflow-n8n.dump
Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue
```

Имена выше зарезервированы для restore-check. Если база с таким именем уже существует, остановитесь и выберите другое явное имя; не добавляйте автоматический `dropdb` к рабочей инструкции.

После восстановления проверьте:

- `alembic current` и `/api/health`;
- число заявок и историю выбранной заявки;
- extraction status/revision и отсутствие дублей;
- notification outbox;
- имена, active state и число узлов n8n workflow;
- чтение существующих n8n credentials без их вывода.

## Обновление и откат

Перед обновлением:

1. Остановите backend, worker и n8n.
2. Создайте оба dump и отдельно сохраните n8n encryption key.
3. Запишите текущие Git revision/версию сборки, `alembic current`, PostgreSQL и n8n versions.
4. Не удаляйте volumes/runtime предыдущей версии до успешной проверки новой.

После обновления сначала выполните миграции, затем API health и только потом запускайте worker/n8n.

Предпочтительный откат — предыдущая версия приложения плюс восстановление проверенных dump в новые базы. `alembic downgrade` допустим только для конкретной заранее проверенной обратимой миграции; не используйте его как универсальный аварийный механизм. Для отката n8n используйте прежнюю закреплённую версию, восстановленную базу и тот же encryption key. Команды `docker compose down -v` и удаление portable data не являются способом отката: они уничтожают данные.
