# Передача проекта

## Подготовка к портфолио

Актуальный порядок оставшихся работ, блокеры и критерии готовности собраны в
[`RELEASE_CHECKLIST.md`](RELEASE_CHECKLIST.md). Согласованный финальный review GPT-6 Astra завершён:
[`FINAL_REVIEW.md`](FINAL_REVIEW.md) фиксирует **PASS** локального portfolio package без оставшихся
actionable P0/P1/P2. Владелец впоследствии разрешил публикацию исходников в публичном GitHub-репозитории `leadflow`.

Локальный portfolio package собран: repo-facing `README.md`, кейс `docs/PORTFOLIO_CASE.md`,
demo script, пять curated screenshots с manifest, локальный setup и инструкция подготовки Git.
30 октября 2026 года README и portfolio case дополнены описанием целевой аудитории, применимости и
четырьмя иллюстративными сценариями; возможности и ограничения сверены с текущими docs/source.
Это была только редактура документации: код и тестовый статус не менялись.
`scripts\check-repository.ps1` прошёл для 131 Git-visible candidate files: обязательные portfolio-файлы,
ignore rules, UTF-8/whitespace, локальные Markdown links/images и типовые credential signatures.
По запросу reviewer backend suite свежо прошёл на отдельной disposable PostgreSQL-БД: `54 passed`;
frontend `24 passed` относится к последней функциональной регрессии. До release-прохода Git был без
HEAD/коммитов/remote/staging. LICENSE не выбран; отсутствие лицензии сохранено осознанно. Infra
готовит локальный initial commit, а создание remote и push остаются за координатором.

## Быстрый запуск через Docker

Требования: Docker с Compose plugin.

1. Скопируйте `.env.example` в `.env` и замените `POSTGRES_PASSWORD` на длинный случайный пароль.
2. Выполните `docker compose up --build -d`.
3. Дождитесь статуса `healthy`: `docker compose ps`.
4. Создайте менеджера интерактивно: `docker compose exec backend python -m app.cli create-manager`.
5. Откройте `http://localhost:8080`.

Остановка без удаления данных: `docker compose down`. Полное удаление базы выполняется только осознанной командой `docker compose down -v`.

## Проверки

- API: `http://localhost:8080/api/health`
- Web/nginx: `http://localhost:8080/healthz`
- Backend: `cd backend`, затем `python -m pytest` и `python -m ruff check .`
- Frontend: `cd frontend`, затем `npm ci`, `npm test` и `npm run build`
- Recovery/backup drill: `scripts\run-recovery-backup-integration.ps1`
- Demo-данные: `scripts\manage-local-demo-data.ps1 seed`; scoped reset — `scripts\manage-local-demo-data.ps1 reset -ConfirmReset`
- Backup/restore runbook: [`BACKUP_RESTORE.md`](BACKUP_RESTORE.md)

## Текущий проверенный статус

- Базовый этап до AI: PostgreSQL 17.11, Alembic downgrade/upgrade и backend integration suite — `10 passed`; Ruff — clean.
- Базовый redesign-этап до AI: frontend `13 passed`; production build — успешно.
- Live API smoke на `localhost:8080`/`127.0.0.1:8080`: unauthorized, Origin, идемпотентность, login, list, detail, status history, logout — успешно.
- Persistence: после stop/start PostgreSQL число заявок сохранилось, API health вернулся в `ok`.
- Chrome E2E: public submit → login → list/search/filter → detail → status/history → logout → protected guard → login return path — успешно.
- Отказ logout при недоступном API оставляет пользователя в кабинете и показывает повтор действия; после восстановления API выход успешен.
- Узкий viewport `390×844` проверен визуально; итоговые снимки находятся в игнорируемом `artifacts/`.
- Redesign QA: публичный экран снят в точном размере референса `1487×1058` при DPR 1 и сопоставлен в одном изображении; footer полностью помещается при `scrollHeight=1058` без desktop-scrollbar. Финальные снимки public/login/manager/detail сняты также в `390×844`, карточка дополнительно проверена при ширине `320`. Горизонтального overflow и ошибок/предупреждений в чистой browser console не обнаружено.
- После redesign повторно пройден реальный путь submit → login → list/search/filter/empty → detail → status/history → logout → protected guard → возврат к прямой ссылке. Финальные QA-артефакты находятся в `artifacts/redesign-qa/`.
- Независимый `design-qa.md` завершён с `final result: passed`: после трёх визуальных итераций не осталось P0/P1/P2 расхождений. Остаточные P3 и непокрытые tablet/200% zoom/screen-reader проверки перечислены в отчёте.
- Backend AI extraction: добавлены Alembic-миграция, Yandex structured-output adapter,
  durable worker с lease/fencing и защищённые API ручной коррекции/retry. Worker запускается после
  миграций командой `python -m app.worker` и сам миграции не выполняет.
