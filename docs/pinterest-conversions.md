# Pinterest Conversions API v5

Серверная отправка конверсий в Pinterest: `lead`, `signup`, `checkout` и другие.
Нужна, чтобы Pinterest оптимизировал рекламу на подписки и покупки, а не на клики.

## Что добавлено

- `content-factory/scripts/pinterest_conversions.py` — клиент и CLI.
- `content-factory/infra/cloudflare/links-tracker/worker.js` — при `/subscribe`
  автоматически отправляет `lead` в Pinterest (если заданы секреты).
- Формы подписки на 50 страницах передают `epik` (Pinterest click id) и `url`.
- `POST /admin/conversion` — ручная отправка события с `ADMIN_TOKEN`.
- `GET /admin/pinterest-status` — проверка, заданы ли токен и ad account.
- `content-factory/tests/test_pinterest_conversions.py` — тесты клиента.

## Переменные окружения

Файл: `content-factory/.env`.

```dotenv
PINTEREST_CAPI_TOKEN=pina_...
PINTEREST_AD_ACCOUNT_ID=549755885175
PINTEREST_CAPI_API_BASE=https://api.pinterest.com/v5
```

Токен для конверсий отдельный от `PINTEREST_ACCESS_TOKEN` (пины). Ему нужен
scope `ads:write`. Для проверки через `GET /ad_accounts/{id}` нужен ещё
`ads:read`.

`PINTEREST_AD_ACCOUNT_ID` — id рекламного аккаунта из Pinterest Ads Manager
(не board id и не user id).

## CLI

```bash
cd content-factory

# только проверить конфиг, без сети
python3 scripts/pinterest_conversions.py --check

# проверить токен и доступ к рекламному аккаунту
python3 scripts/pinterest_conversions.py --verify

# посмотреть payload, ничего не отправляя
python3 scripts/pinterest_conversions.py \
  --event lead --email test@example.com \
  --external-id tg:123 --click-id epik_abc \
  --source-url https://example.com/travel --dry-run

# отправить реальное событие
python3 scripts/pinterest_conversions.py \
  --event lead --email test@example.com --send

# отправить пакет из JSON
python3 scripts/pinterest_conversions.py --from-json events.json --send

# отправить новых подписчиков из D1 (state-файл не даёт дублей)
LINK_TRACKER_ADMIN_TOKEN=... python3 scripts/pinterest_conversions.py \
  --from-d1 --send --state .local/pinterest-capi-state.json

При выгрузке из D1 берутся только подписчики за последние 7 дней:
Pinterest отбрасывает более старые `event_time`.
```

## Автоматическая конверсия при подписке

`links-tracker` при `POST /subscribe` пишет подписчика в D1 и через
`ctx.waitUntil()` отправляет `lead` в Pinterest. Запрос к Pinterest не
задерживает ответ пользователю и не ломает подписку при ошибке.

Payload:

- `event_name`: `lead`
- `action_source`: `web`
- `event_id`: sha256(`lead|email`), чтобы повторная подписка не давала дубль
- `user_data.em`: sha256(email в нижнем регистре)
- `user_data.external_id`: sha256(`email:<email>`)
- `user_data.click_id`: `epik` из URL, если он был
- `event_source_url`: `body.url` или `Referer`
- `custom_data.source`, `custom_data.lang`

Если `PINTEREST_CAPI_TOKEN` или `PINTEREST_AD_ACCOUNT_ID` не заданы, воркер
просто пропускает отправку. Подписки продолжают работать.

### Ручное событие

```bash
curl -X POST "https://links-tracker.valdislav-n.workers.dev/admin/conversion?token=$LINK_TRACKER_ADMIN_TOKEN" \
  -H 'content-type: application/json' \
  -d '{"event_name":"signup","email":"user@example.com","epik":"epik_abc","source":"landing","lang":"en"}'
```

### Статус

```bash
curl "https://links-tracker.valdislav-n.workers.dev/admin/pinterest-status?token=$LINK_TRACKER_ADMIN_TOKEN"
```

Ответ: `configured`, `token_set`, `ad_account_set`.

## Деплой

```bash
bash content-factory/scripts/deploy_link_tracker.sh --update
```

Скрипт сам заливает `PINTEREST_CAPI_TOKEN` и `PINTEREST_AD_ACCOUNT_ID` как
секреты Cloudflare Worker, если они есть в `.env`.

## Атрибуция клика

Pinterest добавляет к исходящим ссылкам параметр `epik`. Формы подписки
теперь читают его из `location.search` и передают в `/subscribe`. Редирект
`/r/{code}` сохраняет `epik` и utm-метки при переходе на лендинг. Без `epik`
событие всё равно уйдёт, но матчинг с рекламным кликом будет хуже: останутся
только хешированные email/external_id.

## Статус и проверка

На 16.11.2026 интеграция настроена и проверена:

- `PINTEREST_AD_ACCOUNT_ID=549769603178` сохранён в `.env` и как секрет Worker.
- Токен имеет `ads:write`: безопасный probe с пустым `data` вернул 400
  валидацию, а не 403. `GET /ad_accounts` при этом отвечает `missing: ads:read` —
  для отправки событий это не нужно.
- Тестовое событие через CLI в режиме `--test` обработано Pinterest:
  `num_events_processed: 1`, warning пустой.
- Тестовое событие через Worker `/admin/conversion` с `"test": true` тоже
  обработано.
- `GET /admin/pinterest-status` возвращает `configured: true`.

Проверка без влияния на отчёты:

```bash
cd content-factory
python3 scripts/pinterest_conversions.py \
  --event lead --email test@example.com --click-id epik_test \
  --source-url https://example.com/travel \
  --client-ip 203.0.113.10 --client-user-agent 'Mozilla/5.0 test' \
  --send --test --json
```

```bash
curl -X POST "https://links-tracker.valdislav-n.workers.dev/admin/conversion?token=$LINK_TRACKER_ADMIN_TOKEN" \
  -H 'content-type: application/json' \
  -d '{"event_name":"lead","email":"test@example.com","epik":"epik_test","url":"https://example.com/travel","test":true}'
```

`--test` / `"test": true` не учитываются в отчётности Pinterest. Боевые
события уходят с `test: false` автоматически.

