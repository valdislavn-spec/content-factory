# cf-stars — Telegram Stars donations

Cloudflare Worker that turns the existing crosspromo bot (`@Cf_crosspromo_bot`) into a
Telegram Stars donation endpoint while forwarding all other updates to the legacy
Railway webhook.

## Commands

- `/donate` — reply with 50 / 100 / 250 ⭐ inline buttons.
- Any other update — forwarded to `OLD_WEBHOOK` (configured in `index.js`).

## Deploy

1. Create a Cloudflare Worker named `stars-pay` and enable workers.dev route.
2. Bind secrets:
   - `BOT_TOKEN` — bot token (e.g. `TELEGRAM_ADMINHUB_BOT_TOKEN`).
   - `WEBHOOK_SECRET` — random string, used as Telegram `secret_token`.
   - optional `TG_API_BASE` — proxy base, default `https://api.telegram.org`.
3. Deploy `index.js` (classic service-worker syntax; `body_part: "script"`).
4. Point the bot webhook at the worker and pass the same secret:

```bash
curl -F "url=https://stars-pay.<subdomain>.workers.dev/" \
     -F "secret_token=$WEBHOOK_SECRET" \
     -F 'allowed_updates=["message","callback_query","pre_checkout_query","inline_query"]' \
     https://api.telegram.org/bot$BOT_TOKEN/setWebhook
```

5. Open the bot, press **Start** (a bot cannot initiate a conversation, so `/donate`
   only works after the user has started it), then send `/donate`.

All Stars payments use `currency: "XTR"`, empty `provider_token`, and are handled
statelessly; `successful_payment` replies with a thank-you message.

## Rollback

Restore the previous webhook (saved before the switch):

```bash
curl -F "url=https://backend-git-production-cb93.up.railway.app/webhook/9273924219" \
     https://api.telegram.org/bot$BOT_TOKEN/setWebhook
```
