# GrowthBot storage: do-redis

GrowthBot больше не использует Cloudflare KV. Хранилище — Redis-совместимый
воркер [`zion-off/do-redis`](https://github.com/zion-off/do-redis) на
Cloudflare Durable Objects.

## Почему

Cloudflare KV на free-плане имеет общий лимит записей на аккаунт. После его
исчерпания GrowthBot получал `429` на `PUT`, не сохранял пользователя и не
отправлял welcome-сообщение. `do-redis` хранит данные в SQLite внутри Durable
Object и не расходует квоту Cloudflare KV.

## Что развёрнуто

- Worker: `do-redis-growth`
- URL: https://do-redis-growth.valdislav-n.workers.dev
- Durable Object: `StorageDurableObject`
- Секрет: `AUTH_TOKEN`
- Токен GrowthBot: `growth-funnel/.secrets/do-redis-growth-token`

## Проверка

```bash
TOKEN=$(cat growth-funnel/.secrets/do-redis-growth-token)
curl -sS https://do-redis-growth.valdislav-n.workers.dev \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '["PING"]'
# {"result":"PONG"}
```

Ключи GrowthBot:

- `user:<telegram_id>` — профиль, подписка, рефералы;
- `stats` — общая статистика;
- `giveaway:participants` — участники;
- `giveaway:active` — флаг розыгрыша.

## Передеплой GrowthBot

```bash
bash growth-funnel/deploy_growthbot.sh
```

Скрипт:

1. проверяет `PING` у do-redis;
2. деплоит GrowthBot с service binding `REDIS → do-redis-growth`;
3. обновляет секреты `BOT_TOKEN`, `WEBHOOK_SECRET`, `ADMIN_ID`, `REDIS_TOKEN`;
4. переустанавливает Telegram webhook.

## Если do-redis нужно пересоздать

```bash
git clone https://github.com/zion-off/do-redis /tmp/do-redis
cd /tmp/do-redis/do-redis
# в wrangler.json: "name": "do-redis-growth"
npx wrangler deploy
npx wrangler secret put AUTH_TOKEN
curl https://do-redis-growth.<subdomain>.workers.dev \
  -H "Authorization: Bearer $TOKEN" \
  -d '["INIT"]'
```

После пересоздания обновите `growth-funnel/.secrets/do-redis-growth-token`
и выполните `bash growth-funnel/deploy_growthbot.sh`.
