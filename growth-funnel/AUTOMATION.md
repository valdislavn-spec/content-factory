# Автопубликация Travel Funnel

## Рабочая схема (2026-11-23)

- **D1-очередь** — единственный источник правды:
  `https://links-tracker.valdislav-n.workers.dev/admin/queue`
- **Telegram** — GitHub Actions `growth-funnel.yml`, ежедневно в **09:05 UTC**
  через Cloudflare `github-cron` (`workflow_dispatch`).
- **Pinterest** — локальный Playwright-планировщик
  `growth-funnel/pinterest_scheduler.cjs`, запуск при старте и каждые 6 часов;
  проверка wall-clock раз в минуту, поэтому после сна Mac догоняет расписание.
  Официальный Pinterest API ждёт Standard access, поэтому используется
  залогиненный профиль `tools/playwright-mcp/profile-tp2`.
- **Отчёт** — GitHub Actions `travel-report.yml`, ежедневно в **09:30 UTC**;
  также отправляется в Telegram админу.
- **Трекер** — D1 `links-tracker`; клики, боты и очередь в одной базе.

## Состояние очереди

- 11 элементов уже опубликованы (Telegram + Pinterest).
- 10 будущих элементов: по одному Pinterest и одному Telegram в день
  с 2026-11-25 по 2026-11-29. Первый будущий пин (Лиссабон) уже
  опубликован 2026-11-24.
- Pinterest-пины лежат в `content-factory/docs/travel-finds/pins/future-*.png`
  и деплоятся вместе с лендингом.

## Ручные команды

Проверить очередь:

```bash
curl -sS -H "x-token: $LINK_TRACKER_ADMIN_TOKEN" \
  https://links-tracker.valdislav-n.workers.dev/admin/queue \
  | python3 -m json.tool | less
```

Опубликовать один Telegram-пост:

```bash
cd content-factory
PYTHONDONTWRITEBYTECODE=1 python3 growth-funnel/auto_publish.py \
  --platforms telegram --execute --limit-per-platform 1 --json
```

Опубликовать один Pinterest-пин вручную:

```bash
cd content-factory
PLAYWRIGHT_BROWSERS_PATH=/Users/vd/Documents/deepseek-harness/default-workspace/tools/playwright-mcp/ms-playwright \
/Users/vd/.dsh/dsh-runtimes/dsh-primary-runtime/dependencies/node/bin/node \
growth-funnel/pinterest_playwright_publish.cjs
```

Перезапустить локальный Pinterest-планировщик:

```bash
cd content-factory
nohup env PLAYWRIGHT_BROWSERS_PATH=/Users/vd/Documents/deepseek-harness/default-workspace/tools/playwright-mcp/ms-playwright \
/Users/vd/.dsh/dsh-runtimes/dsh-primary-runtime/dependencies/node/bin/node \
growth-funnel/pinterest_scheduler.cjs >> growth-funnel/pinterest-scheduler.log 2>&1 &
```

Построить отчёт:

```bash
cd content-factory
PYTHONDONTWRITEBYTECODE=1 python3 growth-funnel/travel_report.py --send --json
```

## Как выбираются элементы

`auto_publish.py` берёт только `status=queued` с `due <= сегодня`,
сортирует по `due`, затем по `id`, и публикует не больше одного элемента
на платформу за запуск. После успеха пишет `status=published`,
`published_at`, `message_id`, `published_url`, `attempts`.

Pinterest-планировщик берёт первый due-пин, публикует через UI и обновляет
ту же D1-запись. Если публикация не подтверждена диалогом, он проверяет
профиль `VladislavPint` и ищет пин по заголовку.

## GitHub Actions

- `growth-funnel.yml` — только Telegram (`--platforms telegram`).
- `travel-report.yml` — отчёт по воронке.
- `deploy-surge.yml` — деплой `docs/travel-finds` на `travel-finds.surge.sh`.
- Расписание `github-cron`:
  - 09:05 UTC — `growth-funnel.yml`
  - 09:30 UTC — `travel-report.yml`

Секреты GitHub: `LINK_TRACKER_ADMIN_TOKEN`, `TELEGRAM_BOT_TOKEN`,
`GROWTH_STATS_TOKEN`, `PINTEREST_ACCESS_TOKEN` (на будущее),
`SURGE_LOGIN`, `SURGE_TOKEN`.

## Ограничения

- `launchd`-агент записать нельзя: среда даёт `Operation not permitted` на
  `~/Library/LaunchAgents`. Плист лежит в
  `content-factory/growth-funnel/com.goodtravel.pinterest-publish.plist`;
  его можно установить вручную на Mac.
- Локальный планировщик живёт, пока Mac включён. После перезагрузки
  запустить команду из раздела выше.
- Pinterest UI может менять селекторы. При сбое смотрите
  `growth-funnel/pinterest-scheduler.log` и `pinterest-publish.err.log`.
