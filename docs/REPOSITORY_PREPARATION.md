# Подготовка репозитория LeadFlow

Этот документ фиксирует подготовку исходников к согласованной публикации в публичном GitHub-репозитории `leadflow`.

## Текущее состояние

- ветка: `main`;
- valid `HEAD` отсутствует, коммитов нет;
- remote отсутствует;
- staging не выполнялся;
- публичный hosting не настроен;
- final pre-publication review завершён: [`FINAL_REVIEW.md`](FINAL_REVIEW.md) — PASS локального package без оставшихся actionable P0/P1/P2;
- владелец разрешил публикацию исходников; создание GitHub-репозитория и push выполняет координатор;
- публичный hosting приложения не настроен и в текущий локальный portfolio release не входит.

Текущий кандидат включает приложение, инфраструктуру, документацию, портфолио-кейс и пять curated screenshots в `docs/portfolio/images/`. Сырые QA-кадры остаются в игнорируемом `artifacts/`.

Последняя packaging-проверка: `scripts\check-repository.ps1` завершился успешно для 131 Git-visible candidate files. Проверены обязательные portfolio-файлы, ignore rules, UTF-8, trailing whitespace, локальные Markdown links/images и типовые credential signatures. Для финального review backend suite отдельно повторён на disposable PostgreSQL-БД (`54 passed`); frontend `24 passed` — результат последней функциональной регрессии.

## Что войдёт и не войдёт в Git

В кандидат входят:

- `frontend/`, `backend/`, `docker/`, `automation/n8n/`;
- root Compose/config examples;
- воспроизводимые `scripts/` и `tests/`;
- `README.md`, продуктовые и эксплуатационные документы;
- curated portfolio images и их manifest/captions.

Не входят:

- `.env`, `.runtime/`, credentials, cookies и пароли;
- PostgreSQL data/dumps, SQLite-файлы, логи и backups;
- `node_modules/`, virtual environments, build output и coverage;
- raw `artifacts/`, Playwright reports и test results.

Лицензия не выбрана, поэтому файл `LICENSE` намеренно не добавлен: публикация исходников без лицензии не предоставляет третьим лицам право копировать, изменять или распространять код. Curated screenshots являются прямыми снимками приложения; этот документ не обещает прав на сторонние материалы.

## Воспроизводимая проверка кандидата

```powershell
.\scripts\check-repository.ps1
git status --short
```

Скрипт проверяет только Git-visible candidate files и не выводит найденные значения:

- запрещённые runtime/log/dump/build пути;
- типовые сигнатуры credentials/private keys;
- UTF-8, финальный newline и trailing whitespace;
- существование локальных Markdown links и images;
- наличие curated portfolio set;
- ignore rules для локальных секретов и сырых артефактов.

Это эвристическая hygiene-проверка, а не гарантия отсутствия секретов. Перед первым commit и особенно перед публичным push нужен отдельный финальный scan рабочего дерева; после появления истории — scan всей истории.

## Последовательность публикации

Финальный review завершён, а публикация исходников разрешена владельцем. Локальную подготовку и
коммит выполняет infra; создание GitHub-репозитория `leadflow`, remote и push выполняет координатор.

1. Использовать публичный режим; не добавлять лицензию без отдельного выбора владельца.
2. Проверить provenance публикуемых assets.
3. Обновить screenshots/текст только из финального release candidate.
4. Запустить `scripts\check-repository.ps1` и согласованные tests затронутых областей.
5. Сверить итог уже завершённого review в [`FINAL_REVIEW.md`](FINAL_REVIEW.md); два найденных P2 исправлены и перепроверены.
6. Выполнить dedicated secret scan рабочего дерева; после initial commit — history scan.
7. Просмотреть staging:

   ```powershell
   git add -A
   git diff --cached --check
   git diff --cached --stat
   git status --short
   ```

8. Вручную проверить staged filenames и содержимое изменений. Не продолжать при неожиданном `.env`, `.runtime`, dump, log, raw artifact или credential.
9. Создать initial commit. Remote и push передать координатору.

Публичный hosting, HTTPS, live Yandex и live Telegram не входят в этот релиз исходников. Yandex и Telegram остаются честно описанными как неподключённые интеграции, проверенные только на изолированных fixture-контурах.