- Backend после AI-изменений: PostgreSQL 17.11 suite — `38 passed`, Ruff — clean. Транспорт Yandex,
  schema и ошибки проверены только через `httpx.MockTransport`. Live-вызов и качество модели
  намеренно не проверялись без ключа; при отсутствии настройки показывается `not_configured`.
- Текущий frontend: свежий повторный прогон `24 passed`; production build — успешно (`1604` modules).
- Изолированный AI pipeline на отдельной PostgreSQL-БД и loopback-фикстуре прошёл: `pending`,
  временная ошибка и retry, официальный response envelope, structured result/evidence, `401`,
  Origin `403`, ручная правка с `expected_revision`, защита ручного результата, явный rerun,
  постоянная ошибка и повтор. Команда: `scripts\run-ai-mock-integration.ps1`; Yandex она не вызывает.
- Windows local demo после миграции запускает и отслеживает три процесса: backend, worker и frontend.
  Повторный `start-local-demo.ps1` идемпотентен; proxied `/api/health` возвращает `ok`.
- В реальном браузере без ключа новая заявка показала `Не подключено`, безопасную проверку
  подключения, ручное заполнение и сохранение. Результат сохранился после reload и полного
  stop/start приложения с PostgreSQL.
- Backend Telegram-уведомлений готов к подключению: durable outbox, initial alert,
  30-минутное one-time reminder, отмена при взятии в работу, bounded retry и
  scoped Bearer API для n8n. PostgreSQL 17.11 suite — `54 passed`; Ruff и compileall — clean.
  Telegram проверен только через `httpx.MockTransport`: реального бота/чата нет, сообщения не
  отправлялись. n8n вызывает два workflow с `limit:1`, HTTP timeout 30 s,
  execution timeout 45 s и без retry на стороне n8n.
- Два n8n 2.44.6 workflow прошли офлайн-валидатор и реальный CLI-импорт в отдельную
  PostgreSQL-базу n8n. Readiness/liveness вернули 200; оба workflow сохранены
  неактивными и содержат по пять узлов.
- Реальный n8n 2.44.6 runtime на отдельной PostgreSQL-базе прошёл fixture E2E: CLI execution
  проверил service-token `401`, duplicate outbox, отправку новой заявки, due reminder, отмену
  после смены статуса, 429 retry и timeout → `delivery_unknown`. Отдельный активный test server
  подтвердил срабатывание обоих Schedule Trigger (30 секунд и 1 минута). Использовался только
  loopback Telegram fixture; живых Telegram-вызовов не было.
- Windows runtime использует официальный portable Node 24.22.1 с проверенным SHA-256 и локальный
  n8n 2.44.6 в `.runtime/`. Основной n8n доступен на `127.0.0.1:5678`, readiness — 200, оба
  production workflow неактивны. Backend после миграции `20261025_0003` здоров, существующие
  заявки сохранены; правильный service token при отключённой конфигурации получает 503.
