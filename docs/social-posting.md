# Как content-factory постит в другие соцсети

## Схема

1. Пост генерируется один раз (Telegram HTML).
2. Публикуется в Telegram (основной канал).
3. Затем по очереди вызываются публикаторы из `publisher_ids` канала:
   `bluesky`, `mastodon`, `discord`, `akkoma`, `tumblr`, `x`, `vk`,
   `facebook`, `linkedin`, `medium` и т.д.
4. Публикатор с `optional = true` (Bluesky, Mastodon, Discord, Tumblr,
   Akkoma и др.) **тихо пропускается**, если нет кредов — пайплайн не падает.
5. Для каждого канала можно задать отдельный аккаунт суффиксом:
   `BLUESKY_HANDLE_AI_NEWS`, `MASTODON_TOKEN_CRYPTO_ES` и т.п.

## Что реально работает (08.11.2026)

| Сеть | Статус | Как |
|---|---|---|
| **Telegram** | ✅ 63 публикации | основной, все каналы |
| **Mastodon** | ✅ 2 публикации | EN-каналы; `MASTODON_NO_LINKS=1` (без ссылок) |
| **Tumblr** | ✅ 1 публикация | отдельный workflow `tumblr-digest` раз в 5 ч, не каждый пост |
| **Akkoma** | ⚙️ настроен | только `crypto-news`; после фикса крипто-дат должен пойти |
| **Bluesky** | ⛔ нет кредов | нужны `BLUESKY_HANDLE`/`BLUESKY_APP_PASSWORD` |
| **Discord** | ⛔ нет webhook | нужен `DISCORD_WEBHOOK_URL` (свой сервер) |
| **X** | ⛔ не включён | есть `X_API_KEY/SECRET` и `X_ACCOUNT_BLOB`, но нет publisher_ids |
| **VK** | ⛔ нет токена | нужны `VK_ACCESS_TOKEN`/`VK_GROUP_ID` |
| **Facebook/LinkedIn/Medium** | ⛔ нет кредов | включаются добавлением в publisher_ids |
| **Reddit** | ⚠️ dry-run | нужны `REDDIT_*`; scheduled live без них не постит |
| **Instagram/Threads/Pinterest** | ⛔/⚙️ | Instagram/Threads без кредов; Pinterest — отдельный check |

## Исправлено сейчас

У ES-каналов (`tech-ai-es`, `crypto-es`, `futbol-es`) не было
`publisher_ids` — они постили только в Telegram. Добавил:
`[telegram, mastodon, bluesky, discord]`.
Bluesky/Discord без кредов будут пропускаться, Mastodon начнёт кросс-постить.
Коммит: `1e2ed4a`.

## Чтобы включить

1. Добавить секреты в GitHub → Settings → Secrets:
   - Bluesky: `BLUESKY_HANDLE`, `BLUESKY_APP_PASSWORD`
   - Discord: `DISCORD_WEBHOOK_URL`
   - X: `X_API_KEY`, `X_API_SECRET`, `X_ACCESS_TOKEN`, `X_ACCESS_SECRET`
   - VK: `VK_ACCESS_TOKEN`, `VK_GROUP_ID`
   - Reddit: `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, `REDDIT_USERNAME`,
     `REDDIT_PASSWORD`, `REDDIT_SUBREDDIT`
2. Добавить имя в `publisher_ids` нужного канала.
3. Проверить: `python -m content_factory run --channel <id> --dry-run`, затем
   live-слот.

## Важно

- Mastodon: лимиты инстанса, не спамить; сейчас без ссылок.
- Discord: только свои серверы, webhook = 30 сообщений/мин.
- Bluesky: App Password, не основной пароль.
- X/Reddit: OAuth-токены истекают, нужен refresh.
- Tumblr — дайджест, не по каждому посту.
- Все публикаторы логируются в `data/logs/factory.log` и таблицу `publishes`.
