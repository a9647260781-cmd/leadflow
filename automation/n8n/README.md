# n8n-оркестрация уведомлений LeadFlow

В каталоге лежат два импортируемых workflow для n8n 2.44.6:

- `leadflow-new-lead-notifications.json` — запуск диспетчера новых заявок каждые 30 секунд;
- `leadflow-reminder-notifications.json` — запуск диспетчера напоминаний каждые 60 секунд (официально поддерживаемый интервал `1 minute`, так как seconds-интервал n8n ограничен 59 секундами).

Оба workflow экспортированы неактивными. Они не отправляют сообщения, пока оператор не настроит внутреннюю авторизацию, Telegram в backend и не опубликует каждый workflow.

## Граница ответственности

n8n — только планировщик. Каждый workflow вызывает внутренний FastAPI endpoint:

```http
POST http://backend:8000/api/internal/notifications/dispatch
Authorization: Bearer <NOTIFICATIONS_SERVICE_TOKEN>
Content-Type: application/json

{"kind":"new_lead|reminder","limit":1}
```

`http://backend:8000` — канонический адрес внутри Docker Compose network. Он не доступен нативному n8n в Windows. Изолированный Windows runtime-test импортирует игнорируемые копии, в которых заменён только host на `http://127.0.0.1:18000` для loopback-фикстуры. Эта замена не попадает в канонические экспорты.

Backend единолично определяет eligibility, захватывает durable outbox-задачи, вызывает Telegram, хранит статус доставки и решает, когда повторять попытку. Один вызов захватывает не более одной задачи: это сохраняет запас между 10-секундным ожиданием Telegram, двумя возможными 5-секундными подключениями к PostgreSQL и 30-секундным HTTP timeout n8n. Весь execution ограничен 45 секундами. Токен Telegram и chat ID не попадают в n8n. В workflow нет Telegram-узла, Code-узла, тестовых заявок и pin data.

Успешный ответ имеет вид:

```json
{
  "kind": "new_lead",
  "claimed": 0,
  "sent": 0,
  "retried": 0,
  "failed": 0,
  "delivery_unknown": 0,
  "skipped": 0
}
```

`claimed > 0` и `claimed = 0` явно разведены на ветки. Отсутствие готовых задач — успешный no-op. HTTP 401, 503 и любой другой non-2xx останавливает execution с ошибкой. n8n не повторяет HTTP-запрос самостоятельно: durable retry принадлежит backend.

## Подключение

1. Сгенерируйте длинный случайный `NOTIFICATIONS_SERVICE_TOKEN` и задайте его backend. Не коммитьте значение.
2. В n8n создайте credential типа **Header Auth** с именем `LeadFlow Backend Dispatch Auth`:
   - Name: `Authorization`
   - Value: `Bearer <тот же NOTIFICATIONS_SERVICE_TOKEN>`
3. Импортируйте оба JSON-файла. Откройте HTTP Request-узел в каждом workflow и выберите созданный credential. Экспорты ссылаются на стабильные ID/name, но после ручного создания n8n может выдать credential другой внутренний ID, поэтому выбор в UI обязателен.
4. До реального запуска задайте `TELEGRAM_BOT_TOKEN` и `TELEGRAM_CHAT_ID` только в backend. Без них endpoint честно вернёт 503; это не зависший и не фальшиво успешный статус.
5. Запустите **Test workflow** для обоих workflow. Schedule Trigger в test-режиме срабатывает сразу. Проверьте ветку no-op и ветку с обработанным пакетом.
6. Только после успешной проверки опубликуйте workflow. Schedule Trigger работает только для опубликованного workflow.

## Данные execution

Успешные production execution и manual execution не сохраняются. Для ошибок сохраняется минимальный execution с redaction; тело запроса не содержит данных заявки, а тело успешного ответа — только счётчики. Сервисный токен хранится в credential store n8n, а Telegram-секреты — только в backend environment.

## Проверка экспортов

```powershell
node automation/n8n/validate-workflows.mjs
```

Валидатор проверяет версии узлов n8n 2.44.6, граф и обе ветки IF, расписание, endpoint, request body, Header Auth reference, отключённые HTTP retry, настройки retention и отсутствие встроенных секретов. Это офлайн-проверка контракта, а не замена runtime-импорта и execution test в настоящем n8n.

Актуальные схемы узлов сверены с исходными кодами n8n 2.44.6: [Schedule Trigger](https://github.com/n8n-io/n8n/blob/n8n%402.44.6/packages/nodes-base/nodes/Schedule/ScheduleTrigger.node.ts), [HTTP Request](https://github.com/n8n-io/n8n/blob/n8n%402.44.6/packages/nodes-base/nodes/HttpRequest/HttpRequest.node.ts), [If](https://github.com/n8n-io/n8n/blob/n8n%402.44.6/packages/nodes-base/nodes/If/V2/IfV2.node.ts). По [документации Schedule Trigger](https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.scheduletrigger/) workflow нужно опубликовать, чтобы расписание работало.
