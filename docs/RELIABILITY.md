# Надёжность публикаций

Цель: не допускать **молчаливых** пропусков. Абсолютной гарантии «без отказов»
не существует, но сбой должен приводить к повтору, алерту или понятной ошибке.

## Что уже работает

- **Retry Telegram API**: ответы `429/500/502/503/504` повторяются до 3 раз
  с учётом `retry_after`.
- **Plain-text fallback**: если Telegram не смог разобрать HTML, пост
  отправляется повторно без `parse_mode`.
- **Очередь повторной публикации**: неудачная отправка в Telegram сохраняется
  в SQLite (`publish_retries`) и повторяется на следующих тиках.
  Настройки: `pipeline.publish_retry_max_attempts`,
  `pipeline.publish_retry_base_minutes`.
- **Health по каналам**: `scripts/check_publish_health.py` падает, если у
  канала были ошибки публикации или были посты, но ничего не опубликовано.
- **Сохранение состояния при падении**: workflow сохраняет SQLite и state
  через `actions/cache/save@v4` даже при ошибке, а также кладёт БД в artifact.
- **Защита от параллельных запусков**: `concurrency` на уровне workflow.
- **Алерт по застрявшей очереди**: `tg-cron` раз в 15 минут проверяет D1;
  если due-запись висит дольше 30 минут, приходит Telegram-алерт.

## Healthchecks.io

1. Создать check с периодом 30 минут и grace 15 минут.
2. Скопировать ping URL.
3. Добавить в GitHub Secrets репозитория `content-factory`:
   `HEALTHCHECK_PING_URL`.
4. Workflow будет отправлять ping в конце каждого запуска; при падении —
   `/fail`, при успехе — обычный ping.

Если секрет не задан, шаг просто пропускается.

## UptimeRobot / Better Stack

Публичный health endpoint Cloudflare Worker `tg-cron`:

```
https://<worker-domain>/
```

Он отдаёт `200`, если последний запуск content-factory свежий и успешный,
иначе `503`. Достаточно бесплатного HTTP-монитора с интервалом 5 минут.

## Cloudflare D1 (основное durable-хранилище)

Создана D1-база `content-factory-state` и API в Worker `tg-cron`:

- `GET/PUT /api/v1/state/:name` — состояние планировщика EN/ES;
- `POST /api/v1/queue` — снимок поста для повтора;
- `GET /api/v1/queue/due` — очередь к повтору;
- `POST /api/v1/queue/done` — успешная публикация;
- `POST /api/v1/health/tick` — health канала;
- `GET /api/v1/health` — очередь и health каналов.

Запись защищена `STATE_API_TOKEN`. В GitHub Actions нужны:

- Repository variable `CONTENT_FACTORY_STATE_URL` =
  `https://tg-cron.valdislav-n.workers.dev`;
- Repository secret `CONTENT_FACTORY_STATE_TOKEN` — тот же токен, что
  `wrangler secret put STATE_API_TOKEN`.

Pipeline сначала читает очередь из D1, затем работает с локальной SQLite;
успешные/неудачные попытки синхронизируются обратно в D1. Если D1
недоступна, публикации продолжаются на локальной очереди. Лимит GitHub
Variable в 45 КБ больше не ограничивает состояние: D1 принимает его
целиком, а GitHub остаётся только резервной копией.

## Ограничения

- D1 и Worker — внешний сервис; при полном отказе Cloudflare публикации
  приостанавливаются, но состояние не теряется.
- Бесплатные тарифы не дают SLA; для критичного продакшена нужен платный
  тариф или собственный runner.