- Demo seeder проверен на реальном PostgreSQL: первый запуск создал шесть синтетических заявок,
  повторный вернул `created=0 existing=6`. В общей локальной БД 14 заявок, из них шесть demo:
  четыре с ручным разбором, две с `not_configured`, outbox для них пуст. Восемь прежних заявок
  сохранены; reset общей БД не запускался.
- Изолированный recovery/backup drill дважды прошёл на отдельном PostgreSQL cluster `:55433`.
  Worker был подтверждён в `processing`, БД останавливалась на 6 секунд, тот же процесс остался
  жив и записал bounded retry. После restart истёкший lease был забран повторно: одна extraction
  row, `attempts=2`, `revision=1`, `succeeded`, без дубля.
- App history/extraction/outbox и metadata двух неактивных пятиузловых n8n workflow совпали после
  `pg_dump`/`pg_restore` в отдельные базы и после restart PostgreSQL. Backend, worker и n8n были
  реально перезапущены на restored databases; API health и n8n readiness прошли. Пустая app DB
  также прошла Alembic и API health. Это clean database/runtime check, не clean dependency install
  и не Docker check. Yandex и Telegram не вызывались.
- Свежий браузерный regression на `:8080` прошёл: submit, list/search/filter, detail,
  status/history, manual extraction, реальный конфликт двух вкладок `409`, logout guard и возврат
  на прямую ссылку после login. Browser console чистая.
- AI-панель и keyboard focus проверены в точном `390×844`, DPR 1, без horizontal overflow;
  артефакты находятся в игнорируемом `artifacts/portfolio-qa-2026-10-25/`. Эквивалентный 200%
  reflow прошёл при `innerWidth=640`, DPR 2, но native Chrome text zoom отдельно не проверялся.
- Предварительный read-only hygiene scan охватил 117 Git-visible файлов (112 текстовых и две
  видимые картинки): подтверждённых секретов, private keys, dumps, archives или реального PII не
  найдено; ignore для `.env`, `.runtime/`, `node_modules/` и `artifacts/` подтверждён. Это
  эвристическая проверка, а не замена финальному secret scan перед первым commit/publication.
- Финальный snapshot этого этапа: shared API `/api/health` — `ok`, web `:8080` — 200, n8n
  readiness `:5678` — 200. Живые env-файлы не менялись, production workflow остались неактивными.
- Согласованный единый финальный review GPT-6 Astra завершён со статусом PASS для локального
  portfolio package. Два найденных P2 в QA harness исправлены: mutable environment изолирован
  дочерними PowerShell-процессами, а AI harness создаёт и проверяет точную disposable test DB.
  Независимый regression изоляции и owner-run clean missing-DB fixture прошли. Позднее владелец
  отдельно разрешил публичную GitHub-публикацию исходников; это не меняет исторический scope review.

## Ограничения

- В исходной среде QA Docker и системная PostgreSQL отсутствовали. Docker-конфигурация прошла статический review, но `docker compose up` требует отдельной проверки там, где доступен Docker.
- Для Windows QA PostgreSQL runtime/data находится в `%LOCALAPPDATA%\LeadFlowRuntime`, потому что `initdb` не может bootstrap-иться внутри кириллического пути этого репозитория. Остановка: `scripts\stop-local-demo.ps1`; удалять runtime следует только вручную после остановки и только по этому точному пути.
- Локальные `.env`, runtime-данные и тестовые артефакты игнорируются Git и не должны передаваться как часть репозитория.
- Предыдущий PowerShell outage-harness действительно зависал до recovery-заявки. Новый
  изолированный harness устранил handle inheritance и закрыл этот пробел; старый результат не
  используется как доказательство.
- Native Chrome zoom 200% и screen-reader проход остаются отдельными accessibility-проверками;
  текущий 200% артефакт — детерминированная reflow-эмуляция, а не native zoom.
- Docker отсутствует на проверенной машине, поэтому notification Compose profile прошёл YAML/static
  проверку, но контейнеры n8n/PostgreSQL фактически не запускались. Локальный эквивалент на настоящем
  PostgreSQL и настоящем n8n CLI/server проверен полностью.
