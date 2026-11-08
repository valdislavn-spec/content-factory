# Трекер коротких ссылок (Cloudflare Worker + KV)

Свой сервис коротких ссылок с клик-аналитикой — под партнёрские ссылки всех
сетей (BingX, MyLead, collaborator.pro и т.д.). Работает на Cloudflare бесплатно.

**URL:** https://links-tracker.valdislav-n.workers.dev
**KV namespace:** `content-factory-links`
**Исходник воркера:** [`infra/cloudflare/links-tracker/worker.js`](../../infra/cloudflare/links-tracker/worker.js)
**Деплой:** [`scripts/deploy_link_tracker.sh`](../../scripts/deploy_link_tracker.sh)

## Эндпоинты

| Метод | Путь | Назначение |
|---|---|---|
| GET | `/r/{code}` | 302 на target + запись клика (день, канал) |
| GET | `/stats?token=STATS[&code=]` | статистика: total, по дням, по каналам, last_click |
| POST | `/admin/links` | создать/обновить ссылку (header `x-token: ADMIN`) |
| GET | `/admin/links` | список ссылок (admin) |

Тело создания ссылки:
```json
{"code":"bingx-crypto-news","target":"https://bingxdao.com/invite/WYYEGK/",
 "channel":"crypto-news","network":"bingx","label":"BingX referral (EN)"}
```

## Env (.env)

```
LINK_TRACKER_BASE=https://links-tracker.valdislav-n.workers.dev
LINK_TRACKER_ADMIN_TOKEN=...   # секрет воркера ADMIN_TOKEN
LINK_TRACKER_STATS_TOKEN=...   # секрет воркера STATS_TOKEN
```

## Уже созданные ссылки

| Код | Куда ведёт | Канал |
|---|---|---|
| `bingx-crypto-news` | BingX WYYEGK | crypto-news |
| `bingx-crypto-es` | BingX WYYEGK | crypto-es |
| `bingx-default` | BingX WYYEGK | алерты (без канала) |
| `mylead-crypto-news` | MyLead `r/dJ67Qo` | crypto-news |
| `collab-crypto-news` | collaborator.pro signup | crypto-news |

## Использование

```bash
# список / статистика / создание / базовый набор
python scripts/links_admin.py list
python scripts/links_admin.py stats
python scripts/links_admin.py stats --json
python scripts/links_admin.py create --code travel-news --target "https://..." \
  --channel crypto-news --network travelpayouts --label "Travelpayouts"
python scripts/links_admin.py seed
```

В постах/алертах ссылка берётся из конфига канала:

```yaml
affiliate:
  enabled: true
  link: "https://bingxdao.com/invite/WYYEGK/"          # fallback
  tracked_url: "https://links-tracker.valdislav-n.workers.dev/r/bingx-crypto-news"
```

или без `tracked_url`, через код + env:

```yaml
affiliate:
  code: bingx-crypto-news       # → LINK_TRACKER_BASE + /r/<code>
```

Приоритет: `AFFILIATE_LINK[_CHANNEL]` (прямая, без трекинга) → `tracked_url` →
`code` + `LINK_TRACKER_BASE` → `link`.

## Статистика

`/stats` отдаёт по каждой ссылке: `total`, `days` (последние 60 дней),
`channels`, `last_click`. Этого достаточно, чтобы видеть, какой канал реально
кликает по партнёрке, и сравнивать сети (BingX vs MyLead и т.д.).

## Деплой/обновление воркера

```bash
bash scripts/deploy_link_tracker.sh            # деплой + секреты (если заданы)
bash scripts/deploy_link_tracker.sh --update   # только обновить код воркера
```

Скрипт создаёт KV (если нет), заливает `worker.js`, ставит секреты
`ADMIN_TOKEN`/`STATS_TOKEN` из env (`LINK_TRACKER_ADMIN_TOKEN`/`..._STATS_TOKEN`)
и включает workers.dev-субдомен.

## Ограничения

- KV free: 1 000 записей/день (в минуту — 100k чтений); клики считаются
  read-modify-write, при очень высоком трафике возможна небольшая потеря.
- Персональные данные не пишутся: только счётчики по дням/каналам и время
  последнего клика (без IP/UA).
- Ссылки можно выключать (`active: false`) — редирект вернёт 404.
