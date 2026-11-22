# Cloudflare Worker `tg-cron`

Планировщик content-factory: cron `*/15` дёргает GitHub Actions
(`workflow_dispatch`) и следит за здоровьем публикаций.

- **Антидубль**: если последний запуск был < 8 минут назад — не дёргает снова.
- **Алерты в Telegram**: сбой диспатча, «протухший» health (нет успешного запуска
  > 2 часов), пропуск самого cron (> 45 минут тишины). Антиспам — 3 часа.
- **Health**: `GET https://tg-cron.valdislav-n.workers.dev/` → `200`/`503` + JSON
  с последним запуском (можно повесить UptimeRobot как внешний дубль).
- Секреты Worker: `GITHUB_TOKEN`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_ALERT_CHAT_ID`, `STATE_API_TOKEN`.
- D1 `content-factory-state`: состояние планировщика EN/ES, очередь ретраев и health каналов.

## Деплой

```bash
cd cloudflare
CLOUDFLARE_ACCOUNT_ID=... CLOUDFLARE_API_TOKEN=... \
  npx wrangler deploy --config wrangler.toml
```

Секреты:

```bash
npx wrangler secret put GITHUB_TOKEN --config wrangler.toml
npx wrangler secret put TELEGRAM_BOT_TOKEN --config wrangler.toml
npx wrangler secret put TELEGRAM_ALERT_CHAT_ID --config wrangler.toml
npx wrangler secret put STATE_API_TOKEN --config wrangler.toml
```

D1 создаётся один раз:

```bash
npx wrangler d1 create content-factory-state
# UUID вставить в [[d1_databases]] -> database_id
npx wrangler d1 execute content-factory-state --remote --file schema.sql
```

API (только с `Authorization: Bearer <STATE_API_TOKEN>`):
`/api/v1/state/:name`, `/api/v1/queue`, `/api/v1/queue/due`,
`/api/v1/queue/done`, `/api/v1/health/tick`, `/api/v1/health`.

KV создаётся так:

```bash
npx wrangler kv namespace create tg-cron-state
```

## Email-подписка (cf-subscribe)

Форма на GitHub Pages -> Worker -> Cloudflare KV (и опционально Brevo).

- Код: `cloudflare/subscribe.mjs`; конфиг: `cloudflare/wrangler.subscribe.toml`.
- KV namespace: `content-factory-subscribers` (`422c94623a2a4b88941bd86178429ba8`).
- URL: https://cf-subscribe.valdislav-n.workers.dev/
- Секреты Worker (для синхронизации с Brevo):
  `BREVO_API_KEY`, `BREVO_LIST_ID_EN`, `BREVO_LIST_ID_ES`.
- Деплой: `npx wrangler deploy --config wrangler.subscribe.toml`.
- Инструкция целиком: `docs/promo/email-digest-setup.md`.

