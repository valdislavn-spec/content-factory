# Cloudflare Worker `tg-cron`

Планировщик content-factory: cron `*/22` дёргает GitHub Actions
(`workflow_dispatch`) и следит за здоровьем публикаций.

- **Антидубль**: если последний запуск был < 8 минут назад — не дёргает снова.
- **Алерты в Telegram**: сбой диспатча, «протухший» health (нет успешного запуска
  > 2 часов), пропуск самого cron (> 45 минут тишины). Антиспам — 3 часа.
- **Health**: `GET https://tg-cron.valdislav-n.workers.dev/` → `200`/`503` + JSON
  с последним запуском (можно повесить UptimeRobot как внешний дубль).
- Секреты Worker: `GITHUB_TOKEN`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_ALERT_CHAT_ID`.

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
```

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

