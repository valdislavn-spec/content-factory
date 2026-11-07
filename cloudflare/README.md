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
